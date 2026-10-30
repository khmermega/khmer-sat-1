"""Energy-balance model: body-mounted solar faces, eclipse, battery and loads.

!!! Every numeric parameter below is a SIMULATION ASSUMPTION, NOT a component
specification. Real values are TBD in docs/hardware-bom.md and must replace
these once panels, battery and EPS are selected and characterised. !!!
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from shared.schemas import Mode

# Outward face normals of a 3U body (Z = long axis). Peak power per face at
# normal incidence is an ASSUMPTION for simulation only.
FACE_NORMALS = {
    "+X": np.array([1.0, 0.0, 0.0]),
    "-X": np.array([-1.0, 0.0, 0.0]),
    "+Y": np.array([0.0, 1.0, 0.0]),
    "-Y": np.array([0.0, -1.0, 0.0]),
    "+Z": np.array([0.0, 0.0, 1.0]),
    "-Z": np.array([0.0, 0.0, -1.0]),
}

# Generic Li-ion single-cell open-circuit voltage vs SoC (shape only).
_OCV_SOC = np.array([0, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100], dtype=float)
_OCV_V = np.array([3.00, 3.30, 3.45, 3.55, 3.62, 3.68, 3.74, 3.81, 3.89, 3.97, 4.06, 4.18])


@dataclass(slots=True)
class PowerAssumptions:
    face_peak_w: dict[str, float] = field(
        default_factory=lambda: {"+X": 6.0, "-X": 6.0, "+Y": 6.0, "-Y": 6.0, "+Z": 2.0, "-Z": 2.0}
    )
    battery_capacity_wh: float = 20.0
    cells_series: int = 2
    internal_resistance_ohm: float = 0.12
    charge_efficiency: float = 0.92
    mode_load_w: dict[Mode, float] = field(
        default_factory=lambda: {
            Mode.BOOT: 1.5,
            Mode.NOMINAL: 2.0,
            Mode.IMAGING: 4.5,
            Mode.DOWNLINK: 5.0,
            Mode.SAFE: 1.2,
            Mode.FAULT: 1.0,
        }
    )


@dataclass(slots=True)
class EnergyBalance:
    params: PowerAssumptions = field(default_factory=PowerAssumptions)
    soc_pct: float = 80.0
    solar_w: float = 0.0
    load_w: float = 0.0
    battery_a: float = 0.0
    battery_v: float = 0.0
    extra_drain_w: float = 0.0  # fault injection: parasitic load

    def ocv(self) -> float:
        return float(np.interp(self.soc_pct, _OCV_SOC, _OCV_V)) * self.params.cells_series

    def solar_power(self, sun_body: np.ndarray, sunlit: bool) -> float:
        if not sunlit:
            return 0.0
        return float(
            sum(max(0.0, float(n @ sun_body)) * self.params.face_peak_w[k] for k, n in FACE_NORMALS.items())
        )

    def step(self, dt: float, sun_body: np.ndarray, sunlit: bool, mode: Mode) -> None:
        self.solar_w = self.solar_power(sun_body, sunlit)
        self.load_w = self.params.mode_load_w[mode] + self.extra_drain_w
        net_w = self.solar_w - self.load_w
        if net_w > 0:
            net_w *= self.params.charge_efficiency
        cap_wh = self.params.battery_capacity_wh
        self.soc_pct = float(np.clip(self.soc_pct + net_w * dt / 3600.0 / cap_wh * 100.0, 0.0, 100.0))
        if self.soc_pct >= 100.0 and net_w > 0:
            net_w = 0.0  # charge regulator would shunt excess
        ocv = self.ocv()
        self.battery_a = net_w / ocv
        self.battery_v = ocv + self.battery_a * self.params.internal_resistance_ohm
