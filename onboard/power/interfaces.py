"""EPS (electrical power system) abstraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PowerReading:
    soc_pct: float
    battery_v: float
    battery_a: float
    solar_w: float
    load_w: float


class Eps(Protocol):
    def read(self) -> PowerReading: ...


class SimEps:
    """Reads the simulator's energy-balance model."""

    def __init__(self, world) -> None:  # simulator.world.SimWorld
        self._w = world

    def read(self) -> PowerReading:
        p = self._w.power
        return PowerReading(p.soc_pct, p.battery_v, p.battery_a, p.solar_w, p.load_w)
