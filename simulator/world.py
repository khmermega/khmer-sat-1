"""SimWorld: the simulated physical environment of the spacecraft.

Owns the "truth" state (orbit, attitude, power, thermal). Onboard software
never reads this directly - it goes through sensor/EPS adapters in
onboard/sensors/sim.py and onboard/power/sim.py, exactly as it would go
through hardware drivers. That keeps flight code identical between modes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from shared.schemas import Mode
from simulator.attitude import quaternion as qt
from simulator.attitude.dynamics import AttitudeBehaviour, AttitudeSim
from simulator.environment.magnetic import dipole_field_ecef
from simulator.environment.thermal import ThermalModel
from simulator.orbit.elements import SyntheticElements, overhead_pass_elements
from simulator.orbit.frames import ensure_utc, gmst_rad, julian_date, look_angles, rot_z
from simulator.orbit.propagator import OrbitSample, Propagator
from simulator.orbit.visibility import PHNOM_PENH, GroundStation
from simulator.power.eps import EnergyBalance

_CPU_W = {Mode.BOOT: 1.2, Mode.NOMINAL: 1.0, Mode.IMAGING: 1.8, Mode.DOWNLINK: 1.6, Mode.SAFE: 0.6, Mode.FAULT: 0.5}
_PAYLOAD_W = {Mode.IMAGING: 1.5}


@dataclass
class FaultInjection:
    """Simulation-only fault switches (exposed via /api/sim/faults)."""

    camera_failure: bool = False
    battery_drain_w: float = 0.0
    payload_heater_w: float = 0.0  # forces an over-temperature
    gnss_outage: bool = False
    fsw_hang: bool = False  # flight software stops kicking the watchdog
    link_down: bool = False

    def as_dict(self) -> dict[str, float | bool]:
        return dict(self.__dict__)


@dataclass
class SimWorld:
    start: datetime
    ground_station: GroundStation = PHNOM_PENH
    pass_offset_min: float = 4.0
    seed: int = 7
    elements: SyntheticElements | None = None
    faults: FaultInjection = field(default_factory=FaultInjection)

    def __post_init__(self) -> None:
        self.start = ensure_utc(self.start)
        if self.elements is None:
            # Demo orbit: overhead pass of the ground station `pass_offset_min` after start.
            epoch = self.start + timedelta(minutes=self.pass_offset_min)
            self.elements = overhead_pass_elements(epoch, self.ground_station.lat_deg, self.ground_station.lon_deg)
        self.propagator = Propagator(self.elements)
        self.attitude = AttitudeSim(seed=self.seed)
        self.power = EnergyBalance()
        self.thermal = ThermalModel()
        self.now = self.start
        self.orbit: OrbitSample = self.propagator.sample(self.now)
        self.gs_az, self.gs_el, self.gs_range_km = self._look()

    def _look(self) -> tuple[float, float, float]:
        gs = self.ground_station
        return look_angles(self.orbit.r_ecef_km, gs.lat_deg, gs.lon_deg, gs.alt_km)

    @property
    def gs_visible(self) -> bool:
        return self.gs_el >= self.ground_station.min_elevation_deg

    def sun_body(self) -> np.ndarray:
        return qt.rotate_inverse(self.attitude.q, self.orbit.sun_teme)

    def mag_body_ut(self) -> np.ndarray:
        jd, fr = julian_date(self.now)
        b_eci = rot_z(gmst_rad(jd, fr)).T @ dipole_field_ecef(self.orbit.r_ecef_km)
        return qt.rotate_inverse(self.attitude.q, b_eci)

    def step(self, dt: float, mode: Mode) -> None:
        """Advance simulated truth by dt seconds given the onboard operating mode."""
        if dt <= 0:
            return
        self.now = self.now + timedelta(seconds=dt)
        self.orbit = self.propagator.sample(self.now)
        self.attitude.behaviour = (
            AttitudeBehaviour.IDEAL_NADIR if mode in (Mode.IMAGING, Mode.NOMINAL, Mode.DOWNLINK) else AttitudeBehaviour.TUMBLE
        )
        self.attitude.step(dt, self.orbit.r_teme_km, self.orbit.v_teme_km_s)
        self.power.extra_drain_w = self.faults.battery_drain_w
        self.power.step(dt, self.sun_body(), self.orbit.sunlit, mode)
        self.thermal.step(
            dt,
            self.orbit.sunlit,
            cpu_w=_CPU_W[mode],
            payload_w=_PAYLOAD_W.get(mode, 0.2) + self.faults.payload_heater_w,
            battery_w=abs(self.power.battery_a) ** 2 * self.power.params.internal_resistance_ohm,
            panel_absorbed_w=self.power.solar_w * 0.6,
        )
        self.gs_az, self.gs_el, self.gs_range_km = self._look()
