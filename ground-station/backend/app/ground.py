"""Ground segment: frame reception, telemetry decoding, image reassembly,
command uplink (signing + audit) and ground-side alarms.

Not thread-safe by design: only the engine thread calls into this object.
API threads talk to it through SimulationEngine.submit().
"""

from __future__ import annotations

import hashlib
import io
import logging
import uuid
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from PIL import Image
from pydantic import ValidationError

from onboard.communications.link import Link
from shared import SATELLITE_ID
from shared.protocol import (
    MessageType,
    Packet,
    PacketError,
    decode,
    decode_chunk,
    decode_json,
    encode,
    encode_json,
    sign,
)
from shared.schemas import (
    CRITICAL_COMMANDS,
    CommandAck,
    CommandBody,
    CommandType,
    EventMessage,
    Housekeeping,
    ImageMeta,
)

from .db import CommandRow, EventRow, ImageRow, TelemetryRow
from .objectstore import ObjectStore
from .persistence import Persistence

log = logging.getLogger("ground.segment")

FINAL_STATES = {"COMPLETED", "REJECTED", "FAILED", "TIMEOUT"}
PARTIAL_EXPIRY = timedelta(minutes=30)
NACK_STALL = timedelta(seconds=5)
MAX_GROUND_NACKS = 40
MAX_MISSING_PER_NACK = 400  # keeps the IMAGE_ACK command well under MAX_PAYLOAD


@dataclass
class Partial:
    image_id: str
    total: int
    started: datetime
    meta: ImageMeta | None = None
    chunks: dict[int, bytes] = field(default_factory=dict)
    last_update: datetime | None = None
    nacks: int = 0


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


class GroundSegment:
    def __init__(
        self,
        key: bytes,
        link: Link,
        clock: Callable[[], datetime],
        persistence: Persistence,
        objects: ObjectStore,
        ack_timeout_s: float = 60.0,
        publish: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._key, self.link, self.clock = key, link, clock
        self.persistence, self.objects = persistence, objects
        self.ack_timeout_s = ack_timeout_s
        self._publish = publish or (lambda topic, payload: None)
        self._seq = 0
        self.partials: dict[str, Partial] = {}
        self.latest_hk: dict[str, Any] | None = None
        self.last_rx_utc: datetime | None = None
        self.stats = {"rx_frames": 0, "rx_crc_errors": 0, "rx_other_errors": 0, "tx_frames": 0, "rx_duplicates": 0}
        self._recent_ids: deque[tuple[int, int]] = deque(maxlen=2048)
        self.telemetry: deque[dict] = deque(maxlen=7200)
        self.events: deque[dict] = deque(maxlen=1000)
        self.commands: OrderedDict[str, dict] = OrderedDict()
        self.images: OrderedDict[str, dict] = OrderedDict()
        self.outbox: dict[str, list] = {"events": [], "commands": [], "images": []}
        self._crc_reported_at: datetime | None = None
        self._cmd_rows: dict[str, CommandRow] = {}

    # ----------------------------------------------------------------- events
    def ground_event(self, severity: str, source: str, code: str, message: str) -> dict:
        return self._record_event(
            {"utc": self.clock(), "severity": severity, "source": source, "code": code, "message": message}, origin="ground"
        )

    def _record_event(self, ev: dict, origin: str) -> dict:
        row = EventRow(
            id=str(uuid.uuid4()),
            utc=ev["utc"],
            severity=ev["severity"],
            origin=origin,
            source=ev["source"],
            code=ev["code"],
            message=ev["message"],
            acknowledged=False,
        )
        self.persistence.add(row)
        d = event_to_dict(row)
        self.events.append(d)
        self.outbox["events"].append(d)
        self._publish("events", d)
        return d

    def acknowledge_event(self, event_id: str, operator: str) -> dict | None:
        for d in self.events:
            if d["id"] == event_id:
                d["acknowledged"], d["acknowledged_by"] = True, operator
                row = EventRow(**{k: v for k, v in d.items() if k != "utc"}, utc=datetime.fromisoformat(d["utc"]))
                self.persistence.add(row)
                return d
        return None

    # --------------------------------------------------------------- commands
    def send_command(self, ctype: CommandType, args: dict, operator: str, automatic: bool = False) -> dict:
        now = self.clock()
        cmd_id = str(uuid.uuid4())
        body = CommandBody(command_id=cmd_id, type=ctype, args=args)
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        pkt = Packet(SATELLITE_ID, MessageType.COMMAND, self._seq, int(now.timestamp() * 1000), encode_json(body.model_dump(mode="json")))
        frame = encode(sign(self._key, pkt))
        row = CommandRow(
            id=cmd_id,
            created_utc=now,
            type=ctype.value,
            args=args,
            operator=operator,
            automatic=automatic,
            critical=ctype in CRITICAL_COMMANDS,
            status="SENT",
            seq=self._seq,
            reason="",
            ack_utc=None,
            detail={},
        )
        self._cmd_rows[cmd_id] = row
        self.link.send(frame)
        self.stats["tx_frames"] += 1
        return self._update_command(row)

    def _update_command(self, row: CommandRow) -> dict:
        self.persistence.add(row)
        d = command_to_dict(row)
        self.commands[row.id] = d
        self.commands.move_to_end(row.id)
        while len(self.commands) > 500:
            old, _ = self.commands.popitem(last=False)
            self._cmd_rows.pop(old, None)
        if not row.automatic:
            self.outbox["commands"].append(d)
        return d

    def check_timeouts(self) -> None:
        now = self.clock()
        for row in list(self._cmd_rows.values()):
            if row.status == "SENT" and (now - row.created_utc).total_seconds() > self.ack_timeout_s:
                row.status, row.reason = "TIMEOUT", f"no acknowledgement within {self.ack_timeout_s:.0f} s"
                self._update_command(row)
                if not row.automatic:
                    self.ground_event("WARNING", "commanding", "CMD_TIMEOUT", f"{row.type} {row.id[:8]} not acknowledged")
        for pid, p in list(self.partials.items()):
            if now - p.started > PARTIAL_EXPIRY:
                del self.partials[pid]
                continue
            # Selective repeat: if reception stalls with gaps, request only what is missing.
            if p.last_update and now - p.last_update > NACK_STALL and p.nacks < MAX_GROUND_NACKS:
                missing = [i for i in range(p.total) if i not in p.chunks][:MAX_MISSING_PER_NACK]
                p.nacks += 1
                p.last_update = now
                args: dict[str, Any] = {"image_id": pid, "ok": False, "missing": missing}
                if p.meta is None:
                    args["need_meta"] = True
                self.send_command(CommandType.IMAGE_ACK, args, "ground-auto", automatic=True)

    # --------------------------------------------------------------- receive
    def process_rx(self) -> int:
        n = 0
        for frame in self.link.receive():
            n += 1
            self.stats["rx_frames"] += 1
            try:
                pkt = decode(frame)
            except PacketError as exc:
                key = "rx_crc_errors" if exc.reason == "crc_mismatch" else "rx_other_errors"
                self.stats[key] += 1
                now = self.clock()
                if self._crc_reported_at is None or now - self._crc_reported_at > timedelta(seconds=30):
                    self._crc_reported_at = now
                    self.ground_event("WARNING", "comms", "RX_FRAME_REJECTED", f"downlink frame rejected: {exc.reason}")
                continue
            if pkt.sat_id != SATELLITE_ID:
                self.stats["rx_other_errors"] += 1
                continue
            # (seq, timestamp) identifies a frame even across onboard reboots that reset seq.
            ident = (pkt.seq, pkt.timestamp_ms)
            if ident in self._recent_ids:
                self.stats["rx_duplicates"] += 1
                continue
            self._recent_ids.append(ident)
            self.last_rx_utc = self.clock()
            try:
                self._dispatch(pkt)
            except (PacketError, ValidationError, ValueError) as exc:
                self.stats["rx_other_errors"] += 1
                log.warning("bad %s payload: %s", pkt.msg_type.name, exc)
        return n

    def _dispatch(self, pkt: Packet) -> None:
        t = pkt.msg_type
        if t is MessageType.HOUSEKEEPING:
            hk = Housekeeping.model_validate(decode_json(pkt.payload))
            self._on_housekeeping(hk, pkt.seq)
        elif t is MessageType.EVENT:
            ev = EventMessage.model_validate(decode_json(pkt.payload))
            self._record_event({"utc": ev.utc, "severity": ev.severity.value, "source": ev.source, "code": ev.code, "message": ev.message}, origin="space")
        elif t is MessageType.COMMAND_ACK:
            self._on_ack(CommandAck.model_validate(decode_json(pkt.payload)))
        elif t is MessageType.IMAGE_META:
            self._on_image_meta(ImageMeta.model_validate(decode_json(pkt.payload)))
        elif t is MessageType.IMAGE_CHUNK:
            self._on_chunk(*decode_chunk(pkt.payload))

    def _on_housekeeping(self, hk: Housekeeping, seq: int) -> None:
        d = hk.model_dump(mode="json")
        self.latest_hk = d
        self.telemetry.append(d)
        self._publish("telemetry", d)
        self.persistence.add(
            TelemetryRow(
                utc=hk.utc,
                seq=seq,
                mode=hk.mode.value,
                soc_pct=hk.power.soc_pct,
                battery_v=hk.power.battery_v,
                battery_a=hk.power.battery_a,
                solar_w=hk.power.solar_w,
                load_w=hk.power.load_w,
                cpu_c=hk.thermal.cpu_c,
                payload_c=hk.thermal.payload_c,
                battery_c=hk.thermal.battery_c,
                lat_deg=hk.orbit.lat_deg,
                lon_deg=hk.orbit.lon_deg,
                alt_km=hk.orbit.alt_km,
                sunlit=hk.orbit.sunlit,
                gs_elevation_deg=hk.orbit.gs_elevation_deg,
                simulated=hk.simulated,
                data=d,
            )
        )

    def _on_ack(self, ack: CommandAck) -> None:
        row = self._cmd_rows.get(ack.command_id)
        if row is None:
            log.info("ack for unknown command %s (%s)", ack.command_id, ack.status)
            return
        if row.status in FINAL_STATES and row.status != "TIMEOUT":
            return
        row.status = ack.status.value
        row.reason = ack.reason
        row.ack_utc = ack.utc
        row.detail = ack.detail
        self._update_command(row)

    def _on_image_meta(self, meta: ImageMeta) -> None:
        if meta.image_id in self.images:
            # Retransmission after a lost ACK: we already have it - re-acknowledge.
            self.send_command(CommandType.IMAGE_ACK, {"image_id": meta.image_id, "ok": True}, "ground-auto", automatic=True)
            return
        p = self.partials.setdefault(meta.image_id, Partial(meta.image_id, meta.chunks, self.clock()))
        p.meta, p.total, p.last_update = meta, meta.chunks, self.clock()
        self._try_complete(p)

    def _on_chunk(self, image_id: str, index: int, total: int, data: bytes) -> None:
        if image_id in self.images:
            return
        p = self.partials.setdefault(image_id, Partial(image_id, total, self.clock()))
        p.chunks[index] = data
        p.last_update = self.clock()
        self._try_complete(p)

    def _try_complete(self, p: Partial) -> None:
        if p.meta is None or len(p.chunks) < p.total:
            return
        del self.partials[p.image_id]
        jpeg = b"".join(p.chunks[i] for i in range(p.total) if i in p.chunks)
        ok = len(p.chunks) == p.total and hashlib.sha256(jpeg).hexdigest() == p.meta.sha256
        if not ok:
            self.ground_event("WARNING", "imaging", "IMAGE_CHECKSUM_FAIL", f"image {p.image_id[:8]} failed SHA-256 check - requesting resend")
            self.send_command(CommandType.IMAGE_ACK, {"image_id": p.image_id, "ok": False}, "ground-auto", automatic=True)
            return
        self._store_image(p.meta, jpeg)
        self.send_command(CommandType.IMAGE_ACK, {"image_id": p.image_id, "ok": True}, "ground-auto", automatic=True)

    def _store_image(self, meta: ImageMeta, jpeg: bytes) -> None:
        img = Image.open(io.BytesIO(jpeg))
        img.thumbnail((320, 320))
        tb = io.BytesIO()
        img.convert("RGB").save(tb, format="JPEG", quality=75)
        day = meta.captured_utc.strftime("%Y/%m/%d")
        okey, tkey = f"images/{day}/{meta.image_id}.jpg", f"thumbs/{day}/{meta.image_id}.jpg"
        try:
            self.objects.put(okey, jpeg, "image/jpeg")
            self.objects.put(tkey, tb.getvalue(), "image/jpeg")
        except Exception as exc:  # noqa: BLE001
            # Do not ACK - the satellite will retransmit later.
            self.ground_event("CRITICAL", "storage", "OBJECT_STORE_ERROR", f"cannot store image {meta.image_id[:8]}: {exc}")
            raise ValueError("object store unavailable") from exc
        row = ImageRow(
            id=meta.image_id,
            captured_utc=meta.captured_utc,
            received_utc=self.clock(),
            source=meta.source.value,
            camera=meta.camera,
            width=meta.width,
            height=meta.height,
            size_bytes=meta.size_bytes,
            sha256=meta.sha256,
            verified=True,
            object_key=okey,
            thumb_key=tkey,
            meta=meta.model_dump(mode="json"),
        )
        self.persistence.add(row)
        d = image_to_dict(row)
        self.images[meta.image_id] = d
        while len(self.images) > 500:
            self.images.popitem(last=False)
        self.outbox["images"].append(d)
        self.ground_event("INFO", "imaging", "IMAGE_RECEIVED", f"image {meta.image_id[:8]} received, SHA-256 verified ({meta.size_bytes} B, {meta.source.value})")

    def drain_outbox(self) -> dict[str, list]:
        out, self.outbox = self.outbox, {"events": [], "commands": [], "images": []}
        return out


def event_to_dict(r: EventRow) -> dict:
    return {
        "id": r.id,
        "utc": _iso(r.utc),
        "severity": r.severity,
        "origin": r.origin,
        "source": r.source,
        "code": r.code,
        "message": r.message,
        "acknowledged": bool(r.acknowledged),
        "acknowledged_by": r.acknowledged_by,
    }


def command_to_dict(r: CommandRow) -> dict:
    return {
        "id": r.id,
        "created_utc": _iso(r.created_utc),
        "type": r.type,
        "args": {k: v for k, v in (r.args or {}).items() if k != "confirm"},
        "operator": r.operator,
        "automatic": r.automatic,
        "critical": r.critical,
        "status": r.status,
        "seq": r.seq,
        "reason": r.reason,
        "ack_utc": _iso(r.ack_utc),
        "detail": r.detail or {},
    }


def image_to_dict(r: ImageRow) -> dict:
    return {
        "id": r.id,
        "captured_utc": _iso(r.captured_utc),
        "received_utc": _iso(r.received_utc),
        "source": r.source,
        "camera": r.camera,
        "width": r.width,
        "height": r.height,
        "size_bytes": r.size_bytes,
        "sha256": r.sha256,
        "verified": r.verified,
        "meta": r.meta,
    }
