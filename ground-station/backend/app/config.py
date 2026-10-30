"""Ground-station settings, loaded from environment variables / .env.

Secrets (tokens, keys, passwords) are NEVER defaulted to real values here.
Run `python scripts/init_env.py` to generate a local .env with random secrets.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GroundMode(StrEnum):
    SIMULATION = "SIMULATION"
    HARDWARE = "HARDWARE"


class LinkMode(StrEnum):
    BENCH = "bench"  # always-connected wired/simulated bench link
    ORBITAL = "orbital"  # link only up while the ground station sees the satellite


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gs_mode: GroundMode = GroundMode.SIMULATION
    database_url: str = "sqlite:///./data/ground.db"
    object_store: str = Field(default="local", pattern="^(local|s3)$")
    local_object_dir: str = "./data/objects"
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "khmersat-images"

    mqtt_enabled: bool = False
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_topic_prefix: str = "khmersat1"

    command_hmac_key: str = ""
    operator_token: str = ""
    admin_token: str = ""
    interlock_arm_timeout_s: float = 30.0
    command_ack_timeout_s: float = 60.0

    sim_time_scale: float = Field(default=1.0, ge=0.1, le=200)
    sim_pass_offset_min: float = 10.0
    sim_link_mode: LinkMode = LinkMode.BENCH
    sim_seed: int = 7
    onboard_data_dir: str = "./data/onboard-sim"
    onboard_storage_mb: int = Field(default=64, ge=1, le=4096)

    gs_name: str = "Phnom Penh (simulated)"
    gs_lat: float = Field(default=11.5564, ge=-90, le=90)
    gs_lon: float = Field(default=104.9282, ge=-180, le=180)
    gs_alt_m: float = 12.0
    gs_min_el: float = Field(default=10.0, ge=0, le=60)

    tick_hz: float = Field(default=1.0, gt=0, le=10)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    log_level: str = "INFO"
    log_json: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
