"""KHMER-SAT 1 ground-station API (FastAPI).

Run locally:  uv run uvicorn app.main:app --app-dir ground-station/backend --reload
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from onboard.logging_setup import configure as configure_logging
from shared.protocol import parse_key
from shared.schemas import CRITICAL_COMMANDS, CommandType
from simulator.communications.channel import Impairments
from simulator.orbit.propagator import Propagator
from simulator.orbit.visibility import predict_passes

from .config import GroundMode, LinkMode, Settings, get_settings
from .db import CommandRow, EventRow, ImageRow, TelemetryRow, init_db, make_engine
from .engine import SimulationEngine, resume_start
from .ground import command_to_dict, event_to_dict, image_to_dict
from .mqtt import MqttBridge
from .objectstore import LocalObjectStore, ObjectStore, S3ObjectStore
from .persistence import Persistence
from .security import ArmStore, Principal, require_admin, require_operator

log = logging.getLogger("ground.api")

# Commands an operator may send directly. IMAGE_ACK is ground-automatic only;
# critical commands must go through /api/commands/arm + /execute.
COMMAND_CATALOG: list[dict[str, Any]] = [
    {"type": "PING", "args": {}, "description": "Link/command path check"},
    {"type": "SET_MODE", "args": {"mode": ["NOMINAL", "IMAGING", "DOWNLINK", "SAFE"]}, "description": "Request an operating mode (interlocked)"},
    {"type": "CAPTURE_IMAGE", "args": {"width": "int?", "height": "int?", "jpeg_quality": "int?"}, "description": "Capture one image now"},
    {"type": "SCHEDULE_CAPTURE", "args": {"at_utc": "ISO-8601 UTC", "width": "int?", "height": "int?"}, "description": "Time-tagged capture"},
    {"type": "SET_CAMERA_CONFIG", "args": {"width": "int", "height": "int", "jpeg_quality": "int"}, "description": "Default resolution/quality"},
    {"type": "START_DOWNLINK", "args": {}, "description": "Enter DOWNLINK and transfer queued images"},
    {"type": "SET_TELEMETRY_RATE", "args": {"period_s": "0.5..60"}, "description": "Housekeeping period"},
    {"type": "CLEAR_FAULT", "args": {}, "description": "Clear latched faults; FAULT -> SAFE", "critical": True},
    {"type": "REBOOT", "args": {}, "description": "Reset the onboard computer", "critical": True},
    {"type": "DELETE_ALL_IMAGES", "args": {}, "description": "Erase onboard image storage", "critical": True},
]


class CommandRequest(BaseModel):
    type: CommandType
    args: dict[str, Any] = Field(default_factory=dict)


class ExecuteRequest(BaseModel):
    arm_id: str = Field(min_length=8, max_length=64)


class SimControl(BaseModel):
    time_scale: float | None = Field(default=None, ge=0.1, le=200)
    paused: bool | None = None
    link_mode: LinkMode | None = None


class FaultRequest(BaseModel):
    camera_failure: bool | None = None
    battery_drain_w: float | None = Field(default=None, ge=0, le=30)
    payload_heater_w: float | None = Field(default=None, ge=0, le=10)
    gnss_outage: bool | None = None
    fsw_hang: bool | None = None
    link_down: bool | None = None
    storage_fill: bool | None = None
    db_outage: bool | None = None
    packet_loss: float | None = Field(default=None, ge=0, le=1)
    packet_duplicate: float | None = Field(default=None, ge=0, le=1)
    packet_corrupt: float | None = Field(default=None, ge=0, le=1)
    packet_delay_s: float | None = Field(default=None, ge=0, le=30)


class Broadcaster:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def send_all(self, msg: dict) -> None:
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception:  # noqa: BLE001 - client went away
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


def _make_object_store(s: Settings) -> ObjectStore:
    if s.object_store == "s3":
        return S3ObjectStore(s.s3_endpoint, s.s3_access_key, s.s3_secret_key, s.s3_bucket)
    return LocalObjectStore(s.local_object_dir)


def _load_key(s: Settings) -> bytes:
    if s.command_hmac_key:
        return parse_key(s.command_hmac_key)
    if s.gs_mode is GroundMode.HARDWARE:
        raise RuntimeError("COMMAND_HMAC_KEY is required in HARDWARE mode")
    log.warning("COMMAND_HMAC_KEY not set - using an ephemeral random key (SIMULATION only)")
    return secrets.token_bytes(32)


async def _engine_loop(app: FastAPI) -> None:
    engine: SimulationEngine = app.state.engine
    period = 1.0 / app.state.settings.tick_hz
    last = time.monotonic()
    while True:
        t0 = time.monotonic()
        dt, last = t0 - last, t0
        try:
            outbox = await asyncio.to_thread(_step_and_drain, engine, dt)
            await app.state.broadcaster.send_all({"type": "tick", "status": engine.snapshot, **outbox})
        except Exception:  # noqa: BLE001 - keep the ground segment alive
            log.exception("engine step failed")
        await asyncio.sleep(max(0.0, period - (time.monotonic() - t0)))


def _step_and_drain(engine: SimulationEngine, dt: float) -> dict:
    engine.step(dt)
    return engine.ground.drain_outbox()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(settings.log_level, settings.log_json)
        app.state.settings = settings
        app.state.broadcaster = Broadcaster()
        app.state.arms = ArmStore(settings.interlock_arm_timeout_s)
        db_engine = make_engine(settings.database_url)
        sf = None
        for attempt in range(30):
            try:
                sf = init_db(db_engine)
                break
            except Exception as exc:  # noqa: BLE001 - DB may still be starting
                log.warning("database not ready (attempt %d): %s", attempt + 1, exc)
                await asyncio.sleep(2)
        if sf is None:
            raise RuntimeError("database unavailable at startup")
        app.state.persistence = Persistence(sf)
        app.state.objects = _make_object_store(settings)
        mqtt = None
        if settings.mqtt_enabled:
            mqtt = MqttBridge(settings.mqtt_host, settings.mqtt_port, settings.mqtt_username, settings.mqtt_password, settings.mqtt_topic_prefix)
        app.state.engine = None
        task = None
        if settings.gs_mode is GroundMode.SIMULATION:
            latest = app.state.persistence.query(lambda s: s.scalar(select(func.max(TelemetryRow.utc))))
            app.state.engine = SimulationEngine(
                settings,
                _load_key(settings),
                app.state.persistence,
                app.state.objects,
                start=resume_start(latest),
                publish=mqtt.publish if mqtt else None,
            )
            app.state.query_propagator = Propagator(app.state.engine.world.elements)
            task = asyncio.create_task(_engine_loop(app))
        else:
            _load_key(settings)
        log.info("ground station started", extra={"fields": {"mode": settings.gs_mode.value}})
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if app.state.engine:
            app.state.persistence.flush()
        if mqtt:
            mqtt.close()
        db_engine.dispose()

    app = FastAPI(title="KHMER-SAT 1 Ground Station", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    def engine_of(request: Request) -> SimulationEngine:
        eng = request.app.state.engine
        if eng is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "HARDWARE mode: no onboard link configured yet (milestone M3)")
        return eng

    async def on_engine(eng: SimulationEngine, fn) -> Any:
        return await asyncio.wait_for(asyncio.wrap_future(eng.submit(fn)), timeout=15)

    # ------------------------------------------------------------- status
    @app.get("/api/health")
    def health(request: Request) -> dict:
        p: Persistence = request.app.state.persistence
        return {"status": "ok", "gs_mode": settings.gs_mode.value, "database_ok": p.db_ok}

    @app.get("/api/status")
    def get_status(request: Request) -> dict:
        eng = request.app.state.engine
        if eng is None:
            return {"gs_mode": "HARDWARE", "link": {"up": False}, "telemetry": None, "database": {"ok": request.app.state.persistence.db_ok}}
        return eng.snapshot

    @app.get("/api/auth/whoami")
    def whoami(p: Principal = Depends(require_operator)) -> dict:
        return {"name": p.name, "role": p.role.value}

    # ---------------------------------------------------------- telemetry
    @app.get("/api/telemetry/latest")
    def telemetry_latest(eng: SimulationEngine = Depends(engine_of)) -> dict:
        if eng.ground.latest_hk is None:
            raise HTTPException(404, "no telemetry received yet")
        return eng.ground.latest_hk

    @app.get("/api/telemetry/history")
    def telemetry_history(
        request: Request,
        minutes: float = Query(60, gt=0, le=7 * 24 * 60),
        max_points: int = Query(600, ge=10, le=5000),
        eng: SimulationEngine = Depends(engine_of),
    ) -> dict:
        end = eng.world.now
        start = end - timedelta(minutes=minutes)
        degraded = False
        try:
            rows = request.app.state.persistence.query(
                lambda s: s.execute(
                    select(TelemetryRow.data).where(TelemetryRow.utc >= start, TelemetryRow.utc <= end).order_by(TelemetryRow.utc)
                ).scalars().all()
            )
        except Exception:  # noqa: BLE001 - fall back to in-memory buffer
            degraded = True
            rows = [d for d in list(eng.ground.telemetry) if start.isoformat() <= d["utc"] <= end.isoformat()]
        stride = max(1, len(rows) // max_points)
        return {"degraded": degraded, "count": len(rows), "points": rows[::stride]}

    # -------------------------------------------------------------- orbit
    @app.get("/api/orbit/elements")
    def orbit_elements(eng: SimulationEngine = Depends(engine_of)) -> dict:
        e = eng.world.elements
        return {
            "label": e.label,
            "synthetic": True,
            "epoch_utc": e.epoch.isoformat(),
            "altitude_km": e.altitude_km,
            "inclination_deg": e.inclination_deg,
            "raan_deg": round(e.raan_deg, 4),
            "eccentricity": e.eccentricity,
            "arg_perigee_deg": e.arg_perigee_deg,
            "mean_anomaly_deg": round(e.mean_anomaly_deg, 4),
            "period_min": round(e.period_min, 3),
            "propagator": "SGP4 (python-sgp4, WGS-72 constants)",
            "frames": "TEME -> PEF via GMST (IAU-82); polar motion and UT1-UTC neglected; WGS-84 geodetic",
        }

    @app.get("/api/orbit/track")
    def orbit_track(
        request: Request,
        back_min: float = Query(45, ge=0, le=300),
        ahead_min: float = Query(95, ge=0, le=600),
        step_s: float = Query(30, ge=5, le=300),
        eng: SimulationEngine = Depends(engine_of),
    ) -> dict:
        prop: Propagator = request.app.state.query_propagator
        start = eng.world.now - timedelta(minutes=back_min)
        pts = prop.ground_track(start, back_min + ahead_min, step_s)
        return {
            "now_utc": eng.world.now.isoformat(),
            "label": eng.world.elements.label,
            "points": [
                {"utc": p.utc.isoformat(), "lat": round(p.lat_deg, 3), "lon": round(p.lon_deg, 3), "alt_km": round(p.alt_km, 1), "sunlit": p.sunlit}
                for p in pts
            ],
        }

    @app.get("/api/orbit/passes")
    def orbit_passes(request: Request, hours: float = Query(24, gt=0, le=72), eng: SimulationEngine = Depends(engine_of)) -> dict:
        passes = predict_passes(request.app.state.query_propagator, eng.station, eng.world.now, hours)
        return {
            "station": eng.station.name,
            "min_elevation_deg": eng.station.min_elevation_deg,
            "label": eng.world.elements.label,
            "passes": [
                {"aos": p.aos.isoformat(), "los": p.los.isoformat(), "tca": p.tca.isoformat(), "max_elevation_deg": p.max_elevation_deg, "duration_s": round(p.duration_s)}
                for p in passes
            ],
        }

    # -------------------------------------------------------------- events
    @app.get("/api/events")
    def list_events(
        request: Request,
        limit: int = Query(200, ge=1, le=2000),
        severity: str | None = Query(None, pattern="^(INFO|WARNING|CRITICAL)$"),
    ) -> dict:
        eng = request.app.state.engine
        try:
            def q(s):
                stmt = select(EventRow).order_by(EventRow.utc.desc()).limit(limit)
                if severity:
                    stmt = stmt.where(EventRow.severity == severity)
                return [event_to_dict(r) for r in s.execute(stmt).scalars()]

            return {"degraded": False, "events": request.app.state.persistence.query(q)}
        except Exception:  # noqa: BLE001
            evs = list(eng.ground.events)[::-1] if eng else []
            return {"degraded": True, "events": [e for e in evs if not severity or e["severity"] == severity][:limit]}

    @app.post("/api/events/{event_id}/ack")
    async def ack_event(event_id: str, p: Principal = Depends(require_operator), eng: SimulationEngine = Depends(engine_of)) -> dict:
        d = await on_engine(eng, lambda: eng.ground.acknowledge_event(event_id, p.name))
        if d is None:
            raise HTTPException(404, "event not found in recent buffer")
        return d

    # ------------------------------------------------------------ commands
    @app.get("/api/commands/catalog")
    def command_catalog() -> list[dict]:
        return COMMAND_CATALOG

    @app.get("/api/commands")
    def list_commands(request: Request, limit: int = Query(100, ge=1, le=1000), include_automatic: bool = False) -> dict:
        eng = request.app.state.engine
        try:
            def q(s):
                stmt = select(CommandRow).order_by(CommandRow.created_utc.desc()).limit(limit)
                if not include_automatic:
                    stmt = stmt.where(CommandRow.automatic.is_(False))
                return [command_to_dict(r) for r in s.execute(stmt).scalars()]

            return {"degraded": False, "commands": request.app.state.persistence.query(q)}
        except Exception:  # noqa: BLE001
            cmds = list(eng.ground.commands.values())[::-1] if eng else []
            return {"degraded": True, "commands": [c for c in cmds if include_automatic or not c["automatic"]][:limit]}

    @app.post("/api/commands", status_code=202)
    async def send_command(req: CommandRequest, p: Principal = Depends(require_operator), eng: SimulationEngine = Depends(engine_of)) -> dict:
        if req.type is CommandType.IMAGE_ACK:
            raise HTTPException(400, "IMAGE_ACK is generated automatically by the ground segment")
        if req.type in CRITICAL_COMMANDS:
            raise HTTPException(409, "safety-critical command: use /api/commands/arm then /api/commands/execute")
        if "confirm" in req.args:
            raise HTTPException(400, "'confirm' is reserved for the interlock")
        return await on_engine(eng, lambda: eng.ground.send_command(req.type, req.args, p.name))

    @app.post("/api/commands/arm")
    def arm_command(req: CommandRequest, request: Request, p: Principal = Depends(require_admin), eng: SimulationEngine = Depends(engine_of)) -> dict:
        if req.type not in CRITICAL_COMMANDS:
            raise HTTPException(400, "only safety-critical commands are armed")
        a = request.app.state.arms.arm(req.type, req.args, p)
        return {"arm_id": a.arm_id, "type": a.type.value, "expires_in_s": settings.interlock_arm_timeout_s}

    @app.post("/api/commands/execute", status_code=202)
    async def execute_command(req: ExecuteRequest, request: Request, p: Principal = Depends(require_admin), eng: SimulationEngine = Depends(engine_of)) -> dict:
        a = request.app.state.arms.consume(req.arm_id, p)
        args = {**a.args, "confirm": a.type.value}
        return await on_engine(eng, lambda: eng.ground.send_command(a.type, args, p.name))

    # -------------------------------------------------------------- images
    @app.get("/api/images")
    def list_images(request: Request, limit: int = Query(100, ge=1, le=1000)) -> dict:
        eng = request.app.state.engine
        try:
            imgs = request.app.state.persistence.query(
                lambda s: [image_to_dict(r) for r in s.execute(select(ImageRow).order_by(ImageRow.captured_utc.desc()).limit(limit)).scalars()]
            )
            return {"degraded": False, "images": imgs}
        except Exception:  # noqa: BLE001
            imgs = list(eng.ground.images.values())[::-1] if eng else []
            return {"degraded": True, "images": imgs[:limit]}

    def _image_bytes(request: Request, image_id: str, thumb: bool) -> Response:
        try:
            uuid.UUID(image_id)
        except ValueError as exc:
            raise HTTPException(400, "invalid image id") from exc
        eng = request.app.state.engine
        cached = eng.ground.images.get(image_id) if eng else None
        if cached:
            captured = cached["captured_utc"]
        else:
            try:
                row = request.app.state.persistence.query(lambda s: s.get(ImageRow, image_id))
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(503, "database unavailable") from exc
            if row is None:
                raise HTTPException(404, "image not found")
            captured = row.captured_utc.isoformat()
        day = datetime.fromisoformat(captured).strftime("%Y/%m/%d")
        key = f"{'thumbs' if thumb else 'images'}/{day}/{image_id}.jpg"
        try:
            data = request.app.state.objects.get(key)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(404, "image object not found") from exc
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400, immutable"})

    @app.get("/api/images/{image_id}/file")
    def image_file(image_id: str, request: Request) -> Response:
        return _image_bytes(request, image_id, thumb=False)

    @app.get("/api/images/{image_id}/thumbnail")
    def image_thumb(image_id: str, request: Request) -> Response:
        return _image_bytes(request, image_id, thumb=True)

    # ------------------------------------------------- simulation controls
    @app.get("/api/sim/control")
    def sim_control_get(eng: SimulationEngine = Depends(engine_of)) -> dict:
        return {"time_scale": eng.time_scale, "paused": eng.paused, "link_mode": eng.link_mode.value}

    @app.post("/api/sim/control")
    async def sim_control(req: SimControl, p: Principal = Depends(require_operator), eng: SimulationEngine = Depends(engine_of)) -> dict:
        def apply():
            if req.time_scale is not None:
                eng.time_scale = req.time_scale
            if req.paused is not None:
                eng.paused = req.paused
            if req.link_mode is not None:
                eng.link_mode = req.link_mode
            eng.ground.ground_event("INFO", "sim", "SIM_CONTROL", f"{p.name}: {req.model_dump(exclude_none=True)}")
            return {"time_scale": eng.time_scale, "paused": eng.paused, "link_mode": eng.link_mode.value}

        return await on_engine(eng, apply)

    @app.get("/api/sim/faults")
    def sim_faults(eng: SimulationEngine = Depends(engine_of)) -> dict:
        return eng.faults_dict()

    @app.post("/api/sim/faults")
    async def sim_faults_set(req: FaultRequest, p: Principal = Depends(require_operator), eng: SimulationEngine = Depends(engine_of)) -> dict:
        changes = req.model_dump(exclude_none=True)

        def apply():
            f = eng.world.faults
            for k in ("camera_failure", "battery_drain_w", "payload_heater_w", "gnss_outage", "fsw_hang", "link_down"):
                if k in changes:
                    setattr(f, k, changes[k])
            if "storage_fill" in changes:
                eng.set_storage_fill(changes["storage_fill"])
            if "db_outage" in changes:
                eng.persistence.simulate_outage = changes["db_outage"]
            cur = eng.downlink.impairments
            imp = Impairments(
                changes.get("packet_loss", cur.loss),
                changes.get("packet_duplicate", cur.duplicate),
                changes.get("packet_corrupt", cur.corrupt),
                changes.get("packet_delay_s", cur.delay_s),
            )
            eng.set_impairments(imp)
            if changes:
                eng.ground.ground_event("WARNING", "sim", "FAULT_INJECTION", f"{p.name}: {changes}")
            return eng.faults_dict()

        return await on_engine(eng, apply)

    # ----------------------------------------------------------- websocket
    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        b: Broadcaster = websocket.app.state.broadcaster
        b.clients.add(websocket)
        eng = websocket.app.state.engine
        try:
            await websocket.send_json({"type": "hello", "status": eng.snapshot if eng else {"gs_mode": "HARDWARE"}})
            while True:
                await websocket.receive_text()  # keep-alive; client messages are ignored
        except WebSocketDisconnect:
            pass
        finally:
            b.clients.discard(websocket)

    return app


app = create_app()
