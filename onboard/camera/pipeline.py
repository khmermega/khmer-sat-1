"""Image processing: JPEG compression, thumbnail, SHA-256, UTC timestamp, metadata."""

from __future__ import annotations

import hashlib
import io
import math
import uuid
from dataclasses import dataclass
from datetime import datetime

from shared.schemas import ImageMeta, Mode
from simulator.orbit.frames import ensure_utc

from .base import CameraConfig, RawFrame

THUMB_MAX = 256


@dataclass(slots=True)
class ProcessedImage:
    meta: ImageMeta
    jpeg: bytes
    thumbnail: bytes


def process(
    frame: RawFrame,
    config: CameraConfig,
    captured_utc: datetime,
    chunk_size: int,
    position: tuple[float | None, float | None, float | None] = (None, None, None),
    mode: Mode | None = None,
) -> ProcessedImage:
    captured_utc = ensure_utc(captured_utc)
    buf = io.BytesIO()
    frame.image.save(buf, format="JPEG", quality=config.jpeg_quality, optimize=True)
    jpeg = buf.getvalue()
    thumb = frame.image.copy()
    thumb.thumbnail((THUMB_MAX, THUMB_MAX))
    tbuf = io.BytesIO()
    thumb.save(tbuf, format="JPEG", quality=70)
    lat, lon, alt = position
    meta = ImageMeta(
        image_id=str(uuid.uuid4()),
        captured_utc=captured_utc,
        source=frame.source,
        camera=frame.camera,
        width=frame.image.width,
        height=frame.image.height,
        jpeg_quality=config.jpeg_quality,
        size_bytes=len(jpeg),
        sha256=hashlib.sha256(jpeg).hexdigest(),
        chunks=max(1, math.ceil(len(jpeg) / chunk_size)),
        lat_deg=lat,
        lon_deg=lon,
        alt_km=alt,
        mode=mode,
        note=frame.note,
    )
    return ProcessedImage(meta, jpeg, tbuf.getvalue())
