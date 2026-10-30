"""Versioned message schemas (Pydantic v2).

These models define the JSON payload bodies carried inside protocol frames
(shared/protocol/packet.py). JSON Schema exports live in shared/schemas/json/
and are regenerated with `python scripts/export_schemas.py`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0.0"


class Mode(StrEnum):
    BOOT = "BOOT"
    NOMINAL = "NOMINAL"
    IMAGING = "IMAGING"
    DOWNLINK = "DOWNLINK"
    SAFE = "SAFE"
    FAULT = "FAULT"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ImageSource(StrEnum):
    """Provenance of an image. Ground photography must NEVER be labelled orbital."""

    SIMULATED_ORBITAL = "SIMULATED_ORBITAL"  # procedurally generated, synthetic
    GROUND_TEST_HARDWARE = "GROUND_TEST_HARDWARE"  # real camera, captured on the ground
    MOCK_SAMPLE = "MOCK_SAMPLE"  # bundled/sample file replayed by the mock camera


class CommandType(StrEnum):
    PING = "PING"
    SET_MODE = "SET_MODE"
    CAPTURE_IMAGE = "CAPTURE_IMAGE"
    SCHEDULE_CAPTURE = "SCHEDULE_CAPTURE"
    SET_CAMERA_CONFIG = "SET_CAMERA_CONFIG"
    START_DOWNLINK = "START_DOWNLINK"
    SET_TELEMETRY_RATE = "SET_TELEMETRY_RATE"
    CLEAR_FAULT = "CLEAR_FAULT"  # safety-critical
    REBOOT = "REBOOT"  # safety-critical
    DELETE_ALL_IMAGES = "DELETE_ALL_IMAGES"  # safety-critical
    IMAGE_ACK = "IMAGE_ACK"  # automatic ground acknowledgement of a complete image


#: Commands that require the two-step ARM/EXECUTE interlock on the ground and
#: an elevated (admin) operator role. See docs/safety.md §3.
CRITICAL_COMMANDS: frozenset[CommandType] = frozenset(
    {CommandType.CLEAR_FAULT, CommandType.REBOOT, CommandType.DELETE_ALL_IMAGES}
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrbitState(_Strict):
    lat_deg: float
    lon_deg: float
    alt_km: float
    speed_km_s: float
    sunlit: bool
    gs_elevation_deg: float
    gs_visible: bool


class PowerState(_Strict):
    soc_pct: float = Field(ge=0, le=100)
    battery_v: float
    battery_a: float  # positive = charging
    solar_w: float
    load_w: float


class ThermalState(_Strict):
    cpu_c: float
    payload_c: float
    battery_c: float
    panel_c: float


class AttitudeState(_Strict):
    q: list[float] = Field(min_length=4, max_length=4)  # [w, x, y, z], body->ECI (simulated)
    rate_dps: list[float] = Field(min_length=3, max_length=3)
    mag_ut: list[float] = Field(min_length=3, max_length=3)


class GnssState(_Strict):
    fix: bool
    sats: int
    lat_deg: float | None = None
    lon_deg: float | None = None
    alt_km: float | None = None


class StorageState(_Strict):
    used_bytes: int
    capacity_bytes: int
    images_stored: int
    downlink_queue: int


class Housekeeping(_Strict):
    """Periodic HOUSEKEEPING payload."""

    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    utc: datetime
    mode: Mode
    uptime_s: float
    boot_count: int
    cpu_load_pct: float
    orbit: OrbitState
    power: PowerState
    thermal: ThermalState
    attitude: AttitudeState
    gnss: GnssState
    storage: StorageState
    faults: list[str] = Field(default_factory=list)
    last_cmd_seq: int | None = None
    simulated: bool = True


class EventMessage(_Strict):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    utc: datetime
    severity: Severity
    source: str
    code: str
    message: str


class CommandBody(_Strict):
    """Body of an uplinked COMMAND packet."""

    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    command_id: str
    type: CommandType
    args: dict[str, Any] = Field(default_factory=dict)


class AckStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CommandAck(_Strict):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    command_id: str
    status: AckStatus
    reason: str = ""
    utc: datetime
    detail: dict[str, Any] = Field(default_factory=dict)


class ImageMeta(_Strict):
    """IMAGE_META payload - metadata accompanying every image."""

    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    image_id: str
    captured_utc: datetime
    source: ImageSource
    camera: str
    width: int
    height: int
    jpeg_quality: int
    size_bytes: int
    sha256: str
    chunks: int
    lat_deg: float | None = None
    lon_deg: float | None = None
    alt_km: float | None = None
    mode: Mode | None = None
    note: str = ""
