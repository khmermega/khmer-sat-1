"""Lumped-capacitance thermal model (one node per component).

dT/dt = (P_internal + G_env·(T_env - T)) / C

All coefficients are SIMULATION ASSUMPTIONS chosen to give plausible-looking
trends - they are not derived from a thermal analysis (which is TBD, R-05).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ThermalNode:
    name: str
    temp_c: float
    capacity_j_per_k: float
    conductance_w_per_k: float

    def step(self, dt: float, power_w: float, env_c: float) -> None:
        d = (power_w + self.conductance_w_per_k * (env_c - self.temp_c)) / self.capacity_j_per_k
        self.temp_c += d * dt


@dataclass(slots=True)
class ThermalModel:
    sunlit_env_c: float = 30.0
    eclipse_env_c: float = -15.0
    env_c: float = 15.0
    env_tau_s: float = 900.0
    cpu: ThermalNode = field(default_factory=lambda: ThermalNode("cpu", 25.0, 60.0, 0.08))
    payload: ThermalNode = field(default_factory=lambda: ThermalNode("payload", 20.0, 120.0, 0.06))
    battery: ThermalNode = field(default_factory=lambda: ThermalNode("battery", 20.0, 250.0, 0.05))
    panel: ThermalNode = field(default_factory=lambda: ThermalNode("panel", 10.0, 80.0, 0.3))

    def step(self, dt: float, sunlit: bool, cpu_w: float, payload_w: float, battery_w: float, panel_absorbed_w: float) -> None:
        target = self.sunlit_env_c if sunlit else self.eclipse_env_c
        self.env_c += (target - self.env_c) * min(1.0, dt / self.env_tau_s)
        self.cpu.step(dt, cpu_w, self.env_c)
        self.payload.step(dt, payload_w, self.env_c)
        self.battery.step(dt, battery_w, self.env_c)
        self.panel.step(dt, panel_absorbed_w, self.env_c - 20.0)
