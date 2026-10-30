"""Camera abstraction for the optical payload."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL import Image

from shared.schemas import ImageSource

MIN_DIM, MAX_DIM = 64, 4096


class CameraError(Exception):
    """Capture failed (device missing, timeout, bad frame...)."""


@dataclass(slots=True)
class CameraConfig:
    width: int = 1280
    height: int = 960
    jpeg_quality: int = 85

    def validate(self) -> None:
        if not (MIN_DIM <= self.width <= MAX_DIM and MIN_DIM <= self.height <= MAX_DIM):
            raise ValueError(f"resolution must be within {MIN_DIM}..{MAX_DIM} px")
        if not 10 <= self.jpeg_quality <= 95:
            raise ValueError("jpeg_quality must be within 10..95")


@dataclass(slots=True)
class RawFrame:
    image: Image.Image
    source: ImageSource
    camera: str
    note: str = ""


class Camera(ABC):
    """A camera returns RGB frames and declares their provenance.

    Implementations MUST report an honest ImageSource: a physical camera on the
    ground returns GROUND_TEST_HARDWARE, never SIMULATED_ORBITAL.
    """

    name: str = "camera"

    def open(self) -> None:  # noqa: B027 - optional hook
        """Initialise the device. Default: nothing to do."""

    def close(self) -> None:  # noqa: B027
        """Release the device."""

    @abstractmethod
    def capture(self, config: CameraConfig) -> RawFrame: ...
