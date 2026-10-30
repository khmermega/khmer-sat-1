"""Time and coordinate-frame conversions.

Frames used (explicit, see docs/architecture.md §5):
- TEME : True Equator Mean Equinox - the native output frame of SGP4.
- PEF/ECEF : Earth-fixed. TEME -> PEF is a rotation by GMST (IAU-82) about Z.
  Polar motion (< ~15 m at the surface) is neglected - acceptable for a
  visualisation/visibility simulator, NOT for precision orbit determination.
- WGS-84 geodetic latitude/longitude/height.
- ENU / topocentric azimuth-elevation for ground-station look angles.

Time scale: inputs are UTC datetimes. UT1-UTC (< 0.9 s) is neglected.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np

WGS84_A_KM = 6378.137
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)
EARTH_RADIUS_KM = WGS84_A_KM
OMEGA_EARTH_RAD_S = 7.292115e-5


def ensure_utc(dt: datetime) -> datetime:
    """Reject naive datetimes - every timestamp in the system must be explicit UTC."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime: an explicit UTC tzinfo is required")
    return dt.astimezone(UTC)


def julian_date(dt: datetime) -> tuple[float, float]:
    """Return (jd, fraction) split Julian date for a UTC datetime.

    Splitting keeps sub-millisecond precision in double arithmetic, matching the
    convention of the sgp4 library (``Satrec.sgp4(jd, fr)``).
    """
    dt = ensure_utc(dt)
    y, m = dt.year, dt.month
    d = dt.day
    jd = (
        367 * y
        - (7 * (y + ((m + 9) // 12))) // 4
        + (275 * m) // 9
        + d
        + 1721013.5
    )
    fr = (dt.hour * 3600 + dt.minute * 60 + dt.second + dt.microsecond / 1e6) / 86400.0
    return float(jd), fr


def gmst_rad(jd: float, fr: float = 0.0) -> float:
    """Greenwich Mean Sidereal Time (IAU-82), radians in [0, 2π)."""
    t = ((jd - 2451545.0) + fr) / 36525.0
    gmst_s = (
        67310.54841
        + (876600.0 * 3600.0 + 8640184.812866) * t
        + 0.093104 * t * t
        - 6.2e-6 * t * t * t
    )
    return math.radians((gmst_s % 86400.0) / 240.0) % (2 * math.pi)


def rot_z(angle_rad: float) -> np.ndarray:
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])


def teme_to_ecef(r_teme_km: np.ndarray, jd: float, fr: float = 0.0) -> np.ndarray:
    """Rotate a TEME position into the Earth-fixed (pseudo-ECEF / PEF) frame."""
    return rot_z(gmst_rad(jd, fr)) @ np.asarray(r_teme_km, dtype=float)


def ecef_to_teme(r_ecef_km: np.ndarray, jd: float, fr: float = 0.0) -> np.ndarray:
    return rot_z(gmst_rad(jd, fr)).T @ np.asarray(r_ecef_km, dtype=float)


def geodetic_to_ecef(lat_deg: float, lon_deg: float, alt_km: float) -> np.ndarray:
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    n = WGS84_A_KM / math.sqrt(1.0 - WGS84_E2 * math.sin(lat) ** 2)
    return np.array(
        [
            (n + alt_km) * math.cos(lat) * math.cos(lon),
            (n + alt_km) * math.cos(lat) * math.sin(lon),
            (n * (1.0 - WGS84_E2) + alt_km) * math.sin(lat),
        ]
    )


def ecef_to_geodetic(r_ecef_km: np.ndarray) -> tuple[float, float, float]:
    """WGS-84 geodetic (lat_deg, lon_deg, alt_km) by fixed-point iteration.

    Converges to < 1 mm in a handful of iterations for LEO altitudes.
    """
    x, y, z = (float(v) for v in r_ecef_km)
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1.0 - WGS84_E2))
    for _ in range(10):
        n = WGS84_A_KM / math.sqrt(1.0 - WGS84_E2 * math.sin(lat) ** 2)
        new_lat = math.atan2(z + WGS84_E2 * n * math.sin(lat), p)
        if abs(new_lat - lat) < 1e-12:
            lat = new_lat
            break
        lat = new_lat
    # Height formula valid at all latitudes (no division by cos(lat)).
    sin_lat = math.sin(lat)
    alt = p * math.cos(lat) + z * sin_lat - WGS84_A_KM * math.sqrt(1.0 - WGS84_E2 * sin_lat**2)
    return math.degrees(lat), math.degrees(lon), alt


def look_angles(
    r_sat_ecef_km: np.ndarray, lat_deg: float, lon_deg: float, alt_km: float
) -> tuple[float, float, float]:
    """Topocentric (azimuth_deg, elevation_deg, range_km) of a satellite from a site."""
    site = geodetic_to_ecef(lat_deg, lon_deg, alt_km)
    rho = np.asarray(r_sat_ecef_km, dtype=float) - site
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    # ECEF -> ENU rotation
    east = np.array([-math.sin(lon), math.cos(lon), 0.0])
    north = np.array([-math.sin(lat) * math.cos(lon), -math.sin(lat) * math.sin(lon), math.cos(lat)])
    up = np.array([math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)])
    e, n, u = float(rho @ east), float(rho @ north), float(rho @ up)
    rng = math.sqrt(e * e + n * n + u * u)
    az = math.degrees(math.atan2(e, n)) % 360.0
    el = math.degrees(math.asin(u / rng))
    return az, el, rng
