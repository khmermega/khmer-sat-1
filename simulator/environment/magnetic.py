"""First-order tilted-dipole geomagnetic field.

Approximation only (errors of tens of percent vs IGRF are expected). Adequate
for exercising magnetometer data paths, NOT for ADCS design. Replace with
IGRF-14 (e.g. via `ppigrf`) before any control-law work.
"""

from __future__ import annotations

import math

import numpy as np

from simulator.orbit.frames import EARTH_RADIUS_KM, geodetic_to_ecef

B0_TESLA = 3.0e-5  # approximate equatorial surface field magnitude
# Approximate north geomagnetic pole location (dipole axis), ~2025.
_POLE_LAT, _POLE_LON = 80.8, -72.6


def dipole_field_ecef(r_ecef_km: np.ndarray) -> np.ndarray:
    """Field vector in ECEF, microtesla."""
    m_hat = -geodetic_to_ecef(_POLE_LAT, _POLE_LON, 0.0)
    m_hat /= np.linalg.norm(m_hat)  # Earth's dipole moment points toward geographic south
    r = np.asarray(r_ecef_km, dtype=float)
    rn = float(np.linalg.norm(r))
    r_hat = r / rn
    b = B0_TESLA * (EARTH_RADIUS_KM / rn) ** 3 * (3 * float(m_hat @ r_hat) * r_hat - m_hat)
    return b * 1e6


def field_magnitude_ut(lat_deg: float, alt_km: float) -> float:
    """Convenience for tests: |B| of an axial dipole at a geomagnetic latitude."""
    r = EARTH_RADIUS_KM + alt_km
    return B0_TESLA * 1e6 * (EARTH_RADIUS_KM / r) ** 3 * math.sqrt(1 + 3 * math.sin(math.radians(lat_deg)) ** 2)
