"""Standalone onboard runtime.

    uv run python -m onboard --sim [--minutes 10]

--sim runs the flight application against the simulator with a loopback link
and prints decoded housekeeping, which is useful for exercising the onboard
stack without the ground station. Hardware mode (Raspberry Pi adapters +
wired TCP link to the ground station) is milestone M3 - see
docs/hardware-bom.md §4 for the bench integration plan.
"""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from onboard.app import FlightSoftware
from onboard.communications.link import ChannelLink
from onboard.config import OnboardConfig
from onboard.logging_setup import configure
from onboard.simhal import build_sim_hal
from onboard.storage.manager import StorageManager
from shared.protocol import MessageType, PacketError, decode, decode_json, parse_key
from simulator.communications.channel import Channel
from simulator.world import SimWorld

log = logging.getLogger("onboard")


def run_sim(minutes: float) -> None:
    key_hex = os.environ.get("COMMAND_HMAC_KEY")
    key = parse_key(key_hex) if key_hex else secrets.token_bytes(32)
    world = SimWorld(datetime.now(UTC).replace(microsecond=0))
    up, down = Channel("uplink"), Channel("downlink")
    t = {"s": 0.0}
    link = ChannelLink(down, up, lambda: t["s"])
    cfg = OnboardConfig()
    storage = StorageManager(Path(tempfile.mkdtemp(prefix="khmersat-onboard-")), cfg.storage_capacity_bytes)
    fsw: FlightSoftware
    hal = build_sim_hal(world, lambda: True, lambda: fsw.mode, cfg.watchdog_timeout_s)
    fsw = FlightSoftware(hal, link, storage, key, cfg, simulated=True)
    fsw.boot(world.now)
    end = world.now + timedelta(minutes=minutes)
    hk_count = 0
    while world.now < end:
        world.step(1.0, fsw.mode)
        t["s"] += 1.0
        fsw.tick(world.now)
        for frame in down.receive(t["s"]):
            try:
                pkt = decode(frame)
            except PacketError:
                continue
            if pkt.msg_type is not MessageType.HOUSEKEEPING:
                continue
            hk_count += 1
            if hk_count % 15 == 1:  # ~every 30 s of simulated time
                hk = decode_json(pkt.payload)
                o, p = hk["orbit"], hk["power"]
                log.info(
                    "HK",
                    extra={"fields": {"mode": hk["mode"], "lat": o["lat_deg"], "lon": o["lon_deg"], "soc": p["soc_pct"], "sunlit": o["sunlit"]}},
                )


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m onboard")
    ap.add_argument("--sim", action="store_true", help="run against the simulator (default and only mode for now)")
    ap.add_argument("--minutes", type=float, default=10.0, help="simulated minutes to run")
    args = ap.parse_args()
    configure("INFO", json_output=True)
    run_sim(args.minutes)


if __name__ == "__main__":
    main()
