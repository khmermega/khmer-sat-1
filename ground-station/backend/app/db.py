"""Relational storage (PostgreSQL in Docker; SQLite for zero-setup local dev).

TimescaleDB: the `telemetry` table is a natural hypertable on `utc`. When the
timescaledb extension is present, scripts/timescale.sql converts it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import JSON, BigInteger, Boolean, Float, Integer, String, Text, TypeDecorator, create_engine
from sqlalchemy import DateTime as _DateTime
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class DateTime(TypeDecorator):
    """Timezone-aware UTC timestamps on every backend.

    SQLite drops tzinfo on storage; without this, values read back are naive and
    clients would misinterpret them as local time. Naive values are rejected on write.
    """

    impl = _DateTime(timezone=True)
    cache_ok = True

    def __init__(self, timezone: bool = True) -> None:  # signature-compatible with sqlalchemy.DateTime
        super().__init__()

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime: timestamps must be explicit UTC")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


class TelemetryRow(Base):
    __tablename__ = "telemetry"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    seq: Mapped[int] = mapped_column(BigInteger)
    mode: Mapped[str] = mapped_column(String(16))
    soc_pct: Mapped[float] = mapped_column(Float)
    battery_v: Mapped[float] = mapped_column(Float)
    battery_a: Mapped[float] = mapped_column(Float)
    solar_w: Mapped[float] = mapped_column(Float)
    load_w: Mapped[float] = mapped_column(Float)
    cpu_c: Mapped[float] = mapped_column(Float)
    payload_c: Mapped[float] = mapped_column(Float)
    battery_c: Mapped[float] = mapped_column(Float)
    lat_deg: Mapped[float] = mapped_column(Float)
    lon_deg: Mapped[float] = mapped_column(Float)
    alt_km: Mapped[float] = mapped_column(Float)
    sunlit: Mapped[bool] = mapped_column(Boolean)
    gs_elevation_deg: Mapped[float] = mapped_column(Float)
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    data: Mapped[dict] = mapped_column(JSON)


class EventRow(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid, assigned on ground receipt
    utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    origin: Mapped[str] = mapped_column(String(16))  # "space" or "ground"
    source: Mapped[str] = mapped_column(String(32))
    code: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CommandRow(Base):
    __tablename__ = "commands"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    type: Mapped[str] = mapped_column(String(32))
    args: Mapped[dict] = mapped_column(JSON)
    operator: Mapped[str] = mapped_column(String(64))
    automatic: Mapped[bool] = mapped_column(Boolean, default=False)
    critical: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16))
    seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    ack_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class ImageRow(Base):
    __tablename__ = "images"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    captured_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(32))
    camera: Mapped[str] = mapped_column(String(32))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    verified: Mapped[bool] = mapped_column(Boolean)
    object_key: Mapped[str] = mapped_column(String(128))
    thumb_key: Mapped[str] = mapped_column(String(128))
    meta: Mapped[dict] = mapped_column(JSON)


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite:///"):
        path = url.removeprefix("sqlite:///")
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


def init_db(engine: Engine) -> sessionmaker:
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
