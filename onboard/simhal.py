"""Build a HAL whose adapters are backed by the simulator (SIMULATION mode)."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from onboard.app import Hal
from onboard.camera.mock import MockCamera
from onboard.power.interfaces import SimEps
from onboard.safety.watchdog import SimWatchdogMCU
from onboard.sensors.sim import SimAttitudeSource, SimGnss, SimImu, SimMagnetometer, SimTemperatures
from shared.schemas import Mode, OrbitState
from simulator.world import SimWorld

_CPU_BASE = {Mode.BOOT: 70, Mode.NOMINAL: 18, Mode.IMAGING: 65, Mode.DOWNLINK: 45, Mode.SAFE: 8, Mode.FAULT: 5}


class SimNavigation:
    def __init__(self, world: SimWorld) -> None:
        self._w = world

    def read(self) -> OrbitState:
        o = self._w.orbit
        return OrbitState(
            lat_deg=round(o.lat_deg, 4),
            lon_deg=round(o.lon_deg, 4),
            alt_km=round(o.alt_km, 2),
            speed_km_s=round(o.speed_km_s, 3),
            sunlit=o.sunlit,
            gs_elevation_deg=round(self._w.gs_el, 2),
            gs_visible=self._w.gs_visible,
        )


def build_sim_hal(world: SimWorld, link_up: Callable[[], bool], mode_fn: Callable[[], Mode], watchdog_timeout_s: float) -> Hal:
    rng = np.random.default_rng(99)
    o = lambda: (world.orbit.lat_deg, world.orbit.lon_deg, world.orbit.sunlit)  # noqa: E731
    return Hal(
        imu=SimImu(world),
        mag=SimMagnetometer(world),
        gnss=SimGnss(world),
        temps=SimTemperatures(world),
        attitude=SimAttitudeSource(world),
        eps=SimEps(world),
        camera=MockCamera(position_fn=o, fail_fn=lambda: world.faults.camera_failure),
        watchdog=SimWatchdogMCU(watchdog_timeout_s),
        navigation=SimNavigation(world),
        link_up=link_up,
        cpu_load=lambda: float(np.clip(_CPU_BASE[mode_fn()] + rng.normal(0, 4), 0, 100)),
    )
