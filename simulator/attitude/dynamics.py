"""Bench-only KINEMATIC attitude simulation.

IMPORTANT LIMITATION: there is no actuator model, no inertia/torque dynamics
and no control law here. The two behaviours are:

- TUMBLE: constant-magnitude body rate with an exponential rate decay used as a
  visual stand-in for detumbling. It is NOT a B-dot controller.
- IDEAL_NADIR: the attitude is *set* kinematically to the LVLH (nadir-pointing)
  frame. It represents "what the camera would see if pointing were perfect",
  NOT a claim that KHMER-SAT 1 can achieve it.

A flight-capable ADCS requires validated sensor/actuator models (risk R-07).
"""

from __future__ import annotations

from enum import StrEnum

import numpy as np

from . import quaternion as qt


class AttitudeBehaviour(StrEnum):
    TUMBLE = "TUMBLE"
    IDEAL_NADIR = "IDEAL_NADIR"


def lvlh_quaternion(r_eci: np.ndarray, v_eci: np.ndarray) -> np.ndarray:
    """Body axes: +Z nadir (camera boresight), +X along-track, +Y completes the triad."""
    z = -r_eci / np.linalg.norm(r_eci)
    y = np.cross(z, v_eci)
    y /= np.linalg.norm(y)
    x = np.cross(y, z)
    return qt.from_matrix(np.column_stack([x, y, z]))


class AttitudeSim:
    def __init__(self, seed: int = 1, initial_rate_dps: float = 3.0, decay_tau_s: float = 1800.0) -> None:
        rng = np.random.default_rng(seed)
        axis = rng.normal(size=3)
        self.q = qt.normalize(np.array([1.0, 0.0, 0.0, 0.0]))
        self.omega = axis / np.linalg.norm(axis) * np.radians(initial_rate_dps)
        self.decay_tau_s = decay_tau_s
        self.behaviour = AttitudeBehaviour.TUMBLE

    def step(self, dt: float, r_eci: np.ndarray, v_eci: np.ndarray) -> None:
        if self.behaviour is AttitudeBehaviour.IDEAL_NADIR:
            q_new = lvlh_quaternion(r_eci, v_eci)
            # Derive the body rate from consecutive attitudes for telemetry.
            dq = qt.multiply(qt.conjugate(self.q), q_new)
            dq = qt.normalize(dq)
            ang = 2.0 * np.arccos(np.clip(dq[0], -1.0, 1.0))
            s = np.sqrt(max(1e-12, 1.0 - dq[0] ** 2))
            self.omega = (dq[1:] / s) * (ang / dt) if dt > 0 and ang > 1e-9 else np.zeros(3)
            self.q = q_new
        else:
            self.q = qt.integrate(self.q, self.omega, dt)
            if self.decay_tau_s > 0:
                self.omega = self.omega * np.exp(-dt / self.decay_tau_s)
