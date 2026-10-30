"""SimulationEngine: runs the simulated spacecraft (world + flight software)
and the ground segment, connected through impaired simulated channels.

Threading model: ``step()`` runs in a worker thread (it does CPU-heavy work
such as JPEG encoding). API handlers never touch engine internals directly;
they enqueue work with ``submit()`` and read the immutable ``snapshot``.
"""

from __future__ import annotations

import concurrent.futures as cf
import logging
import math
import queue
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from onboard.app import FlightSoftware
from onboard.communications.link import ChannelLink
from onboard.config import OnboardConfig
from onboard.simhal import build_sim_hal
from onboard.storage.manager import StorageManager
from shared import SATELLITE_ID, SATELLITE_NAME
from shared.protocol import PROTOCOL_VERSION
from simulator.communications.channel import Channel, Impairments
from simulator.orbit.visibility import GroundStation
from simulator.world import SimWorld

from .config import LinkMode, Settings
from .ground import GroundSegment
from .objectstore import ObjectStore
from .persistence import Persistence

log = logging.getLogger("ground.engine")

MAX_SUBSTEP_S = 1.0


class SimulationEngine:
    def __init__(
        self,
        settings: Settings,
        key: bytes,
        persistence: Persistence,
        objects: ObjectStore,
        start: datetime | None = None,
        publish: Callable[[str, dict], None] | None = None,
    ) -> None:
        self.settings = settings
        self.time_scale = settings.sim_time_scale
        self.paused = False
        self.link_mode = settings.sim_link_mode
        self.station = GroundStation(settings.gs_name, settings.gs_lat, settings.gs_lon, settings.gs_alt_m / 1000.0, settings.gs_min_el)
        start = (start or datetime.now(UTC)).replace(microsecond=0)
        self.world = SimWorld(start, self.station, settings.sim_pass_offset_min, settings.sim_seed)
        self.sim_t = 0.0
        self.uplink = Channel("uplink", Impairments(), seed=settings.sim_seed + 1)
        self.downlink = Channel("downlink", Impairments(), seed=settings.sim_seed + 2)
        clock_s = lambda: self.sim_t  # noqa: E731
        self.cfg = OnboardConfig(storage_capacity_bytes=settings.onboard_storage_mb * 1024 * 1024)
        self.storage = StorageManager(Path(settings.onboard_data_dir), self.cfg.storage_capacity_bytes)
        self.fsw: FlightSoftware
        hal = build_sim_hal(self.world, self._link_up, lambda: self.fsw.mode, self.cfg.watchdog_timeout_s)
        self.fsw = FlightSoftware(hal, ChannelLink(self.downlink, self.uplink, clock_s), self.storage, key, self.cfg, simulated=True)
        self.persistence = persistence
        self.ground = GroundSegment(
            key,
            ChannelLink(self.uplink, self.downlink, clock_s),
            lambda: self.world.now,
            persistence,
            objects,
            settings.command_ack_timeout_s,
            publish,
        )
        persistence.on_status_change = self._on_db_status
        self.storage.clear_dummy()
        self._work: queue.Queue[tuple[Callable[[], Any], cf.Future]] = queue.Queue()
        self._was_visible = self.world.gs_visible
        self._link_was_up = self._link_up()
        self.storage_fill = False
        self.snapshot: dict[str, Any] = {}
        self.fsw.boot(self.world.now, "POWER_ON")
        self.ground.ground_event("INFO", "ground", "GS_START", f"ground segment started in SIMULATION mode ({self.link_mode.value} link)")
        self._build_snapshot()

    # ----------------------------------------------------------------- link
    def _link_up(self) -> bool:
        if self.world.faults.link_down:
            return False
        return self.link_mode is LinkMode.BENCH or self.world.gs_visible

    def _on_db_status(self, ok: bool) -> None:
        if ok:
            self.ground.ground_event("INFO", "ground", "DB_RESTORED", f"database restored; flushing {self.persistence.pending} buffered records")
        else:
            self.ground.ground_event("CRITICAL", "ground", "DB_OUTAGE", "database unavailable - buffering records in memory")

    # ------------------------------------------------------------- commands
    def submit(self, fn: Callable[[], Any]) -> cf.Future:
        """Schedule ``fn`` to run on the engine thread at the start of the next step."""
        fut: cf.Future = cf.Future()
        self._work.put((fn, fut))
        return fut

    def _drain_work(self) -> None:
        while True:
            try:
                fn, fut = self._work.get_nowait()
            except queue.Empty:
                return
            if fut.set_running_or_notify_cancel():
                try:
                    fut.set_result(fn())
                except Exception as exc:  # noqa: BLE001
                    fut.set_exception(exc)

    # ------------------------------------------------------------- stepping
    def step(self, real_dt: float) -> None:
        self._drain_work()
        if not self.paused:
            total = real_dt * self.time_scale
            n = max(1, math.ceil(total / MAX_SUBSTEP_S))
            for _ in range(n):
                self._substep(total / n)
        self.persistence.flush()
        self._build_snapshot()

    def _substep(self, dt: float) -> None:
        w = self.world
        w.step(dt, self.fsw.mode)
        self.sim_t += dt
        now = w.now
        up = self._link_up()
        self.uplink.up = self.downlink.up = up
        if up != self._link_was_up:
            self.ground.ground_event("INFO" if up else "WARNING", "comms", "LINK_UP" if up else "LINK_DOWN", "ground link acquired" if up else "ground link lost")
            self._link_was_up = up
        if w.gs_visible != self._was_visible:
            self._was_visible = w.gs_visible
            self.ground.ground_event("INFO", "orbit", "AOS" if w.gs_visible else "LOS", f"{'acquisition' if w.gs_visible else 'loss'} of signal at {self.station.name}")
        if not w.faults.fsw_hang:
            self.fsw.tick(now)
        if self.fsw.hal.watchdog.poll(self.fsw._t(now)):
            w.faults.fsw_hang = False  # a reset clears the (transient) hang
            self.ground.ground_event("CRITICAL", "watchdog", "WATCHDOG_RESET", "watchdog MCU reset the onboard computer (heartbeat lost)")
            self.fsw.reset(now, "WATCHDOG")
        self.ground.process_rx()
        self.ground.check_timeouts()

    # ---------------------------------------------------------- fault injection
    def set_storage_fill(self, enabled: bool) -> None:
        self.storage_fill = enabled
        if enabled:
            self.storage.clear_dummy()
            self.storage.fill_dummy(max(0, self.storage.free_bytes() - 256 * 1024))
        else:
            self.storage.clear_dummy()

    def set_impairments(self, imp: Impairments) -> None:
        imp.validate()
        self.uplink.impairments = Impairments(imp.loss, imp.duplicate, imp.corrupt, imp.delay_s)
        self.downlink.impairments = Impairments(imp.loss, imp.duplicate, imp.corrupt, imp.delay_s)

    def faults_dict(self) -> dict[str, Any]:
        imp = self.downlink.impairments
        return {
            **self.world.faults.as_dict(),
            "storage_fill": self.storage_fill,
            "db_outage": self.persistence.simulate_outage,
            "packet_loss": imp.loss,
            "packet_duplicate": imp.duplicate,
            "packet_corrupt": imp.corrupt,
            "packet_delay_s": imp.delay_s,
        }

    # -------------------------------------------------------------- snapshot
    def _build_snapshot(self) -> None:
        w, g, fsw = self.world, self.ground, self.fsw
        hk_age = (w.now - g.last_rx_utc).total_seconds() if g.last_rx_utc else None
        self.snapshot = {
            "satellite": {"name": SATELLITE_NAME, "id": SATELLITE_ID, "protocol_version": PROTOCOL_VERSION},
            "gs_mode": "SIMULATION",
            "sim": {
                "utc": w.now.isoformat(),
                "start_utc": w.start.isoformat(),
                "time_scale": self.time_scale,
                "paused": self.paused,
                "link_mode": self.link_mode.value,
                "elements_label": w.elements.label,
            },
            "ground_station": {
                "name": self.station.name,
                "lat_deg": self.station.lat_deg,
                "lon_deg": self.station.lon_deg,
                "alt_km": self.station.alt_km,
                "min_elevation_deg": self.station.min_elevation_deg,
            },
            "link": {
                "up": self._link_up(),
                "gs_visible": w.gs_visible,
                "elevation_deg": round(w.gs_el, 2),
                "azimuth_deg": round(w.gs_az, 2),
                "range_km": round(w.gs_range_km, 1),
                "last_rx_utc": g.last_rx_utc.isoformat() if g.last_rx_utc else None,
                "telemetry_age_s": round(hk_age, 1) if hk_age is not None else None,
                "ground": dict(g.stats),
                "uplink": _stats(self.uplink),
                "downlink": _stats(self.downlink),
                "pending_image_reassembly": len(g.partials),
            },
            "onboard": {
                "mode": fsw.mode.value,
                "downlink_queue": len(fsw.downlink),
                "scheduled_captures": len(fsw.captures),
                "camera": {"width": fsw.camera_cfg.width, "height": fsw.camera_cfg.height, "jpeg_quality": fsw.camera_cfg.jpeg_quality},
                "watchdog_resets": fsw.hal.watchdog.reset_count,
                "stats": {k: v for k, v in vars(fsw.stats).items() if k != "task_errors"},
            },
            "database": {"ok": self.persistence.db_ok, "pending_writes": self.persistence.pending, "dropped": self.persistence.dropped},
            "faults": self.faults_dict(),
            "telemetry": g.latest_hk,
        }


def _stats(ch: Channel) -> dict[str, int]:
    s = ch.stats
    return {
        "sent": s.sent,
        "delivered": s.delivered,
        "dropped": s.dropped,
        "duplicated": s.duplicated,
        "corrupted": s.corrupted,
        "blocked": s.blocked,
        "bytes_delivered": s.bytes_delivered,
    }


def resume_start(latest_utc: datetime | None) -> datetime:
    """Continue simulated time after the last stored telemetry so history stays monotonic."""
    now = datetime.now(UTC)
    if latest_utc is None:
        return now
    if latest_utc.tzinfo is None:
        latest_utc = latest_utc.replace(tzinfo=UTC)
    return max(now, latest_utc + timedelta(seconds=1))
