"""REQ: FR-OBC-002, FR-CAM-001..007, FR-STO-001..003, FR-SAF-001..004."""

import hashlib
import io
import socket
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image

from onboard.camera.base import CameraConfig, CameraError
from onboard.camera.mock import MockCamera
from onboard.camera.pipeline import process
from onboard.camera.scheduler import CaptureScheduler
from onboard.communications.tcp import TcpFrameLink
from onboard.communications.transfer import DownlinkQueue, TransferState
from onboard.config import OnboardConfig
from onboard.safety.fdir import Action, FaultCode, HealthSnapshot, evaluate
from onboard.safety.modes import ModeManager, TransitionError
from onboard.safety.watchdog import SimWatchdogMCU
from onboard.scheduler.scheduler import TaskScheduler
from onboard.sensors.interfaces import SensorError
from onboard.sensors.nmea import parse_gga
from onboard.storage.manager import StorageFullError, StorageManager
from shared.schemas import ImageSource, Mode

NOW = datetime(2026, 10, 30, 3, 0, tzinfo=UTC)


# ---------------------------------------------------------------- modes
def test_mode_machine_allowed_and_illegal():
    m = ModeManager()
    assert m.mode is Mode.BOOT
    m.transition(Mode.NOMINAL, "boot", NOW)
    m.transition(Mode.IMAGING, "cmd", NOW)
    with pytest.raises(TransitionError, match="illegal"):
        m.transition(Mode.DOWNLINK, "cmd", NOW)  # IMAGING -> DOWNLINK not allowed
    m.transition(Mode.SAFE, "fdir", NOW)
    with pytest.raises(TransitionError):
        m.transition(Mode.IMAGING, "cmd", NOW)
    m.transition(Mode.FAULT, "x", NOW)
    with pytest.raises(TransitionError):
        m.transition(Mode.NOMINAL, "x", NOW)  # FAULT exits only to SAFE
    m.reset("reboot", NOW)
    assert m.mode is Mode.BOOT and len(m.history) == 5


def test_mode_same_state_rejected():
    m = ModeManager()
    m.transition(Mode.SAFE, "x", NOW)
    with pytest.raises(TransitionError, match="already"):
        m.transition(Mode.SAFE, "x", NOW)


# ---------------------------------------------------------------- FDIR
def _snap(**kw):
    base = dict(soc_pct=80, battery_c=20, payload_c=20, cpu_c=40, storage_free_bytes=10**8, camera_failures=0, gnss_fix=True)
    base.update(kw)
    return HealthSnapshot(**base)


def test_fdir_nominal_has_no_faults():
    assert evaluate(_snap(), OnboardConfig()) == []


@pytest.mark.parametrize(
    "kw,code,action",
    [
        ({"soc_pct": 20}, FaultCode.LOW_BATTERY, Action.ENTER_SAFE),
        ({"payload_c": 60}, FaultCode.PAYLOAD_OVERTEMP, Action.ENTER_SAFE),
        ({"payload_c": -30}, FaultCode.PAYLOAD_UNDERTEMP, Action.INHIBIT_IMAGING),
        ({"cpu_c": 90}, FaultCode.CPU_OVERTEMP, Action.ENTER_SAFE),
        ({"battery_c": -5}, FaultCode.BATTERY_TEMP, Action.ENTER_SAFE),
        ({"camera_failures": 3}, FaultCode.CAMERA_FAILURE, Action.INHIBIT_IMAGING),
        ({"storage_free_bytes": 10}, FaultCode.STORAGE_FULL, Action.INHIBIT_IMAGING),
        ({"gnss_fix": False}, FaultCode.GNSS_NO_FIX, Action.NONE),
    ],
)
def test_fdir_rules(kw, code, action):
    faults = {f.code: f for f in evaluate(_snap(**kw), OnboardConfig())}
    assert faults[code].action is action


# ---------------------------------------------------------------- watchdog
def test_sim_watchdog_resets_after_timeout_only():
    wd = SimWatchdogMCU(timeout_s=10)
    assert not wd.poll(0)
    for t in range(1, 30):
        wd.kick(t)
        assert not wd.poll(t)
    assert not wd.poll(39)
    assert wd.poll(40) and wd.reset_count == 1
    assert not wd.poll(41)  # re-armed


# ---------------------------------------------------------------- camera
def _cam(**kw):
    return MockCamera(position_fn=lambda: (11.5, 104.9, True), **kw)


def test_pipeline_jpeg_checksum_timestamp_metadata():
    cfg = CameraConfig(320, 240, 80)
    img = process(_cam().capture(cfg), cfg, NOW, chunk_size=1000, position=(11.5, 104.9, 500.0), mode=Mode.IMAGING)
    assert img.jpeg[:2] == b"\xff\xd8"
    assert img.meta.sha256 == hashlib.sha256(img.jpeg).hexdigest()
    assert img.meta.size_bytes == len(img.jpeg)
    assert img.meta.captured_utc == NOW and img.meta.captured_utc.tzinfo is not None
    assert img.meta.source is ImageSource.SIMULATED_ORBITAL
    assert img.meta.chunks == -(-len(img.jpeg) // 1000)
    assert (img.meta.width, img.meta.height) == (320, 240)
    thumb = Image.open(io.BytesIO(img.thumbnail))
    assert max(thumb.size) <= 256


def test_pipeline_rejects_naive_timestamp():
    cfg = CameraConfig(128, 128, 80)
    with pytest.raises(ValueError):
        process(_cam().capture(cfg), cfg, datetime(2026, 1, 1), 1000)


@pytest.mark.parametrize("cfg", [CameraConfig(10, 10, 80), CameraConfig(640, 480, 99), CameraConfig(9000, 480, 80)])
def test_invalid_camera_config(cfg):
    with pytest.raises(ValueError):
        _cam().capture(cfg)


def test_mock_camera_failure_injection():
    with pytest.raises(CameraError):
        _cam(fail_fn=lambda: True).capture(CameraConfig(128, 128, 80))


def test_mock_sample_dir_is_not_labelled_orbital(tmp_path):
    Image.new("RGB", (64, 64), (10, 20, 30)).save(tmp_path / "bench.png")
    frame = MockCamera(sample_dir=tmp_path).capture(CameraConfig(128, 96, 80))
    assert frame.source is ImageSource.MOCK_SAMPLE


def test_capture_scheduler_orders_and_limits():
    s = CaptureScheduler()
    s.add(NOW + timedelta(seconds=20), "b")
    s.add(NOW + timedelta(seconds=10), "a")
    assert [c.command_id for c in s.due(NOW + timedelta(seconds=15))] == ["a"]
    assert [c.command_id for c in s.due(NOW + timedelta(seconds=25))] == ["b"]
    with pytest.raises(ValueError):
        s.add(datetime(2026, 1, 1), "naive")


# ---------------------------------------------------------------- storage
def test_storage_save_load_and_exhaustion(tmp_path):
    st = StorageManager(tmp_path, capacity_bytes=60_000)
    cfg = CameraConfig(320, 240, 80)
    img = process(_cam().capture(cfg), cfg, NOW, 1000)
    st.save_image(img.meta, img.jpeg, img.thumbnail)
    meta, data = st.load_image(img.meta.image_id)
    assert data == img.jpeg and meta == img.meta
    with pytest.raises(StorageFullError):
        for _ in range(100):
            i2 = process(_cam().capture(cfg), cfg, NOW, 1000)
            st.save_image(i2.meta, i2.jpeg, i2.thumbnail)
    assert st.used_bytes() <= st.capacity_bytes


def test_storage_state_survives_restart_and_tmp_cleanup(tmp_path):
    st = StorageManager(tmp_path, 10**6)
    st.save_state({"boot_count": 3})
    (st.images_dir / "torn.jpg.tmp").write_bytes(b"partial")
    st2 = StorageManager(tmp_path, 10**6)
    assert st2.load_state()["boot_count"] == 3
    assert not list(st2.images_dir.glob("*.tmp"))


def test_storage_ignores_corrupt_metadata(tmp_path):
    st = StorageManager(tmp_path, 10**6)
    (st.images_dir / "bad.json").write_text("{not json")
    assert st.list_images() == []


# ---------------------------------------------------------------- transfer
def test_transfer_timeout_retry_and_abandon():
    q = DownlinkQueue(ack_timeout_s=10, max_retries=2)
    q.enqueue("a", 3)
    q.enqueue("a", 3)
    assert len(q) == 1
    t = q.active()
    for attempt in range(2):
        t.state, t.sent_at, t.attempts = TransferState.AWAIT_ACK, 0.0, attempt + 1
        res = q.check_timeouts(11)
    assert res.abandoned == ["a"] and len(q) == 0


def test_transfer_selective_repeat():
    q = DownlinkQueue()
    q.enqueue("a", 5)
    t = q.active()
    assert [t.next_index() for _ in range(6)] == [0, 1, 2, 3, 4, None]
    t.state = TransferState.AWAIT_ACK
    q.nack("a", missing=[3, 1, 99])
    assert t.state is TransferState.SENDING
    assert [t.next_index() for _ in range(3)] == [1, 3, None]
    q.nack("a")  # checksum failure -> full restart
    assert t.state is TransferState.QUEUED and t.next_chunk == 0


# ---------------------------------------------------------------- scheduler
def test_task_scheduler_isolates_failures():
    s = TaskScheduler()
    calls = []
    s.add("ok", 1.0, lambda t: calls.append(t))
    s.add("bad", 1.0, lambda t: 1 / 0)
    for t in range(5):
        s.run_due(float(t))
    assert calls == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert s.tasks["bad"].errors == 5


# ---------------------------------------------------------------- GNSS / TCP
def test_nmea_gga():
    fix = parse_gga("$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47")
    assert fix.fix and fix.sats == 8
    assert fix.lat_deg == pytest.approx(48.1173) and fix.lon_deg == pytest.approx(11.516667)
    assert fix.alt_km == pytest.approx(0.5454)
    with pytest.raises(SensorError):
        parse_gga("$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*48")


def test_tcp_frame_link_reassembles_stream():
    a, b = socket.socketpair()
    la, lb = TcpFrameLink(a), TcpFrameLink(b)
    frames = [b"x" * n for n in (1, 100, 5000)]
    for f in frames:
        la.send(f)
    got = []
    for _ in range(50):
        got += lb.receive()
        if len(got) == 3:
            break
    assert got == frames
    la.close()
    lb.receive()
    assert not lb.connected
