"""Quaternion utilities. Convention: q = [w, x, y, z], Hamilton product,
q rotates vectors from the BODY frame into the reference (ECI/TEME) frame:
    v_ref = q ⊗ v_body ⊗ q*
"""

from __future__ import annotations

import math

import numpy as np


def normalize(q: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(q))
    if n == 0.0:
        raise ValueError("zero quaternion")
    q = np.asarray(q, dtype=float) / n
    return q if q[0] >= 0 else -q  # canonical hemisphere for telemetry continuity


def multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ]
    )


def conjugate(q: np.ndarray) -> np.ndarray:
    return np.array([q[0], -q[1], -q[2], -q[3]])


def rotate(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Rotate body vector v into the reference frame."""
    p = np.concatenate(([0.0], v))
    return multiply(multiply(q, p), conjugate(q))[1:]


def rotate_inverse(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Rotate reference-frame vector v into the body frame."""
    return rotate(conjugate(q), v)


def from_axis_angle(axis: np.ndarray, angle_rad: float) -> np.ndarray:
    axis = np.asarray(axis, dtype=float)
    axis = axis / np.linalg.norm(axis)
    s = math.sin(angle_rad / 2)
    return np.array([math.cos(angle_rad / 2), *(axis * s)])


def integrate(q: np.ndarray, omega_body_rad_s: np.ndarray, dt: float) -> np.ndarray:
    """Exact integration for constant body rate over dt (q_dot = ½ q ⊗ [0, ω])."""
    w = np.asarray(omega_body_rad_s, dtype=float)
    rate = float(np.linalg.norm(w))
    if rate * dt < 1e-12:
        return normalize(q)
    dq = from_axis_angle(w / rate, rate * dt)
    return normalize(multiply(q, dq))


def from_matrix(m: np.ndarray) -> np.ndarray:
    """Rotation matrix (columns = body axes expressed in reference frame) -> quaternion."""
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        q = [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s]
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s]
    return normalize(np.array(q))


def angle_between(a: np.ndarray, b: np.ndarray) -> float:
    """Smallest rotation angle (rad) between two attitudes."""
    d = abs(float(np.dot(normalize(a), normalize(b))))
    return 2.0 * math.acos(min(1.0, d))
