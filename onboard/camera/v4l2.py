"""USB / V4L2 camera adapter (OpenCV backend) for GROUND tests.

Install with `uv pip install opencv-python-headless` (extra: hardware).
Frames are always labelled GROUND_TEST_HARDWARE.
"""

from __future__ import annotations

from PIL import Image

from shared.schemas import ImageSource

from .base import Camera, CameraConfig, CameraError, RawFrame


class V4L2Camera(Camera):
    name = "usb-v4l2"

    def __init__(self, device: int | str = 0, warmup_frames: int = 3) -> None:
        self.device = device
        self.warmup_frames = warmup_frames
        self._cap = None

    def open(self) -> None:
        try:
            import cv2  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on host
            raise CameraError("OpenCV not installed (uv pip install opencv-python-headless)") from exc
        self._cv2 = cv2
        self._cap = cv2.VideoCapture(self.device)
        if not self._cap.isOpened():
            raise CameraError(f"cannot open video device {self.device!r}")

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def capture(self, config: CameraConfig) -> RawFrame:
        config.validate()
        if self._cap is None:
            self.open()
        cap, cv2 = self._cap, self._cv2
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.height)
        frame = None
        for _ in range(self.warmup_frames + 1):  # let auto-exposure settle
            ok, frame = cap.read()
            if not ok:
                raise CameraError("frame grab failed")
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        if img.size != (config.width, config.height):
            img = img.resize((config.width, config.height))
        return RawFrame(img, ImageSource.GROUND_TEST_HARDWARE, self.name, note="ground test capture")
