"""Mock camera: synthetic orbital scenes, or replay of sample image files."""

from __future__ import annotations

from collections.abc import Callable
from itertools import cycle
from pathlib import Path

from PIL import Image

from shared.schemas import ImageSource
from simulator.imagery.synthetic import render_synthetic_scene

from .base import Camera, CameraConfig, CameraError, RawFrame

PositionFn = Callable[[], tuple[float, float, bool]]  # lat, lon, sunlit


class MockCamera(Camera):
    """Two flavours:

    - ``position_fn`` given: render a synthetic scene for the simulated position
      (ImageSource.SIMULATED_ORBITAL).
    - ``sample_dir`` given: cycle through JPEG/PNG files in that directory
      (ImageSource.MOCK_SAMPLE - provenance of those files is the user's).
    """

    name = "mock"

    def __init__(
        self,
        position_fn: PositionFn | None = None,
        sample_dir: Path | None = None,
        fail_fn: Callable[[], bool] | None = None,
    ) -> None:
        if position_fn is None and sample_dir is None:
            raise ValueError("MockCamera needs position_fn or sample_dir")
        self._position_fn = position_fn
        self._fail_fn = fail_fn or (lambda: False)
        self._samples = None
        if sample_dir is not None:
            files = sorted(p for p in Path(sample_dir).iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
            if not files:
                raise ValueError(f"no sample images in {sample_dir}")
            self._samples = cycle(files)

    def capture(self, config: CameraConfig) -> RawFrame:
        config.validate()
        if self._fail_fn():
            raise CameraError("mock camera: injected failure (no frame)")
        if self._samples is not None:
            path = next(self._samples)
            img = Image.open(path).convert("RGB").resize((config.width, config.height))
            return RawFrame(img, ImageSource.MOCK_SAMPLE, self.name, note=f"sample file {path.name}")
        assert self._position_fn is not None
        lat, lon, sunlit = self._position_fn()
        img = render_synthetic_scene(config.width, config.height, lat, lon, sunlit)
        return RawFrame(img, ImageSource.SIMULATED_ORBITAL, "mock-synthetic", note="procedural synthetic scene")
