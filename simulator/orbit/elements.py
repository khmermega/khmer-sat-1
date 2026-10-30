"""SYNTHETIC demonstration orbital elements.

!!! These elements do NOT describe any real satellite. !!!
KHMER-SAT 1 has no launch, no NORAD catalogue number and no published TLE.
Everything produced from these elements is a labelled simulation.

The demonstration orbit is a circular, sun-synchronous-like LEO. Its RAAN is
solved so that the sub-satellite point passes over a chosen target (by default
Phnom Penh) shortly after simulation start - purely to make demos interesting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from .frames import EARTH_RADIUS_KM, ensure_utc, gmst_rad, julian_date

MU_EARTH_KM3_S2 = 398600.4418
SYNTHETIC_LABEL = "SYNTHETIC DEMO ORBIT - NOT REAL TRACKING DATA"


@dataclass(frozen=True, slots=True)
class SyntheticElements:
    epoch: datetime
    altitude_km: float
    inclination_deg: float
    raan_deg: float
    eccentricity: float
    arg_perigee_deg: float
    mean_anomaly_deg: float
    bstar: float = 0.0
    label: str = field(default=SYNTHETIC_LABEL)

    @property
    def semi_major_axis_km(self) -> float:
        return EARTH_RADIUS_KM + self.altitude_km

    @property
    def mean_motion_rad_s(self) -> float:
        return math.sqrt(MU_EARTH_KM3_S2 / self.semi_major_axis_km**3)

    @property
    def period_min(self) -> float:
        return 2 * math.pi / self.mean_motion_rad_s / 60.0


def overhead_pass_elements(
    epoch: datetime,
    target_lat_deg: float,
    target_lon_deg: float,
    altitude_km: float = 500.0,
    inclination_deg: float = 97.4,
    ascending: bool = False,
) -> SyntheticElements:
    """Build circular elements whose ground track crosses the target at ``epoch``.

    For a circular orbit with argument of perigee 0, the argument of latitude
    equals the mean anomaly ``u``. Then sin(lat) = sin(i)·sin(u) and the right
    ascension of the sub-satellite point is RAAN + atan2(cos(i)·sin(u), cos(u)).
    Requiring that to equal (target longitude + GMST) yields the RAAN.
    """
    epoch = ensure_utc(epoch)
    inc = math.radians(inclination_deg)
    lat = math.radians(target_lat_deg)
    if abs(math.sin(lat)) > abs(math.sin(inc)):
        raise ValueError("target latitude is not reachable at this inclination")
    u = math.asin(math.sin(lat) / math.sin(inc))
    if not ascending:
        u = math.pi - u  # descending node pass (typical SSO morning orbit)
    jd, fr = julian_date(epoch)
    ra_point = math.radians(target_lon_deg) + gmst_rad(jd, fr)
    raan = ra_point - math.atan2(math.cos(inc) * math.sin(u), math.cos(u))
    return SyntheticElements(
        epoch=epoch,
        altitude_km=altitude_km,
        inclination_deg=inclination_deg,
        raan_deg=math.degrees(raan) % 360.0,
        eccentricity=0.0001,
        arg_perigee_deg=0.0,
        mean_anomaly_deg=math.degrees(u) % 360.0,
    )
