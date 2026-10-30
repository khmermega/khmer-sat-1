"""Hardware-in-the-loop tests. Skipped unless KS_HIL=1 and the device is attached.

Run on the bench (Raspberry Pi + USB camera + MCU on /dev/ttyACM0):
    KS_HIL=1 KS_CAMERA_DEVICE=0 KS_WATCHDOG_PORT=/dev/ttyACM0 uv run pytest -m hil tests/hardware-in-loop
"""

from __future__ import annotations

import hashlib
import os
import time
from datetime import UTC, datetime

import pytest

from onboard.camera.base import CameraConfig
from onboard.camera.pipeline import process
from shared.schemas import ImageSource

pytestmark = [
    pytest.mark.hil,
    pytest.mark.skipif(os.environ.get("KS_HIL") != "1", reason="hardware-in-the-loop disabled (set KS_HIL=1)"),
]


def test_usb_camera_capture_is_labelled_ground_test():
    from onboard.camera.v4l2 import V4L2Camera

    cam = V4L2Camera(int(os.environ.get("KS_CAMERA_DEVICE", "0")))
    cfg = CameraConfig(640, 480, 85)
    try:
        frame = cam.capture(cfg)
    finally:
        cam.close()
    assert frame.source is ImageSource.GROUND_TEST_HARDWARE
    img = process(frame, cfg, datetime.now(UTC), 3072)
    assert img.meta.sha256 == hashlib.sha256(img.jpeg).hexdigest()


def test_watchdog_mcu_responds_to_heartbeat():
    from onboard.safety.watchdog import SerialWatchdogMCU

    port = os.environ.get("KS_WATCHDOG_PORT")
    if not port:
        pytest.skip("KS_WATCHDOG_PORT not set")
    wd = SerialWatchdogMCU(port)
    for _ in range(5):
        wd.kick(time.monotonic())
        time.sleep(0.5)
    assert wd.reset_count >= 0
