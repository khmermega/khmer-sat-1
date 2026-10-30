"""Procedurally generated SYNTHETIC "orbital" imagery.

These images are invented terrain made from value noise. They are stamped
"SIMULATED" in the pixels themselves and tagged ImageSource.SIMULATED_ORBITAL
in metadata, so they can never be mistaken for real Earth observation data.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _value_noise(rng: np.random.Generator, h: int, w: int, octaves: int = 5) -> np.ndarray:
    out = np.zeros((h, w))
    amp, total = 1.0, 0.0
    for o in range(octaves):
        gs = 2 ** (o + 2)
        grid = rng.random((gs + 1, gs + 1))
        ys = np.linspace(0, gs, h, endpoint=False)
        xs = np.linspace(0, gs, w, endpoint=False)
        y0, x0 = ys.astype(int), xs.astype(int)
        fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
        fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
        a = grid[y0][:, x0]
        b = grid[y0][:, x0 + 1]
        c = grid[y0 + 1][:, x0]
        d = grid[y0 + 1][:, x0 + 1]
        out += amp * (a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy)
        total += amp
        amp *= 0.5
    return out / total


def render_synthetic_scene(width: int, height: int, lat: float, lon: float, sunlit: bool = True) -> Image.Image:
    seed = int((round(lat, 1) + 90) * 10_000 + (round(lon, 1) + 180) * 10)
    rng = np.random.default_rng(seed)
    elev = _value_noise(rng, height, width)
    clouds = _value_noise(rng, height, width, octaves=4)
    rgb = np.zeros((height, width, 3))
    water = elev < 0.45
    rgb[water] = [0.05, 0.18, 0.32]
    veg = (elev >= 0.45) & (elev < 0.6)
    rgb[veg] = [0.16, 0.36, 0.14]
    dry = (elev >= 0.6) & (elev < 0.72)
    rgb[dry] = [0.48, 0.42, 0.26]
    rgb[elev >= 0.72] = [0.55, 0.52, 0.48]
    cloud_mask = np.clip((clouds - 0.58) * 4, 0, 1)[..., None]
    rgb = rgb * (1 - cloud_mask) + cloud_mask * 0.95
    if not sunlit:
        rgb *= 0.08
    img = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8), "RGB")
    draw = ImageDraw.Draw(img)
    stamp = f"SIMULATED - NOT REAL IMAGERY  {lat:+.2f} {lon:+.2f}"
    size = max(10, height // 24)  # legible even in a 256 px thumbnail
    font = ImageFont.load_default(size=size)
    bar = int(size * 1.6)
    draw.rectangle([0, height - bar, width, height], fill=(0, 0, 0))
    draw.text((size // 2, height - bar + (bar - size) // 2), stamp, fill=(255, 200, 0), font=font)
    return img
