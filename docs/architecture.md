# KHMER-SAT 1 — Architecture

## 1. Context

```
                    ┌────────────────────── SIMULATION MODE (this milestone) ─────────────────────┐
                    │                                                                              │
 ┌──────────────┐   │  ┌─────────────────────┐   uplink channel    ┌──────────────────────────────┐ │
 │  Operator    │   │  │  Ground segment     │ ──(signed COMMAND)─▶ │ Flight software (onboard/)   │ │
 │  browser     │◀──┼──│  ground-station/    │                      │  modes · FDIR · scheduler    │ │
 │  (React)     │ WS│  │  backend/app        │ ◀─(HK, EVENT, ACK,── │  camera · storage · downlink │ │
 └──────────────┘   │  │  FastAPI + engine   │   IMAGE_META/CHUNK)  │  watchdog heartbeat          │ │
        ▲ REST      │  └─────────┬───────────┘  downlink channel    └──────────────┬───────────────┘ │
        │           │            │  (loss/delay/dup/corrupt, AOS/LOS)              │ HAL adapters    │
        │           │  ┌─────────▼──────────┐                         ┌────────────▼───────────────┐ │
        │           │  │ PostgreSQL · MinIO │                         │ Simulator (simulator/)     │ │
        │           │  │ MQTT (Mosquitto)   │                         │ SGP4 orbit · sun/eclipse   │ │
        │           │  └────────────────────┘                         │ attitude · EPS · thermal   │ │
        │           │                                                 │ magnetic field · imagery   │ │
        │           └─────────────────────────────────────────────────┴────────────────────────────┘ │
```

In HARDWARE mode the simulator and in-process channels are replaced by the
Raspberry Pi running `onboard/` with hardware adapters, connected to the ground
station over a **wired** TCP link (`onboard/communications/tcp.py`), plus the
watchdog MCU (`firmware/watchdog-mcu`). That wiring is milestone M3.

## 2. Components

| Component | Path | Responsibility |
|---|---|---|
| Protocol | `shared/protocol` | Frame encode/decode, CRC-16, HMAC auth, replay guard, payload codecs |
| Schemas | `shared/schemas` | Versioned Pydantic payload models; JSON Schema export |
| Simulator | `simulator/` | Physical "truth": SGP4 orbit, frames, sun/eclipse, kinematic attitude, EPS energy balance, lumped thermal, dipole field, link channels, synthetic imagery |
| Flight software | `onboard/` | Mode manager, FDIR, task scheduler, command processor, camera pipeline, storage manager, downlink queue, watchdog client, structured logging |
| Ground backend | `ground-station/backend/app` | Simulation engine, ground segment (decode, reassembly, signing, audit), persistence with outage buffering, object store, MQTT bridge, REST + WebSocket API, auth + interlocks |
| Mission control | `ground-station/frontend` | React/TypeScript/Vite/Tailwind dashboard, Three.js attitude, Recharts trends, SVG ground track |
| Watchdog MCU | `firmware/watchdog-mcu` | Portable C watchdog/health state machine + RP2040 port |

## 3. Architecture decision records

### ADR-001 — Python for the prototype flight software
**Context:** Software-first prototype on a Raspberry Pi-class computer; small team; fast iteration.
**Decision:** Python 3.12, single-threaded tick loop, HAL-based adapters.
**Consequences:** Rapid development and shared code with the ground; not suitable for a flight OBC as-is (GC pauses, interpreter footprint, no MISRA). Safety-critical supervision is delegated to an independent C MCU (ADR-006). Re-implementation for a flight computer is a future decision (R-02).

### ADR-002 — One flight codebase for simulation and hardware
**Decision:** Flight code depends only on Protocols in `onboard/*/interfaces.py`; simulator adapters live in separate modules.
**Consequences:** Every integration test exercises the real flight logic. Hardware adapters must match the same interfaces.

### ADR-003 — Custom binary frame with JSON payloads (v1)
**Context:** Need inspectable messages now; bandwidth matters later.
**Decision:** Fixed 21-byte binary header + CRC; JSON payloads (binary for image chunks).
**Consequences:** ~817 B housekeeping frames (measured). A packed binary HK format (and CCSDS Space Packet compatibility) is planned once the radio and data rate are known (R-04). Version byte allows migration.

### ADR-004 — HMAC-SHA256 authentication, no encryption
**Decision:** Truncated (128-bit) HMAC-SHA256 tag over header+payload; replay guard on (timestamp, seq) within ±30 s.
**Consequences:** Integrity and authenticity without obscuring content (amateur-service rules commonly prohibit encryption — the applicable licence regime is TBD). Requires time sync (GNSS or ground time upload) — R-10.

### ADR-005 — In-process simulation engine inside the ground backend
**Decision:** The backend runs world + flight software + channels in a worker thread at 1 Hz × time-scale, sub-stepping at ≤1 s.
**Consequences:** One process to run for demos; deterministic tests drive `engine.step()` directly. In HARDWARE mode the engine is disabled.

### ADR-006 — Independent watchdog MCU
**Decision:** Separate microcontroller resets / power-cycles the OBC on missing heartbeats, holds it in reset on undervoltage.
**Consequences:** Recovery from software hangs does not depend on the OBC. Core logic is portable C with host unit tests.

### ADR-007 — PostgreSQL + MinIO + MQTT, SQLite fallback
**Decision:** Postgres (optionally TimescaleDB) for relational/time-series data, MinIO for images, Mosquitto for telemetry fan-out. Local development uses SQLite + filesystem with the same code paths.
**Consequences:** Zero-setup local runs; production-like stack in Docker. The Postgres/MinIO path must be exercised in CI (compose job builds images; full stack test is pending).

### ADR-008 — Buffered persistence
**Decision:** All DB writes queue in memory and flush once per tick; on failure they are retained (bounded, telemetry shed first) and reads fall back to in-memory caches flagged `degraded`.
**Consequences:** Ground keeps running through DB outages without telemetry loss (NFR-REL-001/002).

### ADR-009 — Selective-repeat image downlink
**Decision:** IMAGE_META + N×IMAGE_CHUNK; ground NACKs the missing chunk list after a 5 s stall; onboard also retries whole images after 60 s ACK timeout (max 3).
**Consequences:** Delivery under realistic loss; ACK/NACK travel as authenticated commands.

## 4. Operating modes

See `docs/safety.md §1` for the transition table and interlocks.

## 5. Time and reference frames

| Quantity | Convention |
|---|---|
| Time scale | UTC everywhere; naive datetimes rejected; UT1−UTC neglected |
| Protocol timestamp | uint64 ms since Unix epoch (UTC) |
| Orbit output frame | TEME (SGP4 native) |
| Earth-fixed | PEF via GMST IAU-82 rotation; polar motion neglected |
| Geodetic | WGS-84 |
| Attitude | quaternion [w,x,y,z], Hamilton, body → TEME (treated as ECI) |
| Body frame | +Z long axis / camera boresight; +X along-track in ideal nadir pointing |
| Sun | Astronomical Almanac low-precision formula; cylindrical shadow |

## 6. Budgets

Power, mass, storage and data-rate budgets: [`budgets.md`](budgets.md).

## 7. Deployment

`docker-compose.yml` — postgres, minio, mosquitto, backend, frontend (nginx).
All published ports bind to `127.0.0.1`. Local development runs backend +
Vite dev server directly (see README).
