"""Ground-station definitions and pass (AOS/LOS) prediction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .frames import ensure_utc, look_angles
from .propagator import Propagator


@dataclass(frozen=True, slots=True)
class GroundStation:
    name: str
    lat_deg: float
    lon_deg: float
    alt_km: float
    min_elevation_deg: float = 10.0

    def __post_init__(self) -> None:
        if not -90 <= self.lat_deg <= 90 or not -180 <= self.lon_deg <= 180:
            raise ValueError("ground station coordinates out of range")


# Simulated ground station. Coordinates are approximate for central Phnom Penh;
# the real site is TBD (see docs/mission-requirements.md, FR-ORB-005).
PHNOM_PENH = GroundStation("Phnom Penh (simulated)", 11.5564, 104.9282, 0.012, 10.0)


@dataclass(frozen=True, slots=True)
class Pass:
    aos: datetime
    los: datetime
    tca: datetime
    max_elevation_deg: float

    @property
    def duration_s(self) -> float:
        return (self.los - self.aos).total_seconds()


def _el(prop: Propagator, gs: GroundStation, t: datetime) -> float:
    return look_angles(prop.sample(t).r_ecef_km, gs.lat_deg, gs.lon_deg, gs.alt_km)[1]


def _bisect(prop: Propagator, gs: GroundStation, t0: datetime, t1: datetime, rising: bool) -> datetime:
    """Find the min-elevation crossing between t0 and t1 to ~1 s."""
    for _ in range(20):
        if (t1 - t0).total_seconds() <= 1.0:
            break
        mid = t0 + (t1 - t0) / 2
        above = _el(prop, gs, mid) >= gs.min_elevation_deg
        if above == rising:
            t1 = mid
        else:
            t0 = mid
    return t1 if rising else t0


def predict_passes(
    prop: Propagator,
    gs: GroundStation,
    start: datetime,
    hours: float = 24.0,
    step_s: float = 30.0,
) -> list[Pass]:
    """Coarse-scan elevation then refine AOS/LOS by bisection."""
    start = ensure_utc(start)
    end = start + timedelta(hours=hours)
    passes: list[Pass] = []
    t = start
    prev_t, prev_above = t, _el(prop, gs, t) >= gs.min_elevation_deg
    aos: datetime | None = start if prev_above else None
    best_el, best_t = -90.0, start
    while t < end:
        t = t + timedelta(seconds=step_s)
        el = _el(prop, gs, t)
        above = el >= gs.min_elevation_deg
        if above and not prev_above:
            aos = _bisect(prop, gs, prev_t, t, rising=True)
            best_el, best_t = el, t
        if above and el > best_el:
            best_el, best_t = el, t
        if prev_above and not above and aos is not None:
            los = _bisect(prop, gs, prev_t, t, rising=False)
            passes.append(Pass(aos, los, best_t, round(best_el, 2)))
            aos, best_el = None, -90.0
        prev_t, prev_above = t, above
    return passes
