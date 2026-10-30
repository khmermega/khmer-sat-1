"""Shared fixtures: a fully wired simulation engine on temporary storage."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.config import Settings
from app.db import init_db, make_engine
from app.engine import SimulationEngine
from app.objectstore import LocalObjectStore
from app.persistence import Persistence
from onboard.camera.base import CameraConfig
from shared.schemas import CommandType

KEY = bytes.fromhex("11" * 32)
T0 = datetime(2026, 10, 30, 2, 0, tzinfo=UTC)


def make_settings(tmp_path, **kw) -> Settings:
    base = dict(
        database_url=f"sqlite:///{tmp_path}/ground.db",
        onboard_data_dir=str(tmp_path / "onboard"),
        local_object_dir=str(tmp_path / "objects"),
        command_hmac_key=KEY.hex(),
        operator_token="op-token-for-tests",
        admin_token="admin-token-for-tests",
        log_json=False,
    )
    base.update(kw)
    return Settings(_env_file=None, **base)


class Harness:
    """Convenience wrapper for driving the engine deterministically."""

    def __init__(self, engine: SimulationEngine) -> None:
        self.e = engine

    def run(self, seconds: float, scale: float = 1.0) -> None:
        self.e.time_scale = scale
        for _ in range(int(seconds / scale)):
            self.e.step(1.0)

    def cmd(self, ctype: CommandType, **args) -> str:
        return self.e.ground.send_command(ctype, args, "test")["id"]

    def status(self, cmd_id: str) -> dict:
        return self.e.ground.commands[cmd_id]

    def run_until(self, pred, max_s: float = 300, scale: float = 1.0) -> bool:
        self.e.time_scale = scale
        for _ in range(int(max_s / scale)):
            if pred():
                return True
            self.e.step(1.0)
        return pred()

    def event_codes(self) -> list[str]:
        return [ev["code"] for ev in self.e.ground.events]

    @property
    def mode(self) -> str:
        return self.e.fsw.mode.value


@pytest.fixture
def harness(tmp_path) -> Harness:
    s = make_settings(tmp_path)
    p = Persistence(init_db(make_engine(s.database_url)))
    e = SimulationEngine(s, KEY, p, LocalObjectStore(s.local_object_dir), start=T0)
    e.fsw.camera_cfg = CameraConfig(320, 240, 80)  # small images keep tests fast
    h = Harness(e)
    h.run(7)  # boot sequence
    assert h.mode == "NOMINAL"
    return h
