"""SGP4 propagation wrapper (python-sgp4, Vallado's reference implementation)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
from sgp4.api import WGS72, Satrec

from .elements import SyntheticElements
from .frames import ecef_to_geodetic, ensure_utc, julian_date, look_angles, teme_to_ecef
from .sun import in_eclipse, sun_vector_eci

_JD_1949_12_31 = 2433281.5


class PropagationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OrbitSample:
    utc: datetime
    r_teme_km: np.ndarray
    v_teme_km_s: np.ndarray
    r_ecef_km: np.ndarray
    lat_deg: float
    lon_deg: float
    alt_km: float
    speed_km_s: float
    sunlit: bool
    sun_teme: np.ndarray


class Propagator:
    """Propagates synthetic elements with SGP4 and derives geodetic quantities."""

    def __init__(self, elements: SyntheticElements, satnum: int = 99999) -> None:
        self.elements = elements
        jd, fr = julian_date(elements.epoch)
        sat = Satrec()
        sat.sgp4init(
            WGS72,
            "i",
            satnum,
            (jd + fr) - _JD_1949_12_31,
            elements.bstar,
            0.0,
            0.0,
            elements.eccentricity,
            math.radians(elements.arg_perigee_deg),
            math.radians(elements.inclination_deg),
            math.radians(elements.mean_anomaly_deg),
            elements.mean_motion_rad_s * 60.0,  # rad/min
            math.radians(elements.raan_deg),
        )
        self._sat = sat

    def sample(self, t: datetime) -> OrbitSample:
        t = ensure_utc(t)
        jd, fr = julian_date(t)
        err, r, v = self._sat.sgp4(jd, fr)
        if err != 0:
            raise PropagationError(f"SGP4 error code {err} at {t.isoformat()}")
        r_teme = np.array(r)
        v_teme = np.array(v)
        r_ecef = teme_to_ecef(r_teme, jd, fr)
        lat, lon, alt = ecef_to_geodetic(r_ecef)
        sun_u, _ = sun_vector_eci(jd, fr)
        return OrbitSample(
            utc=t,
            r_teme_km=r_teme,
            v_teme_km_s=v_teme,
            r_ecef_km=r_ecef,
            lat_deg=lat,
            lon_deg=lon,
            alt_km=alt,
            speed_km_s=float(np.linalg.norm(v_teme)),
            sunlit=not in_eclipse(r_teme, sun_u),
            sun_teme=sun_u,
        )

    def ground_track(
        self, start: datetime, minutes: float, step_s: float = 30.0
    ) -> list[OrbitSample]:
        n = int(minutes * 60 / step_s) + 1
        return [self.sample(start + timedelta(seconds=i * step_s)) for i in range(n)]

    def elevation(self, t: datetime, lat: float, lon: float, alt_km: float) -> float:
        return look_angles(self.sample(t).r_ecef_km, lat, lon, alt_km)[1]
