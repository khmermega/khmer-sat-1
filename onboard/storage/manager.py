"""Onboard storage: images + metadata on a filesystem with a hard quota.

Layout under ``root``:
    images/<id>.jpg, images/<id>.thumb.jpg, images/<id>.json
    state.json   (persistent counters, e.g. boot_count - survives resets)

Writes are atomic (temp file + rename) so a power loss mid-write leaves either
the old file or the new one, never a torn file.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from shared.schemas import ImageMeta


class StorageFullError(Exception):
    pass


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class StorageManager:
    def __init__(self, root: Path, capacity_bytes: int) -> None:
        if capacity_bytes <= 0:
            raise ValueError("capacity must be positive")
        self.root = Path(root)
        self.capacity_bytes = capacity_bytes
        self.images_dir = self.root / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = self.root / "state.json"
        self._cleanup_temp_files()

    def _cleanup_temp_files(self) -> None:
        for p in self.images_dir.glob("*.tmp"):
            p.unlink(missing_ok=True)

    # ---- persistent key/value state ----
    def load_state(self) -> dict[str, Any]:
        try:
            return json.loads(self._state_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_state(self, state: dict[str, Any]) -> None:
        _atomic_write(self._state_path, json.dumps(state).encode())

    # ---- images ----
    def used_bytes(self) -> int:
        return sum(p.stat().st_size for p in self.images_dir.iterdir() if p.is_file())

    def free_bytes(self) -> int:
        return max(0, self.capacity_bytes - self.used_bytes())

    def save_image(self, meta: ImageMeta, jpeg: bytes, thumbnail: bytes) -> None:
        meta_bytes = meta.model_dump_json().encode()
        needed = len(jpeg) + len(thumbnail) + len(meta_bytes)
        if needed > self.free_bytes():
            raise StorageFullError(f"need {needed} B, {self.free_bytes()} B free")
        base = self.images_dir / meta.image_id
        _atomic_write(base.with_suffix(".jpg"), jpeg)
        _atomic_write(base.with_suffix(".thumb.jpg"), thumbnail)
        _atomic_write(base.with_suffix(".json"), meta_bytes)

    def load_image(self, image_id: str) -> tuple[ImageMeta, bytes]:
        base = self.images_dir / image_id
        meta = ImageMeta.model_validate_json(base.with_suffix(".json").read_bytes())
        return meta, base.with_suffix(".jpg").read_bytes()

    def list_images(self) -> list[ImageMeta]:
        metas = []
        for p in self.images_dir.glob("*.json"):
            try:
                metas.append(ImageMeta.model_validate_json(p.read_bytes()))
            except ValueError:
                continue  # corrupted metadata - skip, reported by health checks
        return sorted(metas, key=lambda m: m.captured_utc)

    def delete_image(self, image_id: str) -> None:
        base = self.images_dir / image_id
        for suffix in (".jpg", ".thumb.jpg", ".json"):
            base.with_suffix(suffix).unlink(missing_ok=True)

    def delete_all_images(self) -> int:
        n = len(list(self.images_dir.glob("*.json")))
        shutil.rmtree(self.images_dir)
        self.images_dir.mkdir(parents=True)
        return n

    def fill_dummy(self, nbytes: int) -> None:
        """Simulation fault injection: consume space to exercise STORAGE_FULL."""
        _atomic_write(self.images_dir / "fill.bin", b"\0" * max(0, nbytes))

    def clear_dummy(self) -> None:
        (self.images_dir / "fill.bin").unlink(missing_ok=True)
