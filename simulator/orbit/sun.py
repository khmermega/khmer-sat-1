"""Low-precision solar ephemeris and cylindrical Earth-shadow model.

Sun direction: Astronomical Almanac low-precision formula (~0.01° accuracy
1950-2050), expressed in the mean-equator-of-date frame which we treat as
equal to TEME (difference < 0.01°, negligible for eclipse/power simulation).

Shadow: cylindrical umbra model (no penumbra). Eclipse entry/exit times are
therefore approximate by several seconds - documented simulator limitation.
"""

from __future__ import annotations

import math

import numpy as np

from .frames import EARTH_RADIUS_KM

AU_KM = 149_597_870.7


def sun_vector_eci(jd: float, fr: float = 0.0) -> tuple[np.ndarray, float]:
    """Return (unit vector Earth->Sun, distance_km)."""
    n = (jd - 2451545.0) + fr
    mean_lon = math.radians((280.460 + 0.9856474 * n) % 360.0)
    g = math.radians((357.528 + 0.9856003 * n) % 360.0)
    ecl_lon = mean_lon + math.radians(1.915) * math.sin(g) + math.radians(0.020) * math.sin(2 * g)
    eps = math.radians(23.439 - 0.0000004 * n)
    r_au = 1.00014 - 0.01671 * math.cos(g) - 0.00014 * math.cos(2 * g)
    u = np.array(
        [
            math.cos(ecl_lon),
            math.cos(eps) * math.sin(ecl_lon),
            math.sin(eps) * math.sin(ecl_lon),
        ]
    )
    return u, r_au * AU_KM


def in_eclipse(r_eci_km: np.ndarray, sun_unit: np.ndarray) -> bool:
    """True if the satellite is inside Earth's cylindrical shadow."""
    r = np.asarray(r_eci_km, dtype=float)
    proj = float(r @ sun_unit)
    if proj >= 0.0:
        return False
    perp = r - proj * sun_unit
    return float(np.linalg.norm(perp)) < EARTH_RADIUS_KM
