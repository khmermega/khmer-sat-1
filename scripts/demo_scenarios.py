#!/usr/bin/env python3
"""Repeatable demonstration scenarios against a RUNNING ground station.

    uv run python scripts/demo_scenarios.py list
    uv run python scripts/demo_scenarios.py run imaging-pass
    uv run python scripts/demo_scenarios.py run all

Reads OPERATOR_TOKEN / ADMIN_TOKEN from the environment or .env. Each scenario
prints what it does and what to watch on the dashboard. Simulation mode only.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

BASE = os.environ.get("KS_API", "http://127.0.0.1:8000")
ROOT = Path(__file__).resolve().parent.parent


def _env(key: str) -> str:
    if os.environ.get(key):
        return os.environ[key]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    sys.exit(f"{key} not set (run scripts/init_env.py)")


def call(method: str, path: str, body: dict | None = None, admin: bool = False) -> dict:
    token = _env("ADMIN_TOKEN" if admin else "OPERATOR_TOKEN")
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "detail": e.read().decode()}


def wait_mode(mode: str, timeout: float = 120) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if call("GET", "/api/status").get("onboard", {}).get("mode") == mode:
            return True
        time.sleep(1)
    return False


def say(msg: str) -> None:
    print(f"  • {msg}", flush=True)


def reset() -> None:
    call("POST", "/api/sim/faults", {k: False for k in ("camera_failure", "gnss_outage", "fsw_hang", "link_down", "storage_fill", "db_outage")}
         | {"battery_drain_w": 0, "payload_heater_w": 0, "packet_loss": 0, "packet_corrupt": 0, "packet_duplicate": 0, "packet_delay_s": 0})


def imaging_pass() -> None:
    """Capture three images at different resolutions and watch them downlink."""
    for w, h in ((640, 480), (1280, 960), (1920, 1440)):
        r = call("POST", "/api/commands", {"type": "CAPTURE_IMAGE", "args": {"width": w, "height": h}})
        say(f"CAPTURE_IMAGE {w}x{h} -> {r.get('status', r)}")
        time.sleep(8)
    say("Watch: IMAGING -> NOMINAL -> DOWNLINK, gallery fills with SIMULATED images")


def lossy_link() -> None:
    """15% loss, 5% corruption, 10% duplication: selective-repeat still delivers verified images."""
    call("POST", "/api/sim/faults", {"packet_loss": 0.15, "packet_corrupt": 0.05, "packet_duplicate": 0.10, "packet_delay_s": 0.5})
    say("impairments on; capturing")
    call("POST", "/api/commands", {"type": "CAPTURE_IMAGE", "args": {"width": 1280, "height": 960}})
    time.sleep(45)
    reset()
    say("Watch: link panel CRC rejects / drops rise; image still arrives SHA-256 verified")


def watchdog_recovery() -> None:
    """Hang the flight software; the watchdog resets it; it boots conservatively into SAFE."""
    call("POST", "/api/sim/faults", {"fsw_hang": True})
    say("flight software hung - telemetry stops")
    ok = wait_mode("SAFE", 60)
    say(f"after watchdog reset the satellite is in SAFE: {ok}")
    r = call("POST", "/api/commands", {"type": "SET_MODE", "args": {"mode": "NOMINAL"}})
    say(f"operator returns to NOMINAL -> {r.get('status', r)}")


def power_emergency() -> None:
    """Parasitic 25 W load drains the battery -> autonomous SAFE; recovery is interlocked."""
    call("POST", "/api/sim/control", {"time_scale": 60})
    call("POST", "/api/sim/faults", {"battery_drain_w": 25})
    say("draining battery at 60x")
    say(f"entered SAFE: {wait_mode('SAFE', 180)}")
    call("POST", "/api/sim/faults", {"battery_drain_w": 0})
    r = call("POST", "/api/commands", {"type": "SET_MODE", "args": {"mode": "NOMINAL"}})
    say(f"immediate NOMINAL request -> {r.get('status')} (expect REJECTED: SoC below recovery threshold)")
    call("POST", "/api/sim/control", {"time_scale": 1})


def critical_command() -> None:
    """Two-step ARM/EXECUTE for a safety-critical REBOOT (admin only)."""
    arm = call("POST", "/api/commands/arm", {"type": "REBOOT", "args": {}}, admin=True)
    say(f"armed: {arm.get('arm_id', arm)}")
    r = call("POST", "/api/commands/execute", {"arm_id": arm.get("arm_id", "")}, admin=True)
    say(f"executed -> {r.get('status', r)}; watch BOOT -> NOMINAL")


def orbital_pass() -> None:
    """Switch to visibility-gated link and fast-forward to the next Phnom Penh pass."""
    call("POST", "/api/sim/control", {"link_mode": "orbital", "time_scale": 60})
    say("orbital link mode at 60x - telemetry only flows during passes (AOS/LOS events)")


SCENARIOS: dict[str, Callable[[], None]] = {
    "imaging-pass": imaging_pass,
    "lossy-link": lossy_link,
    "watchdog-recovery": watchdog_recovery,
    "power-emergency": power_emergency,
    "critical-command": critical_command,
    "orbital-pass": orbital_pass,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("list", "run"):
        print(__doc__)
        return 1
    if sys.argv[1] == "list":
        for name, fn in SCENARIOS.items():
            print(f"{name:20s} {fn.__doc__}")
        return 0
    names = list(SCENARIOS) if sys.argv[2:] == ["all"] else sys.argv[2:]
    for n in names:
        if n not in SCENARIOS:
            print(f"unknown scenario {n}")
            return 1
        print(f"\n▶ {n}: {SCENARIOS[n].__doc__}")
        reset()
        SCENARIOS[n]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
