"""End-to-end flight software <-> link <-> ground segment scenarios.

REQ: FR-OBC-*, FR-SAF-*, FR-TTC-*, FR-CAM-*, NFR-REL-*. Each test maps to a
verification case in docs/verification-plan.md (VC-xx in the docstring).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.config import LinkMode
from app.db import ImageRow, TelemetryRow
from conftest import KEY
from shared import SATELLITE_ID
from shared.protocol import MessageType, Packet, encode, encode_json, sign
from shared.schemas import CommandType
from simulator.communications.channel import Impairments

DONE = {"COMPLETED", "REJECTED", "FAILED", "TIMEOUT"}


def _final(h, cid, max_s=30):
    h.run_until(lambda: h.status(cid)["status"] in DONE, max_s)
    return h.status(cid)


def test_telemetry_continuity(harness):
    """VC-01: housekeeping arrives every period with no gaps under nominal conditions."""
    h = harness
    n0 = len(h.e.ground.telemetry)
    h.run(120)
    hk = list(h.e.ground.telemetry)[n0:]
    assert len(hk) >= 59
    times = [datetime.fromisoformat(d["utc"]) for d in hk]
    gaps = {(b - a).total_seconds() for a, b in zip(times, times[1:], strict=False)}
    assert gaps == {2.0}
    assert all(d["simulated"] for d in hk)


def test_ping_and_capture_downlink_verified(harness):
    """VC-02: capture -> JPEG -> SHA-256 -> chunked downlink -> verified storage."""
    h = harness
    assert _final(h, h.cmd(CommandType.PING))["status"] == "COMPLETED"
    c = _final(h, h.cmd(CommandType.CAPTURE_IMAGE))
    assert c["status"] == "COMPLETED", c
    image_id = c["detail"]["image_id"]
    assert h.run_until(lambda: image_id in h.e.ground.images, 60)
    img = h.e.ground.images[image_id]
    assert img["verified"] and img["source"] == "SIMULATED_ORBITAL"
    assert img["sha256"] == c["detail"]["sha256"]
    assert h.run_until(lambda: len(h.e.fsw.downlink) == 0 and h.mode == "NOMINAL", 30)
    h.e.persistence.flush()
    assert h.e.persistence.query(lambda s: s.get(ImageRow, image_id)) is not None


def _raw_command(h, body: dict, key: bytes = KEY, ts=None, seq=4242) -> bytes:
    ts = ts or int(h.e.world.now.timestamp() * 1000)
    pkt = Packet(SATELLITE_ID, MessageType.COMMAND, seq, ts, encode_json(body))
    return encode(sign(key, pkt))


def _inject(h, frame: bytes) -> None:
    h.e.uplink.send(frame, h.e.sim_t)


def _acks_for(h, cid):
    return [ev for ev in h.e.ground.events if cid[:8] in ev["message"]]


def test_forged_and_replayed_commands_rejected(harness):
    """VC-03: wrong key, replay and stale timestamps are rejected and reported."""
    h = harness
    body = {"schema_version": "1.0.0", "command_id": "forged-1", "type": "PING", "args": {}}
    _inject(h, _raw_command(h, body, key=bytes(32)))
    h.run(3)
    assert "CMD_AUTH_FAIL" in h.event_codes()
    before = h.e.fsw.stats.cmd_accepted
    good = _raw_command(h, {**body, "command_id": "legit-1"})
    _inject(h, good)
    h.run(2)
    assert h.e.fsw.stats.cmd_accepted == before + 1
    _inject(h, good)  # exact replay
    h.run(2)
    assert h.e.fsw.stats.cmd_accepted == before + 1
    stale = _raw_command(h, {**body, "command_id": "stale-1"}, ts=int((h.e.world.now - timedelta(minutes=5)).timestamp() * 1000))
    _inject(h, stale)
    h.run(2)
    assert h.e.fsw.stats.cmd_accepted == before + 1
    msgs = " ".join(ev["message"] for ev in h.e.ground.events)
    assert "bad_signature" in msgs and "replay" in msgs and "stale_timestamp" in msgs


def test_invalid_commands_rejected_with_reason(harness):
    """VC-04: invalid arguments, illegal modes and missing interlocks."""
    h = harness
    cases = [
        (CommandType.SET_MODE, {"mode": "FAULT"}, "mode_not_commandable"),
        (CommandType.SET_MODE, {"mode": "BOGUS"}, "bad_arguments"),
        (CommandType.CAPTURE_IMAGE, {"width": 10}, "bad_arguments"),
        (CommandType.SET_TELEMETRY_RATE, {"period_s": 0.01}, "period_out_of_range"),
        (CommandType.REBOOT, {}, "interlock_confirmation_missing"),
        (CommandType.DELETE_ALL_IMAGES, {"confirm": "REBOOT"}, "interlock_confirmation_missing"),
        (CommandType.SCHEDULE_CAPTURE, {"at_utc": "2020-01-01T00:00:00Z"}, "at_utc_out_of_range"),
    ]
    for ctype, args, reason in cases:
        st = _final(h, h.cmd(ctype, **args))
        assert st["status"] == "REJECTED", (ctype, st)
        assert reason in st["reason"], (ctype, st)
    assert h.mode == "NOMINAL"
    h.cmd(CommandType.SET_MODE, mode="SAFE")
    st = _final(h, h.cmd(CommandType.CAPTURE_IMAGE))
    assert st["status"] == "REJECTED" and "mode_SAFE" in st["reason"]


def test_camera_failure_latches_until_clear_fault(harness):
    """VC-05: repeated camera failures latch CAMERA_FAILURE; CLEAR_FAULT restores imaging."""
    h = harness
    h.e.world.faults.camera_failure = True
    for _ in range(3):
        st = _final(h, h.cmd(CommandType.CAPTURE_IMAGE))
        assert st["status"] == "FAILED"
        h.run(6)  # let IMAGING hold expire
    h.run(2)
    assert "CAMERA_FAILURE" in h.e.ground.latest_hk["faults"]
    h.e.world.faults.camera_failure = False
    st = _final(h, h.cmd(CommandType.CAPTURE_IMAGE))
    assert st["status"] == "REJECTED" and "CAMERA_FAILURE" in st["reason"]
    assert _final(h, h.cmd(CommandType.CLEAR_FAULT, confirm="CLEAR_FAULT"))["status"] == "COMPLETED"
    h.run(2)
    assert _final(h, h.cmd(CommandType.CAPTURE_IMAGE))["status"] == "COMPLETED"


def test_power_loss_enters_safe_and_recovery_is_interlocked(harness):
    """VC-06: battery drain -> autonomous SAFE; NOMINAL refused until SoC recovers."""
    h = harness
    h.e.world.faults.battery_drain_w = 30
    assert h.run_until(lambda: h.mode == "SAFE", 3000, scale=20)
    assert any(c.startswith("FAULT_LOW_BATTERY") for c in h.event_codes())
    h.e.world.faults.battery_drain_w = 0
    h.e.time_scale = 1
    st = _final(h, h.cmd(CommandType.SET_MODE, mode="NOMINAL"))
    assert st["status"] == "REJECTED" and "soc_below_recovery" in st["reason"]
    h.e.world.power.soc_pct = 60.0  # bench: battery recharged
    h.run(3)
    assert _final(h, h.cmd(CommandType.SET_MODE, mode="NOMINAL"))["status"] == "COMPLETED"


def test_payload_overtemperature_enters_safe(harness):
    """VC-07: thermal limit violation -> SAFE."""
    h = harness
    h.e.world.faults.payload_heater_w = 10
    assert h.run_until(lambda: h.mode == "SAFE", 3000, scale=10)
    assert "FAULT_PAYLOAD_OVERTEMP" in h.event_codes()


def test_watchdog_recovery(harness):
    """VC-08: hung flight software is reset by the watchdog and boots conservatively into SAFE."""
    h = harness
    boots = h.e.fsw.boot_count
    h.e.world.faults.fsw_hang = True
    assert h.run_until(lambda: "WATCHDOG_RESET" in h.event_codes(), 30)
    assert h.e.fsw.boot_count == boots + 1
    assert not h.e.world.faults.fsw_hang
    assert h.run_until(lambda: h.mode == "SAFE", 15)
    assert h.e.ground.latest_hk["boot_count"] == boots + 1


def test_watchdog_storm_enters_fault_then_clear(harness):
    """VC-09: repeated watchdog resets -> FAULT; CLEAR_FAULT -> SAFE."""
    h = harness
    for _ in range(3):
        h.e.world.faults.fsw_hang = True
        h.run_until(lambda: not h.e.world.faults.fsw_hang, 30)
        h.run(8)
    assert h.mode == "FAULT"
    assert _final(h, h.cmd(CommandType.SET_MODE, mode="NOMINAL"))["status"] == "REJECTED"
    assert _final(h, h.cmd(CommandType.CLEAR_FAULT, confirm="CLEAR_FAULT"))["status"] == "COMPLETED"
    h.run(2)
    assert h.mode == "SAFE"


def test_storage_exhaustion_inhibits_imaging(harness):
    """VC-10: storage nearly full -> STORAGE_FULL fault and capture refused."""
    h = harness
    h.e.set_storage_fill(True)
    h.run(3)
    assert "STORAGE_FULL" in h.e.ground.latest_hk["faults"]
    st = _final(h, h.cmd(CommandType.CAPTURE_IMAGE))
    assert st["status"] == "REJECTED" and "STORAGE_FULL" in st["reason"]
    h.e.set_storage_fill(False)
    h.run(3)
    assert _final(h, h.cmd(CommandType.CAPTURE_IMAGE))["status"] == "COMPLETED"


def test_network_disconnection_and_recovery(harness):
    """VC-11: link loss -> command timeout + telemetry gap; recovery resumes and drains the queue."""
    h = harness
    at = (h.e.world.now + timedelta(seconds=20)).isoformat()
    sched = h.cmd(CommandType.SCHEDULE_CAPTURE, at_utc=at)
    h.run(2)
    assert h.status(sched)["status"] == "ACCEPTED"
    h.e.world.faults.link_down = True
    h.run(2)
    n_before = len(h.e.ground.telemetry)
    cid = h.cmd(CommandType.PING)
    h.run(70)
    assert h.status(cid)["status"] == "TIMEOUT"
    assert len(h.e.ground.telemetry) == n_before
    assert "LINK_DOWN" in h.event_codes()
    assert len(h.e.fsw.downlink) == 1  # captured during the outage, waiting
    h.e.world.faults.link_down = False
    assert h.run_until(lambda: len(h.e.ground.images) == 1, 60)
    assert h.run_until(lambda: len(h.e.ground.telemetry) > n_before, 5)


def test_packet_loss_corruption_duplication(harness):
    """VC-12: 10% loss, 5% corruption, 10% duplication, 0.5 s delay - image still verified."""
    h = harness
    h.e.set_impairments(Impairments(loss=0.10, duplicate=0.10, corrupt=0.05, delay_s=0.5))
    h.e.fsw.camera_cfg.width, h.e.fsw.camera_cfg.height = 640, 480
    image_id = None
    for _ in range(6):  # operators re-send commands that are lost on the uplink
        st = _final(h, h.cmd(CommandType.CAPTURE_IMAGE), 70)
        if st["status"] == "COMPLETED":
            image_id = st["detail"]["image_id"]
            break
        h.run(6)
    if image_id is None:  # command ACK lost but capture happened: take whatever is queued
        h.run_until(lambda: len(h.e.fsw.downlink) or len(h.e.ground.images), 30)
        image_id = (h.e.fsw.downlink.ids() or list(h.e.ground.images))[0]
    assert h.run_until(lambda: image_id in h.e.ground.images, 600)
    assert h.e.ground.images[image_id]["verified"]
    gs = h.e.ground.stats
    assert gs["rx_crc_errors"] > 0 and gs["rx_duplicates"] > 0
    assert h.e.downlink.stats.dropped > 0


def test_database_outage_buffers_and_backfills(harness):
    """VC-13: DB outage -> buffered writes + degraded reads; restore -> no telemetry lost."""
    h = harness
    h.run(4)
    h.e.persistence.simulate_outage = True
    h.run(30)
    assert not h.e.persistence.db_ok and h.e.persistence.pending > 10
    assert "DB_OUTAGE" in h.event_codes()
    h.e.persistence.simulate_outage = False
    h.run(3)
    assert h.e.persistence.db_ok and h.e.persistence.pending == 0
    assert "DB_RESTORED" in h.event_codes()
    stored = h.e.persistence.query(lambda s: s.scalar(select(func.count()).select_from(TelemetryRow)))
    assert stored == len(h.e.ground.telemetry)


def test_orbital_link_mode_follows_visibility(harness):
    """VC-14: in orbital link mode telemetry flows only while the ground station sees the satellite."""
    h = harness
    h.e.link_mode = LinkMode.ORBITAL
    h.run(2)
    if not h.e.world.gs_visible:
        n = len(h.e.ground.telemetry)
        h.run(20)
        assert len(h.e.ground.telemetry) == n
    assert h.run_until(lambda: h.e.world.gs_visible, 1200)
    n = len(h.e.ground.telemetry)
    h.run(10)
    assert len(h.e.ground.telemetry) > n
    assert "AOS" in h.event_codes()


def test_commanded_reboot_requeues_unacked_images(harness):
    """VC-15: REBOOT preserves non-volatile storage and re-queues un-acknowledged images."""
    h = harness
    h.e.fsw.cfg.auto_downlink = False  # keep the image onboard until commanded
    assert _final(h, h.cmd(CommandType.CAPTURE_IMAGE))["status"] == "COMPLETED"
    h.run(8)
    assert len(h.e.fsw.downlink) == 1 and not h.e.ground.images
    boots = h.e.fsw.boot_count
    st = _final(h, h.cmd(CommandType.REBOOT, confirm="REBOOT"))
    assert st["status"] == "COMPLETED"
    assert h.e.fsw.boot_count == boots + 1 and len(h.e.fsw.downlink) == 1
    assert h.run_until(lambda: h.mode == "NOMINAL", 10)
    assert _final(h, h.cmd(CommandType.START_DOWNLINK))["status"] == "COMPLETED"
    assert h.run_until(lambda: len(h.e.ground.images) == 1, 60)
