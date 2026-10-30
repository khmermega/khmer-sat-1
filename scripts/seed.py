#!/usr/bin/env python3
"""Seed the ground database with a realistic simulated history.

Runs the full simulation (flight software + link + ground segment) faster than
real time for --hours of simulated time, ending at "now", and issues a
representative command plan (captures, mode changes, one fault excursion).
Everything produced is SIMULATED and labelled as such.

    uv run python scripts/seed.py --hours 3
Then start the backend - it resumes simulated time after the seeded history.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "ground-station" / "backend")]

from app.config import get_settings  # noqa: E402
from app.db import init_db, make_engine  # noqa: E402
from app.engine import SimulationEngine  # noqa: E402
from app.main import _load_key, _make_object_store  # noqa: E402
from app.persistence import Persistence  # noqa: E402
from shared.schemas import CommandType  # noqa: E402

STEP_S = 10.0  # simulated seconds per engine step


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=3.0, help="simulated hours of history to generate (default 3)")
    args = ap.parse_args()
    if not 0 < args.hours <= 48:
        ap.error("--hours must be within (0, 48]")

    s = get_settings()
    persistence = Persistence(init_db(make_engine(s.database_url)))
    start = datetime.now(UTC) - timedelta(hours=args.hours)
    eng = SimulationEngine(s, _load_key(s), persistence, _make_object_store(s), start=start)
    eng.time_scale = STEP_S
    total_steps = int(args.hours * 3600 / STEP_S)

    # (fraction of run, action) - a small, readable operations plan.
    plan = [
        (0.05, lambda: eng.ground.send_command(CommandType.PING, {}, "seed")),
        (0.10, lambda: eng.ground.send_command(CommandType.CAPTURE_IMAGE, {"width": 1280, "height": 960}, "seed")),
        (0.25, lambda: eng.ground.send_command(CommandType.CAPTURE_IMAGE, {"width": 640, "height": 480}, "seed")),
        (0.40, lambda: eng.ground.send_command(CommandType.SET_MODE, {"mode": "SAFE"}, "seed")),
        (0.45, lambda: eng.ground.send_command(CommandType.SET_MODE, {"mode": "NOMINAL"}, "seed")),
        (0.55, lambda: setattr(eng.world.faults, "payload_heater_w", 6.0)),
        (0.70, lambda: setattr(eng.world.faults, "payload_heater_w", 0.0)),
        (0.85, lambda: eng.ground.send_command(CommandType.SET_MODE, {"mode": "NOMINAL"}, "seed")),
        (0.90, lambda: eng.ground.send_command(CommandType.CAPTURE_IMAGE, {}, "seed")),
    ]
    t0 = time.time()
    for i in range(total_steps):
        frac = i / total_steps
        while plan and plan[0][0] <= frac:
            plan.pop(0)[1]()
        eng.step(1.0)
        if i % max(1, total_steps // 20) == 0:
            print(f"  {100 * frac:5.1f}%  sim {eng.world.now:%Y-%m-%d %H:%M:%S}Z  mode {eng.fsw.mode.value}")
    persistence.flush()
    print(
        f"seeded {len(eng.ground.telemetry)} housekeeping frames (last buffer), "
        f"{len(eng.ground.images)} images, {len(eng.ground.events)} events in {time.time() - t0:.1f} s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
