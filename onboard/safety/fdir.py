"""Fault Detection, Isolation and Recovery (FDIR) rules.

Each rule inspects a HealthSnapshot and yields Fault objects. The flight
application turns faults into mode transitions and inhibits (docs/safety.md §2).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from onboard.config import OnboardConfig


class FaultCode(StrEnum):
    LOW_BATTERY = "LOW_BATTERY"
    BATTERY_TEMP = "BATTERY_TEMP"
    PAYLOAD_OVERTEMP = "PAYLOAD_OVERTEMP"
    PAYLOAD_UNDERTEMP = "PAYLOAD_UNDERTEMP"
    CPU_OVERTEMP = "CPU_OVERTEMP"
    CAMERA_FAILURE = "CAMERA_FAILURE"
    STORAGE_FULL = "STORAGE_FULL"
    GNSS_NO_FIX = "GNSS_NO_FIX"
    WATCHDOG_RESET = "WATCHDOG_RESET"


class Action(StrEnum):
    NONE = "NONE"  # informational
    INHIBIT_IMAGING = "INHIBIT_IMAGING"
    ENTER_SAFE = "ENTER_SAFE"


@dataclass(frozen=True, slots=True)
class Fault:
    code: FaultCode
    action: Action
    detail: str


@dataclass(slots=True)
class HealthSnapshot:
    soc_pct: float
    battery_c: float
    payload_c: float
    cpu_c: float
    storage_free_bytes: int
    camera_failures: int
    gnss_fix: bool


def evaluate(h: HealthSnapshot, cfg: OnboardConfig) -> list[Fault]:
    faults: list[Fault] = []
    if h.soc_pct < cfg.safe_soc_pct:
        faults.append(Fault(FaultCode.LOW_BATTERY, Action.ENTER_SAFE, f"SoC {h.soc_pct:.1f}% < {cfg.safe_soc_pct}%"))
    if not cfg.battery_min_c <= h.battery_c <= cfg.battery_max_c:
        faults.append(Fault(FaultCode.BATTERY_TEMP, Action.ENTER_SAFE, f"battery {h.battery_c:.1f} C"))
    if h.payload_c > cfg.payload_max_c:
        faults.append(Fault(FaultCode.PAYLOAD_OVERTEMP, Action.ENTER_SAFE, f"payload {h.payload_c:.1f} C"))
    elif h.payload_c < cfg.payload_min_c:
        faults.append(Fault(FaultCode.PAYLOAD_UNDERTEMP, Action.INHIBIT_IMAGING, f"payload {h.payload_c:.1f} C"))
    if h.cpu_c > cfg.cpu_max_c:
        faults.append(Fault(FaultCode.CPU_OVERTEMP, Action.ENTER_SAFE, f"cpu {h.cpu_c:.1f} C"))
    if h.camera_failures >= cfg.camera_max_consecutive_failures:
        faults.append(Fault(FaultCode.CAMERA_FAILURE, Action.INHIBIT_IMAGING, f"{h.camera_failures} consecutive failures"))
    if h.storage_free_bytes < cfg.storage_reserve_bytes:
        faults.append(Fault(FaultCode.STORAGE_FULL, Action.INHIBIT_IMAGING, f"{h.storage_free_bytes} B free"))
    if not h.gnss_fix:
        faults.append(Fault(FaultCode.GNSS_NO_FIX, Action.NONE, "no GNSS fix"))
    return faults
