"""Onboard configuration and safety thresholds.

Thresholds are prototype defaults for the simulator and bench. Flight values
must come from component datasheets and test data (TBD, docs/safety.md §2).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class OnboardConfig:
    sat_id: int = 0x4B31
    telemetry_period_s: float = 2.0
    boot_duration_s: float = 5.0
    # --- power interlocks (state of charge, %) ---
    safe_soc_pct: float = 30.0  # below -> autonomous SAFE
    recover_soc_pct: float = 45.0  # SAFE -> NOMINAL allowed only above this
    imaging_min_soc_pct: float = 50.0
    downlink_min_soc_pct: float = 40.0
    # --- thermal limits (deg C) ---
    payload_min_c: float = -10.0
    payload_max_c: float = 45.0
    cpu_max_c: float = 75.0
    battery_min_c: float = 0.0
    battery_max_c: float = 45.0
    # --- camera ---
    camera_width: int = 1280
    camera_height: int = 960
    jpeg_quality: int = 85
    camera_max_consecutive_failures: int = 3
    imaging_hold_s: float = 5.0
    # --- storage / downlink ---
    storage_capacity_bytes: int = 64 * 1024 * 1024
    storage_reserve_bytes: int = 1 * 1024 * 1024
    chunk_size: int = 3072
    chunks_per_tick: int = 40
    transfer_ack_timeout_s: float = 60.0
    transfer_max_retries: int = 3
    auto_downlink: bool = True
    # --- watchdog ---
    watchdog_timeout_s: float = 10.0
    # --- commanding ---
    replay_window_s: float = 30.0
