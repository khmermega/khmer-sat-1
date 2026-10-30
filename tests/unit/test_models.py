"""REQ: FR-ADC-001..003, FR-PWR-001..003, FR-TTC-007 - attitude, power, link channel, thermal."""

import math

import numpy as np
import pytest

from shared.protocol import MessageType, Packet, PacketError, decode, encode
from shared.schemas import Mode
from simulator.attitude import quaternion as qt
from simulator.attitude.dynamics import lvlh_quaternion
from simulator.communications.channel import Channel, Impairments
from simulator.environment.magnetic import dipole_field_ecef, field_magnitude_ut
from simulator.orbit.frames import geodetic_to_ecef
from simulator.power.eps import EnergyBalance


def test_quaternion_rotate_roundtrip():
    q = qt.from_axis_angle(np.array([1.0, 2.0, 3.0]), 0.7)
    v = np.array([0.3, -1.2, 2.0])
    assert np.allclose(qt.rotate_inverse(q, qt.rotate(q, v)), v)
    assert np.linalg.norm(q) == pytest.approx(1.0)


def test_integrate_quarter_turn_about_z():
    q = np.array([1.0, 0, 0, 0])
    for _ in range(90):
        q = qt.integrate(q, np.radians([0, 0, 1.0]), 1.0)
    assert np.allclose(qt.rotate(q, np.array([1.0, 0, 0])), [0, 1, 0], atol=1e-9)


def test_from_matrix_identity_and_angle():
    assert np.allclose(qt.from_matrix(np.eye(3)), [1, 0, 0, 0])
    a = qt.from_axis_angle(np.array([0, 1.0, 0]), 0.5)
    assert qt.angle_between(np.array([1.0, 0, 0, 0]), a) == pytest.approx(0.5)


def test_lvlh_boresight_points_nadir():
    r = np.array([6878.0, 0, 0])
    v = np.array([0, 7.6, 0])
    q = lvlh_quaternion(r, v)
    boresight = qt.rotate(q, np.array([0, 0, 1.0]))
    assert np.allclose(boresight, -r / np.linalg.norm(r))


def test_dipole_field_magnitude_order():
    b = np.linalg.norm(dipole_field_ecef(geodetic_to_ecef(0, 0, 500)))
    assert 15 < b < 45  # microtesla at LEO
    assert field_magnitude_ut(90, 0) == pytest.approx(2 * field_magnitude_ut(0, 0))


def test_battery_discharges_in_eclipse_and_charges_in_sun():
    eb = EnergyBalance(soc_pct=50.0)
    for _ in range(600):
        eb.step(1.0, np.array([1.0, 0, 0]), sunlit=False, mode=Mode.NOMINAL)
    assert eb.soc_pct < 50 and eb.battery_a < 0 and eb.solar_w == 0
    soc = eb.soc_pct
    for _ in range(600):
        eb.step(1.0, np.array([1.0, 0, 0]), sunlit=True, mode=Mode.NOMINAL)
    assert eb.soc_pct > soc and eb.battery_a > 0


def test_soc_clamped_and_ocv_monotonic():
    eb = EnergyBalance(soc_pct=1.0)
    eb.extra_drain_w = 50
    for _ in range(3600):
        eb.step(1.0, np.zeros(3), sunlit=False, mode=Mode.IMAGING)
    assert eb.soc_pct == 0.0
    volts = []
    for s in range(0, 101, 10):
        eb.soc_pct = s
        volts.append(eb.ocv())
    assert volts == sorted(volts)


def test_solar_power_cosine_and_sun_angle():
    eb = EnergyBalance()
    assert eb.solar_power(np.array([1.0, 0, 0]), True) == pytest.approx(6.0)
    s45 = np.array([math.sqrt(0.5), math.sqrt(0.5), 0])
    assert eb.solar_power(s45, True) == pytest.approx(12 * math.sqrt(0.5))


def _frame(seq):
    return encode(Packet(1, MessageType.EVENT, seq, 1, b"{}"))


def test_channel_loss_and_down():
    ch = Channel("t", Impairments(loss=1.0), seed=1)
    ch.send(_frame(1), 0)
    assert ch.receive(1) == [] and ch.stats.dropped == 1
    ch2 = Channel("t2", seed=1, up=False)
    ch2.send(_frame(1), 0)
    assert ch2.receive(1) == [] and ch2.stats.blocked == 1


def test_channel_duplicate_delay_and_corruption():
    ch = Channel("t", Impairments(duplicate=1.0, delay_s=2.0), seed=1)
    ch.send(_frame(1), 0)
    assert ch.receive(1.9) == []
    assert len(ch.receive(2.0)) == 2
    bad = Channel("c", Impairments(corrupt=1.0), seed=3)
    for i in range(50):
        bad.send(_frame(i), 0)
    for f in bad.receive(0):
        with pytest.raises(PacketError):
            decode(f)


def test_impairment_validation():
    with pytest.raises(ValueError):
        Impairments(loss=1.5).validate()
