"""Raspberry Pi camera adapter (libcamera / picamera2) for GROUND tests.

picamera2 is only available on Raspberry Pi OS (`sudo apt install python3-picamera2`).
Frames are always labelled GROUND_TEST_HARDWARE.
"""

from __future__ import annotations

from PIL import Image

from shared.schemas import ImageSource

from .base import Camera, CameraConfig, CameraError, RawFrame


class PiCamera(Camera):  # pragma: no cover - requires Raspberry Pi hardware
    name = "rpi-camera"

    def __init__(self, camera_num: int = 0) -> None:
        self.camera_num = camera_num
        self._cam = None
        self._configured: tuple[int, int] | None = None

    def open(self) -> None:
        try:
            from picamera2 import Picamera2  # type: ignore[import-not-found]
        except ImportError as exc:
            raise CameraError("picamera2 not available - run on Raspberry Pi OS") from exc
        self._cam = Picamera2(self.camera_num)

    def close(self) -> None:
        if self._cam is not None:
            self._cam.stop()
            self._cam.close()
            self._cam = None

    def capture(self, config: CameraConfig) -> RawFrame:
        config.validate()
        if self._cam is None:
            self.open()
        size = (config.width, config.height)
        if self._configured != size:
            self._cam.stop()
            self._cam.configure(self._cam.create_still_configuration(main={"size": size, "format": "RGB888"}))
            self._cam.start()
            self._configured = size
        try:
            arr = self._cam.capture_array("main")
        except Exception as exc:
            raise CameraError(f"picamera2 capture failed: {exc}") from exc
        # RGB888 in picamera2 is BGR byte order in memory.
        img = Image.fromarray(arr[..., ::-1].copy())
        return RawFrame(img, ImageSource.GROUND_TEST_HARDWARE, self.name, note="ground test capture")
