"""Hardware abstraction interfaces for sensors.

Flight code depends only on these Protocols. Implementations:
- onboard/sensors/sim.py    : backed by simulator.world.SimWorld
- onboard/sensors/nmea.py   : GNSS NMEA parsing for a real serial receiver
- real IMU/magnetometer I2C drivers: TBD once parts are selected (hardware-bom.md)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class SensorError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class GnssFix:
    fix: bool
    sats: int
    lat_deg: float | None = None
    lon_deg: float | None = None
    alt_km: float | None = None


@dataclass(frozen=True, slots=True)
class Temperatures:
    cpu_c: float
    payload_c: float
    battery_c: float
    panel_c: float


class Imu(Protocol):
    def read_rate_dps(self) -> tuple[float, float, float]: ...


class Magnetometer(Protocol):
    def read_ut(self) -> tuple[float, float, float]: ...


class Gnss(Protocol):
    def read(self) -> GnssFix: ...


class TemperatureSensors(Protocol):
    def read(self) -> Temperatures: ...


class AttitudeSource(Protocol):
    """Attitude quaternion source. In simulation this is SIMULATED TRUTH;
    no onboard attitude estimator exists yet (milestone M5)."""

    def read_q(self) -> tuple[float, float, float, float]: ...
