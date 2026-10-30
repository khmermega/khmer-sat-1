"""Mock sensor adapters backed by the simulator (simulated truth + noise)."""

from __future__ import annotations

import numpy as np

from simulator.world import SimWorld

from .interfaces import GnssFix, Temperatures


class SimImu:
    """Gyro = true body rate + constant bias + white noise (illustrative values)."""

    def __init__(self, world: SimWorld, seed: int = 11, bias_dps: float = 0.05, noise_dps: float = 0.02) -> None:
        self._w = world
        self._rng = np.random.default_rng(seed)
        self._bias = self._rng.normal(0, bias_dps, 3)
        self._noise = noise_dps

    def read_rate_dps(self) -> tuple[float, float, float]:
        true = np.degrees(self._w.attitude.omega)
        v = true + self._bias + self._rng.normal(0, self._noise, 3)
        return tuple(float(x) for x in v)  # type: ignore[return-value]


class SimMagnetometer:
    def __init__(self, world: SimWorld, seed: int = 12, noise_ut: float = 0.3) -> None:
        self._w = world
        self._rng = np.random.default_rng(seed)
        self._noise = noise_ut

    def read_ut(self) -> tuple[float, float, float]:
        v = self._w.mag_body_ut() + self._rng.normal(0, self._noise, 3)
        return tuple(float(x) for x in v)  # type: ignore[return-value]


class SimGnss:
    def __init__(self, world: SimWorld, seed: int = 13, noise_deg: float = 0.0001) -> None:
        self._w = world
        self._rng = np.random.default_rng(seed)
        self._noise = noise_deg

    def read(self) -> GnssFix:
        if self._w.faults.gnss_outage:
            return GnssFix(fix=False, sats=0)
        o = self._w.orbit
        return GnssFix(
            fix=True,
            sats=int(self._rng.integers(6, 12)),
            lat_deg=o.lat_deg + float(self._rng.normal(0, self._noise)),
            lon_deg=o.lon_deg + float(self._rng.normal(0, self._noise)),
            alt_km=o.alt_km + float(self._rng.normal(0, 0.01)),
        )


class SimTemperatures:
    def __init__(self, world: SimWorld) -> None:
        self._w = world

    def read(self) -> Temperatures:
        t = self._w.thermal
        return Temperatures(t.cpu.temp_c, t.payload.temp_c, t.battery.temp_c, t.panel.temp_c)


class SimAttitudeSource:
    def __init__(self, world: SimWorld) -> None:
        self._w = world

    def read_q(self) -> tuple[float, float, float, float]:
        return tuple(float(x) for x in self._w.attitude.q)  # type: ignore[return-value]
