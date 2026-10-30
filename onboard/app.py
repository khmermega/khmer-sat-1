"""KHMER-SAT 1 prototype flight application.

Single-threaded, tick-driven (call ``tick(now)`` at ~1 Hz). The same class runs
against simulated adapters (ground-station simulation engine) or hardware
adapters (Raspberry Pi bench build) - only the HAL differs.

Responsibilities: startup & hardware init, telemetry acquisition, command
handling (authenticated, anti-replay, interlocked), camera operation, storage,
image downlink, FDIR / safe-mode transitions, watchdog heartbeat, logging.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from pydantic import ValidationError

from onboard.camera.base import Camera, CameraConfig, CameraError
from onboard.camera.pipeline import process
from onboard.camera.scheduler import CaptureScheduler
from onboard.communications.link import Link
from onboard.communications.transfer import DownlinkQueue, TransferState
from onboard.config import OnboardConfig
from onboard.power.interfaces import Eps
from onboard.safety.fdir import Action, Fault, FaultCode, HealthSnapshot, evaluate
from onboard.safety.modes import COMMANDABLE, ModeManager, Transition, TransitionError
from onboard.safety.watchdog import WatchdogMCU
from onboard.scheduler.scheduler import TaskScheduler
from onboard.sensors.interfaces import AttitudeSource, Gnss, Imu, Magnetometer, TemperatureSensors
from onboard.storage.manager import StorageFullError, StorageManager
from shared.protocol import (
    AuthError,
    MessageType,
    Packet,
    PacketError,
    ReplayGuard,
    decode,
    decode_json,
    encode,
    encode_chunk,
    encode_json,
    verify,
)
from shared.schemas import (
    AckStatus,
    AttitudeState,
    CommandAck,
    CommandBody,
    CommandType,
    EventMessage,
    GnssState,
    Housekeeping,
    Mode,
    OrbitState,
    PowerState,
    Severity,
    StorageState,
    ThermalState,
)

log = logging.getLogger("onboard.app")

MAX_SCHEDULE_AHEAD = timedelta(days=7)
WATCHDOG_STORM_COUNT = 3  # resets within the window below -> boot into FAULT
WATCHDOG_STORM_WINDOW_S = 3600.0
TASK_ERROR_FAULT_THRESHOLD = 5


class NavigationSource(Protocol):
    def read(self) -> OrbitState: ...


@dataclass
class Hal:
    """Hardware abstraction layer bundle injected into the flight application."""

    imu: Imu
    mag: Magnetometer
    gnss: Gnss
    temps: TemperatureSensors
    attitude: AttitudeSource
    eps: Eps
    camera: Camera
    watchdog: WatchdogMCU
    navigation: NavigationSource
    link_up: Callable[[], bool] = lambda: True
    cpu_load: Callable[[], float] = lambda: 0.0


class CommandRejected(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class FswStats:
    rx_frames: int = 0
    rx_bad: int = 0
    cmd_accepted: int = 0
    cmd_rejected: int = 0
    tx_frames: int = 0
    images_captured: int = 0
    task_errors: dict[str, int] = field(default_factory=dict)


class FlightSoftware:
    def __init__(
        self,
        hal: Hal,
        link: Link,
        storage: StorageManager,
        key: bytes,
        cfg: OnboardConfig | None = None,
        simulated: bool = True,
    ) -> None:
        self.hal, self.link, self.storage, self._key = hal, link, storage, key
        self.cfg = cfg or OnboardConfig()
        self.simulated = simulated
        self.modes = ModeManager(on_change=self._on_mode_change)
        self.replay = ReplayGuard(window_ms=int(self.cfg.replay_window_s * 1000))
        self.camera_cfg = CameraConfig(self.cfg.camera_width, self.cfg.camera_height, self.cfg.jpeg_quality)
        self.captures = CaptureScheduler()
        self.downlink = DownlinkQueue(self.cfg.transfer_ack_timeout_s, self.cfg.transfer_max_retries)
        self.tasks = TaskScheduler()
        self.tasks.add("housekeeping", self.cfg.telemetry_period_s, self._task_housekeeping)
        self.tasks.add("fdir", 1.0, self._task_fdir)
        self.stats = FswStats()
        self._seq = 0
        self._epoch: datetime | None = None
        self._boot_t = 0.0
        self._now = datetime.now(UTC)
        self.camera_failures = 0
        self.latched: set[FaultCode] = set()
        self.active_faults: dict[FaultCode, Fault] = {}
        self._imaging_until: float | None = None
        self._last_cmd_seq: int | None = None
        self._boot_reason = "POWER_ON"
        self._rx_bad_reported_at = -1e9

    # ------------------------------------------------------------------ time
    def _t(self, now: datetime) -> float:
        """Monotonic seconds since the application object was created."""
        if self._epoch is None:
            self._epoch = now
        return (now - self._epoch).total_seconds()

    @property
    def mode(self) -> Mode:
        return self.modes.mode

    # --------------------------------------------------------------- startup
    def boot(self, now: datetime, reason: str = "POWER_ON") -> None:
        """Startup sequence: persistent state, hardware init, rebuild queues."""
        self._now = now
        t = self._t(now)
        state = self.storage.load_state()
        state["boot_count"] = int(state.get("boot_count", 0)) + 1
        resets = [r for r in state.get("watchdog_resets", []) if now.timestamp() - r < WATCHDOG_STORM_WINDOW_S]
        if reason == "WATCHDOG":
            resets.append(now.timestamp())
        state["watchdog_resets"] = resets
        self.storage.save_state(state)
        self.boot_count = state["boot_count"]
        self._boot_reason = reason
        self._boot_t = t
        if self.mode is not Mode.BOOT:
            self.modes.reset(reason, now)
        self.tasks.reset()
        self.replay = ReplayGuard(window_ms=int(self.cfg.replay_window_s * 1000))
        self._imaging_until = None
        self.captures.clear()
        self.active_faults.clear()
        sev = Severity.WARNING if reason != "POWER_ON" else Severity.INFO
        self.emit_event(sev, "obc", "BOOT", f"boot #{self.boot_count} reason={reason}")
        try:
            self.hal.camera.open()
        except CameraError as exc:
            self.camera_failures = self.cfg.camera_max_consecutive_failures
            self.emit_event(Severity.WARNING, "camera", "CAMERA_INIT_FAIL", str(exc))
        self._rebuild_downlink_queue()
        self.hal.watchdog.kick(t)

    def reset(self, now: datetime, reason: str) -> None:
        """Processor reset (commanded REBOOT or watchdog). Volatile state is lost."""
        log.warning("reset", extra={"fields": {"reason": reason}})
        self.boot(now, reason)

    def _rebuild_downlink_queue(self) -> None:
        acked = set(self.storage.load_state().get("acked_images", []))
        self.downlink = DownlinkQueue(self.cfg.transfer_ack_timeout_s, self.cfg.transfer_max_retries)
        for meta in self.storage.list_images():
            if meta.image_id not in acked:
                self.downlink.enqueue(meta.image_id, meta.chunks)

    def _finish_boot(self, now: datetime) -> None:
        state = self.storage.load_state()
        if len(state.get("watchdog_resets", [])) >= WATCHDOG_STORM_COUNT:
            self.modes.transition(Mode.FAULT, "repeated watchdog resets", now)
            return
        faults = self._evaluate_faults()
        if self._boot_reason == "WATCHDOG" or any(f.action is Action.ENTER_SAFE for f in faults):
            self.modes.transition(Mode.SAFE, f"boot after {self._boot_reason}; conservative entry", now)
        else:
            self.modes.transition(Mode.NOMINAL, "boot complete", now)

    # ------------------------------------------------------------------ tick
    def tick(self, now: datetime) -> None:
        """One iteration of the main loop. Must be called at >= 1 Hz."""
        self._now = now
        t = self._t(now)
        self.hal.watchdog.kick(t)
        if self.mode is Mode.BOOT and t - self._boot_t >= self.cfg.boot_duration_s:
            self._finish_boot(now)
        self._process_uplink(now)
        self.tasks.run_due(t)
        self._escalate_task_errors(now)
        self._service_scheduled_captures(now)
        self._service_imaging_hold(now, t)
        self._service_downlink(now, t)

    # ------------------------------------------------------------ messaging
    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        return self._seq

    def _send(self, msg_type: MessageType, payload: bytes) -> None:
        pkt = Packet(self.cfg.sat_id, msg_type, self._next_seq(), int(self._now.timestamp() * 1000), payload)
        self.link.send(encode(pkt))
        self.stats.tx_frames += 1

    def emit_event(self, severity: Severity, source: str, code: str, message: str) -> None:
        ev = EventMessage(utc=self._now, severity=severity, source=source, code=code, message=message)
        log.log(
            logging.WARNING if severity is not Severity.INFO else logging.INFO,
            message,
            extra={"fields": {"code": code, "source": source, "severity": severity.value}},
        )
        self._send(MessageType.EVENT, encode_json(ev.model_dump(mode="json")))

    def _ack(self, command_id: str, status: AckStatus, reason: str = "", **detail: Any) -> None:
        ack = CommandAck(command_id=command_id, status=status, reason=reason, utc=self._now, detail=detail)
        self._send(MessageType.COMMAND_ACK, encode_json(ack.model_dump(mode="json")))

    def _on_mode_change(self, tr: Transition) -> None:
        sev = Severity.WARNING if tr.to_mode in (Mode.SAFE, Mode.FAULT) else Severity.INFO
        self.emit_event(sev, "modes", "MODE_CHANGE", f"{tr.from_mode.value} -> {tr.to_mode.value}: {tr.reason}")

    # --------------------------------------------------------------- uplink
    def _process_uplink(self, now: datetime) -> None:
        for frame in self.link.receive():
            self.stats.rx_frames += 1
            try:
                pkt = decode(frame)
            except PacketError as exc:
                self.stats.rx_bad += 1
                t = self._t(now)
                if t - self._rx_bad_reported_at > 10:  # rate-limit event flood
                    self._rx_bad_reported_at = t
                    self.emit_event(Severity.WARNING, "comms", "RX_FRAME_REJECTED", f"uplink frame rejected: {exc.reason}")
                continue
            if pkt.sat_id != self.cfg.sat_id or pkt.msg_type is not MessageType.COMMAND:
                self.stats.rx_bad += 1
                continue
            self._handle_command_packet(pkt, now)

    def _handle_command_packet(self, pkt: Packet, now: datetime) -> None:
        try:
            raw = decode_json(pkt.payload)
        except PacketError:
            raw = {}
        cmd_id = str(raw.get("command_id", "unknown"))[:64]
        try:
            verify(self._key, pkt)
            self.replay.check_and_record(pkt, int(now.timestamp() * 1000))
        except AuthError as exc:
            self.stats.cmd_rejected += 1
            self.emit_event(Severity.WARNING, "commanding", "CMD_AUTH_FAIL", f"command {cmd_id} rejected: {exc.reason}")
            self._ack(cmd_id, AckStatus.REJECTED, exc.reason)
            return
        try:
            body = CommandBody.model_validate(raw)
        except ValidationError as exc:
            self.stats.cmd_rejected += 1
            self._ack(cmd_id, AckStatus.REJECTED, "invalid_body", errors=exc.error_count())
            return
        self._last_cmd_seq = pkt.seq
        self.execute(body, now)

    # ------------------------------------------------------------- commands
    def execute(self, cmd: CommandBody, now: datetime) -> None:
        """Validate interlocks and run a command. Always produces an ACK."""
        handler = getattr(self, f"_cmd_{cmd.type.value.lower()}", None)
        try:
            if self.mode is Mode.BOOT and cmd.type is not CommandType.PING:
                raise CommandRejected("booting")
            if handler is None:
                raise CommandRejected("unsupported_command")
            result = handler(cmd, now)
            self.stats.cmd_accepted += 1
            if result is None:  # handler already acknowledged (e.g. REBOOT)
                return
            status = result.pop("_status", AckStatus.COMPLETED)
            if cmd.type is not CommandType.IMAGE_ACK:
                self._ack(cmd.command_id, status, **result)
        except CommandRejected as exc:
            self.stats.cmd_rejected += 1
            self._ack(cmd.command_id, AckStatus.REJECTED, exc.reason)
        except (ValueError, TypeError, KeyError) as exc:
            self.stats.cmd_rejected += 1
            self._ack(cmd.command_id, AckStatus.REJECTED, f"bad_arguments: {exc}")

    def _require_critical_confirm(self, cmd: CommandBody) -> None:
        # Onboard half of the two-layer interlock: the ground must echo the
        # command type as confirmation (added only after ARM/EXECUTE on ground).
        if cmd.args.get("confirm") != cmd.type.value:
            raise CommandRejected("interlock_confirmation_missing")

    def imaging_inhibit_reason(self) -> str | None:
        if self.mode not in (Mode.NOMINAL, Mode.IMAGING):
            return f"mode_{self.mode.value}"
        p = self.hal.eps.read()
        if p.soc_pct < self.cfg.imaging_min_soc_pct:
            return "battery_below_imaging_threshold"
        inhibit = [f.code for f in self.active_faults.values() if f.action is not Action.NONE]
        inhibit += list(self.latched)
        if inhibit:
            return f"fault_{inhibit[0].value}"
        return None

    def _cmd_ping(self, cmd: CommandBody, now: datetime) -> dict:
        return {"pong": True, "mode": self.mode.value}

    def _cmd_set_mode(self, cmd: CommandBody, now: datetime) -> dict:
        target = Mode(str(cmd.args.get("mode", "")))
        if target not in COMMANDABLE:
            raise CommandRejected(f"mode_not_commandable_{target.value}")
        p = self.hal.eps.read()
        if target is Mode.NOMINAL and self.mode is Mode.SAFE:
            if p.soc_pct < self.cfg.recover_soc_pct:
                raise CommandRejected("interlock_soc_below_recovery_threshold")
            if any(f.action is Action.ENTER_SAFE for f in self.active_faults.values()):
                raise CommandRejected("interlock_active_safe_fault")
        if target is Mode.IMAGING and (why := self.imaging_inhibit_reason()):
            raise CommandRejected(f"interlock_{why}")
        if target is Mode.DOWNLINK and p.soc_pct < self.cfg.downlink_min_soc_pct:
            raise CommandRejected("interlock_soc_below_downlink_threshold")
        try:
            self.modes.transition(target, f"command {cmd.command_id}", now)
        except TransitionError as exc:
            raise CommandRejected(exc.reason) from exc
        self._imaging_until = None
        return {"mode": target.value}

    def _cmd_capture_image(self, cmd: CommandBody, now: datetime) -> dict:
        cfg = self._camera_cfg_from(cmd.args)
        return self._capture(cmd.command_id, cfg, now)

    def _camera_cfg_from(self, args: dict) -> CameraConfig:
        cfg = CameraConfig(
            int(args.get("width", self.camera_cfg.width)),
            int(args.get("height", self.camera_cfg.height)),
            int(args.get("jpeg_quality", self.camera_cfg.jpeg_quality)),
        )
        cfg.validate()
        return cfg

    def _capture(self, command_id: str, cfg: CameraConfig, now: datetime) -> dict:
        if why := self.imaging_inhibit_reason():
            raise CommandRejected(f"interlock_{why}")
        if self.mode is Mode.NOMINAL:
            self.modes.transition(Mode.IMAGING, f"capture {command_id}", now)
            self._imaging_until = self._t(now) + self.cfg.imaging_hold_s
        nav = self.hal.navigation.read()
        gnss = self.hal.gnss.read()
        pos = (gnss.lat_deg, gnss.lon_deg, gnss.alt_km) if gnss.fix else (None, None, None)
        try:
            frame = self.hal.camera.capture(cfg)
        except CameraError as exc:
            self.camera_failures += 1
            self.emit_event(Severity.WARNING, "camera", "CAPTURE_FAILED", f"{exc} ({self.camera_failures} consecutive)")
            return {"_status": AckStatus.FAILED, "error": str(exc)}
        self.camera_failures = 0
        img = process(frame, cfg, now, self.cfg.chunk_size, pos, self.mode)
        try:
            self.storage.save_image(img.meta, img.jpeg, img.thumbnail)
        except StorageFullError as exc:
            self.emit_event(Severity.WARNING, "storage", "STORAGE_FULL", str(exc))
            return {"_status": AckStatus.FAILED, "error": "storage_full"}
        self.stats.images_captured += 1
        self.downlink.enqueue(img.meta.image_id, img.meta.chunks)
        self.emit_event(
            Severity.INFO,
            "camera",
            "IMAGE_CAPTURED",
            f"{img.meta.image_id[:8]} {img.meta.width}x{img.meta.height} {img.meta.size_bytes} B {img.meta.source.value}"
            + ("" if nav.sunlit else " (eclipse)"),
        )
        return {"image_id": img.meta.image_id, "sha256": img.meta.sha256, "size_bytes": img.meta.size_bytes}

    def _cmd_schedule_capture(self, cmd: CommandBody, now: datetime) -> dict:
        at = datetime.fromisoformat(str(cmd.args["at_utc"]).replace("Z", "+00:00"))
        if at.tzinfo is None:
            raise CommandRejected("at_utc_must_include_timezone")
        if not now <= at <= now + MAX_SCHEDULE_AHEAD:
            raise CommandRejected("at_utc_out_of_range")
        cfg = self._camera_cfg_from(cmd.args)
        self.captures.add(at, cmd.command_id, width=cfg.width, height=cfg.height, jpeg_quality=cfg.jpeg_quality)
        return {"_status": AckStatus.ACCEPTED, "scheduled_for": at.astimezone(UTC).isoformat()}

    def _cmd_set_camera_config(self, cmd: CommandBody, now: datetime) -> dict:
        self.camera_cfg = self._camera_cfg_from(cmd.args)
        return {"width": self.camera_cfg.width, "height": self.camera_cfg.height, "jpeg_quality": self.camera_cfg.jpeg_quality}

    def _cmd_start_downlink(self, cmd: CommandBody, now: datetime) -> dict:
        if not len(self.downlink):
            return {"queue": 0}
        if not self.hal.link_up():
            raise CommandRejected("link_not_available")
        if self.mode is not Mode.DOWNLINK:
            self._cmd_set_mode(CommandBody(command_id=cmd.command_id, type=CommandType.SET_MODE, args={"mode": "DOWNLINK"}), now)
        return {"queue": len(self.downlink)}

    def _cmd_set_telemetry_rate(self, cmd: CommandBody, now: datetime) -> dict:
        period = float(cmd.args["period_s"])
        if not 0.5 <= period <= 60:
            raise CommandRejected("period_out_of_range_0.5_60")
        self.tasks.set_period("housekeeping", period)
        return {"period_s": period}

    def _cmd_clear_fault(self, cmd: CommandBody, now: datetime) -> dict:
        self._require_critical_confirm(cmd)
        cleared = sorted(c.value for c in self.latched)
        self.latched.clear()
        self.camera_failures = 0
        state = self.storage.load_state()
        state["watchdog_resets"] = []
        self.storage.save_state(state)
        for name in self.stats.task_errors:
            self.tasks.tasks[name].errors = 0
        self.stats.task_errors.clear()
        if self.mode is Mode.FAULT:
            self.modes.transition(Mode.SAFE, f"CLEAR_FAULT {cmd.command_id}", now)
        return {"cleared": cleared}

    def _cmd_reboot(self, cmd: CommandBody, now: datetime) -> None:
        self._require_critical_confirm(cmd)
        self._ack(cmd.command_id, AckStatus.COMPLETED, "rebooting")
        self.reset(now, "COMMANDED_REBOOT")

    def _cmd_delete_all_images(self, cmd: CommandBody, now: datetime) -> dict:
        self._require_critical_confirm(cmd)
        if self.mode not in (Mode.NOMINAL, Mode.SAFE):
            raise CommandRejected(f"interlock_mode_{self.mode.value}")
        n = self.storage.delete_all_images()
        self.downlink = DownlinkQueue(self.cfg.transfer_ack_timeout_s, self.cfg.transfer_max_retries)
        if self.mode is Mode.DOWNLINK:
            self.modes.transition(Mode.NOMINAL, "queue cleared", now)
        self.emit_event(Severity.WARNING, "storage", "IMAGES_DELETED", f"{n} images deleted by command")
        return {"deleted": n}

    def _cmd_image_ack(self, cmd: CommandBody, now: datetime) -> dict:
        image_id = str(cmd.args["image_id"])
        if cmd.args.get("ok", False):
            if self.downlink.ack(image_id):
                state = self.storage.load_state()
                acked = state.get("acked_images", [])
                acked.append(image_id)
                state["acked_images"] = acked[-5000:]
                self.storage.save_state(state)
        else:
            missing = cmd.args.get("missing")
            if missing is not None:
                missing = [int(i) for i in missing][:1000]
            self.downlink.nack(image_id, missing, bool(cmd.args.get("need_meta", False)))
        return {}

    # ---------------------------------------------------------- periodic work
    def _evaluate_faults(self) -> list[Fault]:
        p = self.hal.eps.read()
        tm = self.hal.temps.read()
        g = self.hal.gnss.read()
        snap = HealthSnapshot(
            soc_pct=p.soc_pct,
            battery_c=tm.battery_c,
            payload_c=tm.payload_c,
            cpu_c=tm.cpu_c,
            storage_free_bytes=self.storage.free_bytes(),
            camera_failures=self.camera_failures,
            gnss_fix=g.fix,
        )
        return evaluate(snap, self.cfg)

    def _task_fdir(self, t: float) -> None:
        now = self._now
        faults = {f.code: f for f in self._evaluate_faults()}
        for code, f in faults.items():
            if code not in self.active_faults:
                sev = Severity.CRITICAL if f.action is Action.ENTER_SAFE else Severity.WARNING
                if f.action is Action.NONE:
                    sev = Severity.INFO
                self.emit_event(sev, "fdir", f"FAULT_{code.value}", f.detail)
                if code is FaultCode.CAMERA_FAILURE:
                    self.latched.add(code)  # latched until CLEAR_FAULT
        for code in set(self.active_faults) - set(faults):
            self.emit_event(Severity.INFO, "fdir", f"CLEARED_{code.value}", f"{code.value} no longer active")
        self.active_faults = faults
        if self.mode in (Mode.BOOT, Mode.SAFE, Mode.FAULT):
            return
        safe = [f for f in faults.values() if f.action is Action.ENTER_SAFE]
        if safe:
            self.modes.transition(Mode.SAFE, f"FDIR: {safe[0].code.value} ({safe[0].detail})", now)
            self._imaging_until = None
        elif self.mode is Mode.IMAGING and self.imaging_inhibit_reason():
            self.modes.transition(Mode.NOMINAL, f"FDIR: imaging inhibited ({self.imaging_inhibit_reason()})", now)

    def _escalate_task_errors(self, now: datetime) -> None:
        for name, task in self.tasks.tasks.items():
            self.stats.task_errors[name] = task.errors
            if task.errors >= TASK_ERROR_FAULT_THRESHOLD and self.mode is not Mode.FAULT and self.mode is not Mode.BOOT:
                self.modes.transition(Mode.FAULT, f"task {name} failed {task.errors}x: {task.last_error}", now)

    def _service_scheduled_captures(self, now: datetime) -> None:
        for sc in self.captures.due(now):
            cfg = CameraConfig(sc.width or self.camera_cfg.width, sc.height or self.camera_cfg.height, sc.jpeg_quality or self.camera_cfg.jpeg_quality)
            try:
                res = self._capture(sc.command_id, cfg, now)
                status = res.pop("_status", AckStatus.COMPLETED)
                self._ack(sc.command_id, status, "scheduled capture", **res)
            except CommandRejected as exc:
                self._ack(sc.command_id, AckStatus.FAILED, f"scheduled capture skipped: {exc.reason}")

    def _service_imaging_hold(self, now: datetime, t: float) -> None:
        if self._imaging_until is not None and t >= self._imaging_until:
            self._imaging_until = None
            if self.mode is Mode.IMAGING:
                self.modes.transition(Mode.NOMINAL, "imaging complete", now)

    def _service_downlink(self, now: datetime, t: float) -> None:
        res = self.downlink.check_timeouts(t)
        for image_id in res.abandoned:
            self.emit_event(Severity.WARNING, "comms", "TRANSFER_ABANDONED", f"image {image_id[:8]} not acknowledged after retries")
        link_up = self.hal.link_up()
        if (
            self.cfg.auto_downlink
            and self.mode is Mode.NOMINAL
            and len(self.downlink)
            and link_up
            and self.hal.eps.read().soc_pct >= self.cfg.downlink_min_soc_pct
        ):
            self.modes.transition(Mode.DOWNLINK, "auto downlink: link available and images queued", now)
        if self.mode is not Mode.DOWNLINK:
            return
        if not len(self.downlink) or not link_up:
            self.modes.transition(Mode.NOMINAL, "downlink complete" if link_up else "link lost", now)
            return
        tr = self.downlink.active()
        assert tr is not None
        if tr.state is TransferState.AWAIT_ACK:
            return
        try:
            meta, jpeg = self.storage.load_image(tr.image_id)
        except (FileNotFoundError, ValueError):
            self.downlink.ack(tr.image_id)  # missing on disk - drop from queue
            self.emit_event(Severity.WARNING, "storage", "IMAGE_MISSING", f"queued image {tr.image_id[:8]} missing")
            return
        if not tr.meta_sent:
            self._send(MessageType.IMAGE_META, encode_json(meta.model_dump(mode="json")))
            tr.meta_sent, tr.state = True, TransferState.SENDING
        cs = self.cfg.chunk_size
        selective = bool(tr.resend)
        done = False
        for _ in range(self.cfg.chunks_per_tick):
            i = tr.next_index()
            if i is None:
                done = True
                break
            self._send(MessageType.IMAGE_CHUNK, encode_chunk(tr.image_id, i, tr.total_chunks, jpeg[i * cs : (i + 1) * cs]))
        if done or (not tr.resend and tr.next_chunk >= tr.total_chunks):
            tr.state, tr.sent_at = TransferState.AWAIT_ACK, t
            if not selective:
                tr.attempts += 1

    def _task_housekeeping(self, t: float) -> None:
        self._send(MessageType.HOUSEKEEPING, encode_json(self.housekeeping().model_dump(mode="json")))

    def housekeeping(self) -> Housekeeping:
        p = self.hal.eps.read()
        tm = self.hal.temps.read()
        g = self.hal.gnss.read()
        return Housekeeping(
            utc=self._now,
            mode=self.mode,
            uptime_s=round(self._t(self._now) - self._boot_t, 1),
            boot_count=getattr(self, "boot_count", 0),
            cpu_load_pct=round(self.hal.cpu_load(), 1),
            orbit=self.hal.navigation.read(),
            power=PowerState(
                soc_pct=round(p.soc_pct, 2),
                battery_v=round(p.battery_v, 3),
                battery_a=round(p.battery_a, 3),
                solar_w=round(p.solar_w, 2),
                load_w=round(p.load_w, 2),
            ),
            thermal=ThermalState(
                cpu_c=round(tm.cpu_c, 2), payload_c=round(tm.payload_c, 2), battery_c=round(tm.battery_c, 2), panel_c=round(tm.panel_c, 2)
            ),
            attitude=AttitudeState(
                q=[round(x, 5) for x in self.hal.attitude.read_q()],
                rate_dps=[round(x, 3) for x in self.hal.imu.read_rate_dps()],
                mag_ut=[round(x, 2) for x in self.hal.mag.read_ut()],
            ),
            gnss=GnssState(fix=g.fix, sats=g.sats, lat_deg=g.lat_deg, lon_deg=g.lon_deg, alt_km=g.alt_km),
            storage=StorageState(
                used_bytes=self.storage.used_bytes(),
                capacity_bytes=self.storage.capacity_bytes,
                images_stored=len(self.storage.list_images()),
                downlink_queue=len(self.downlink),
            ),
            faults=sorted({c.value for c in self.active_faults} | {c.value for c in self.latched}),
            last_cmd_seq=self._last_cmd_seq,
            simulated=self.simulated,
        )
