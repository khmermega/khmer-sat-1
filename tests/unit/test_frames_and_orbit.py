"""REQ: FR-ORB-001..006 - time scales, frame conversions, SGP4, visibility."""

import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from simulator.orbit.elements import SYNTHETIC_LABEL, overhead_pass_elements
from simulator.orbit.frames import (
    ecef_to_geodetic,
    ecef_to_teme,
    ensure_utc,
    geodetic_to_ecef,
    gmst_rad,
    julian_date,
    look_angles,
    teme_to_ecef,
)
from simulator.orbit.propagator import Propagator
from simulator.orbit.sun import in_eclipse, sun_vector_eci
from simulator.orbit.visibility import PHNOM_PENH, GroundStation, predict_passes

T0 = datetime(2026, 1, 15, 3, 0, tzinfo=UTC)


def test_julian_date_j2000():
    jd, fr = julian_date(datetime(2000, 1, 1, 12, 0, tzinfo=UTC))
    assert jd + fr == pytest.approx(2451545.0, abs=1e-9)


def test_julian_date_matches_sgp4_library():
    from sgp4.api import jday

    dt = datetime(2026, 10, 30, 7, 31, 12, 500000, tzinfo=UTC)
    jd, fr = julian_date(dt)
    jd2, fr2 = jday(2026, 10, 30, 7, 31, 12.5)
    assert jd + fr == pytest.approx(jd2 + fr2, abs=1e-10)


def test_gmst_vallado_example_3_5():
    # Vallado, Fundamentals of Astrodynamics, Ex. 3-5: 1992-08-20 12:14 UT1 -> 152.578788 deg
    jd, fr = julian_date(datetime(1992, 8, 20, 12, 14, tzinfo=UTC))
    assert math.degrees(gmst_rad(jd, fr)) == pytest.approx(152.578788, abs=1e-4)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        ensure_utc(datetime(2026, 1, 1))


@pytest.mark.parametrize("lat,lon,alt", [(0, 0, 0), (11.5564, 104.9282, 0.012), (-45, -170, 500), (89.9, 10, 400), (-90, 0, 0)])
def test_geodetic_roundtrip(lat, lon, alt):
    la, lo, al = ecef_to_geodetic(geodetic_to_ecef(lat, lon, alt))
    assert la == pytest.approx(lat, abs=1e-9)
    if abs(lat) < 90:
        assert lo == pytest.approx(lon, abs=1e-9)
    assert al == pytest.approx(alt, abs=1e-6)


def test_equator_prime_meridian_ecef():
    assert np.allclose(geodetic_to_ecef(0, 0, 0), [6378.137, 0, 0])


def test_teme_ecef_inverse():
    jd, fr = julian_date(T0)
    r = np.array([7000.0, -1200.0, 300.0])
    assert np.allclose(ecef_to_teme(teme_to_ecef(r, jd, fr), jd, fr), r)


def test_look_angles_overhead_and_horizon():
    site = (11.5564, 104.9282, 0.0)
    overhead = geodetic_to_ecef(site[0], site[1], 500)
    _, el, rng = look_angles(overhead, *site)
    assert el == pytest.approx(90, abs=1e-6)
    assert rng == pytest.approx(500, abs=1e-6)
    far = geodetic_to_ecef(-site[0], site[1] + 180, 500)
    assert look_angles(far, *site)[1] < -60


def test_synthetic_elements_are_labelled():
    e = overhead_pass_elements(T0, 11.5564, 104.9282)
    assert e.label == SYNTHETIC_LABEL and "SYNTHETIC" in e.label
    assert 94 < e.period_min < 95.5  # 500 km circular


def test_sgp4_overhead_pass_at_epoch():
    e = overhead_pass_elements(T0, PHNOM_PENH.lat_deg, PHNOM_PENH.lon_deg)
    prop = Propagator(e)
    s = prop.sample(T0)
    assert s.lat_deg == pytest.approx(PHNOM_PENH.lat_deg, abs=0.3)
    assert s.lon_deg == pytest.approx(PHNOM_PENH.lon_deg, abs=0.3)
    assert 480 < s.alt_km < 520
    assert 7.5 < s.speed_km_s < 7.7
    assert prop.elevation(T0, PHNOM_PENH.lat_deg, PHNOM_PENH.lon_deg, 0) > 80


def test_ground_track_is_continuous():
    prop = Propagator(overhead_pass_elements(T0, 11.5, 104.9))
    pts = prop.ground_track(T0, 95, 30)
    for a, b in zip(pts, pts[1:], strict=False):
        dlat = abs(a.lat_deg - b.lat_deg)
        assert dlat < 2.5  # ~1.9 deg per 30 s at 7.6 km/s


def test_pass_prediction_finds_designed_pass():
    gs = GroundStation("test", 11.5564, 104.9282, 0.0, 10.0)
    prop = Propagator(overhead_pass_elements(T0 + timedelta(minutes=10), gs.lat_deg, gs.lon_deg))
    passes = predict_passes(prop, gs, T0, hours=24)
    assert passes, "expected at least one pass"
    first = passes[0]
    assert first.max_elevation_deg > 80
    assert 5 * 60 < first.duration_s < 12 * 60
    assert prop.elevation(first.aos, gs.lat_deg, gs.lon_deg, 0) == pytest.approx(10, abs=0.5)


def test_sun_at_march_equinox():
    jd, fr = julian_date(datetime(2024, 3, 20, 3, 6, tzinfo=UTC))
    u, dist = sun_vector_eci(jd, fr)
    assert math.degrees(math.asin(u[2])) == pytest.approx(0, abs=0.05)
    assert dist == pytest.approx(1.496e8, rel=0.01)


def test_cylindrical_eclipse():
    sun = np.array([1.0, 0.0, 0.0])
    assert in_eclipse(np.array([-7000.0, 0, 0]), sun)
    assert not in_eclipse(np.array([7000.0, 0, 0]), sun)
    assert not in_eclipse(np.array([-7000.0, 7000.0, 0]), sun)
