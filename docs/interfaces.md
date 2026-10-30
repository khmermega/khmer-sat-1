# KHMER-SAT 1 — Interface Control Document (ICD)

| | |
|---|---|
| Document | KS1-ICD-001 |
| Protocol version | 1 |
| Schema version | 1.0.0 |

## 1. Interface list

| ID | From → To | Medium | Status |
|---|---|---|---|
| IF-01 | Ground ↔ OBC (telemetry / telecommand) | Simulated channel; wired TCP (bench) | Sim ✅, TCP transport ✅ (unit tested), ground TCP client ⏳ |
| IF-02 | OBC ↔ watchdog MCU | UART 115200 8N1, line protocol | Sim ✅, firmware core ✅, hardware ⏳ |
| IF-03 | OBC ↔ camera | USB UVC (V4L2) / CSI (libcamera) | Adapters written, HIL ⏳ |
| IF-04 | OBC ↔ GNSS | UART NMEA-0183 | GGA parser ✅, serial driver ⏳ |
| IF-05 | OBC ↔ IMU / magnetometer | I²C (part TBD) | Interfaces ✅, drivers ⏳ |
| IF-06 | OBC ↔ EPS | TBD (I²C/SMBus typical) | Interface ✅, driver ⏳ |
| IF-07 | Backend ↔ dashboard | HTTPS REST + WebSocket | ✅ |
| IF-08 | Backend → MQTT broker | MQTT 3.1.1/5, username/password | Implemented, live test ⏳ |

## 2. Space/ground frame format (IF-01)

### 2.1 Frame layout (big-endian)

| Offset | Size | Field | Notes |
|---|---|---|---|
| 0 | 2 | Sync word | `0x4B53` ("KS") |
| 2 | 1 | Protocol version | `1` |
| 3 | 2 | Satellite ID | `0x4B31` — project-internal, **not** a NORAD/ITU id |
| 5 | 1 | Message type | §2.2 |
| 6 | 4 | Sequence number | per sender, wraps at 2³² |
| 10 | 8 | Timestamp | UTC, ms since 1970-01-01 |
| 18 | 1 | Flags | bit0 = AUTHENTICATED |
| 19 | 2 | Payload length N | ≤ 8192 |
| 21 | N | Payload | §2.3 |
| 21+N | 16 | Auth tag | only if AUTHENTICATED: HMAC-SHA256(key, header‖payload)[0:16] |
| end−2 | 2 | CRC | CRC-16/CCITT-FALSE over all preceding bytes (check value 0x29B1) |

Wired transport (TCP) prefixes each frame with a 4-byte big-endian length.

### 2.2 Message types

| Code | Name | Direction | Payload | Authenticated |
|---|---|---|---|---|
| 0x01 | HOUSEKEEPING | ↓ | JSON `Housekeeping` | no |
| 0x02 | EVENT | ↓ | JSON `EventMessage` | no |
| 0x03 | COMMAND_ACK | ↓ | JSON `CommandAck` | no |
| 0x10 | IMAGE_META | ↓ | JSON `ImageMeta` | no |
| 0x11 | IMAGE_CHUNK | ↓ | binary: uuid(16) ‖ index u16 ‖ total u16 ‖ data | no |
| 0x80 | COMMAND | ↑ | JSON `CommandBody` | **required** |

Downlink authentication is TBD (R-11).

### 2.3 Payload schemas

JSON Schemas: `shared/schemas/json/*.schema.json` (generated from
`shared/schemas/models.py` by `scripts/export_schemas.py`). Unknown fields are
rejected (`extra="forbid"`).

### 2.4 Commands

| Type | Args | Allowed modes | Interlocks | Critical |
|---|---|---|---|---|
| PING | — | all incl. BOOT | — | |
| SET_MODE | `mode` ∈ NOMINAL/IMAGING/DOWNLINK/SAFE | per transition table | SAFE→NOMINAL: SoC ≥ 45 %, no SAFE-class fault; IMAGING: imaging interlocks; DOWNLINK: SoC ≥ 40 % | |
| CAPTURE_IMAGE | `width?`, `height?`, `jpeg_quality?` | NOMINAL, IMAGING | SoC ≥ 50 %, no imaging-inhibit faults | |
| SCHEDULE_CAPTURE | `at_utc` (ISO-8601 with tz), size/quality | not BOOT | now ≤ at ≤ now+7 d | |
| SET_CAMERA_CONFIG | `width`, `height`, `jpeg_quality` | not BOOT | ranges | |
| START_DOWNLINK | — | NOMINAL | link up, SoC ≥ 40 % | |
| SET_TELEMETRY_RATE | `period_s` 0.5–60 | not BOOT | | |
| CLEAR_FAULT | `confirm="CLEAR_FAULT"` | not BOOT | admin + ARM/EXECUTE | ⚠ |
| REBOOT | `confirm="REBOOT"` | not BOOT | admin + ARM/EXECUTE | ⚠ |
| DELETE_ALL_IMAGES | `confirm="DELETE_ALL_IMAGES"` | NOMINAL, SAFE | admin + ARM/EXECUTE | ⚠ |
| IMAGE_ACK | `image_id`, `ok`, `missing?`, `need_meta?` | not BOOT | ground-automatic only | |

Rejection reasons are stable strings (e.g. `bad_signature`, `replay`,
`stale_timestamp`, `interlock_soc_below_recovery_threshold`,
`illegal_transition_IMAGING_to_DOWNLINK`, `booting`).

### 2.5 Timing

| Parameter | Value |
|---|---|
| Housekeeping period | 2 s default (0.5–60 s) |
| Replay window | ±30 s |
| Ground command ACK timeout | 60 s |
| Ground image NACK stall | 5 s |
| Onboard image ACK timeout / retries | 60 s / 3 |
| Image chunk size | 3072 B data (3115 B frame) |

## 3. Watchdog UART (IF-02)

115200 8N1, `\n`-terminated ASCII lines.

| OBC → MCU | MCU → OBC |
|---|---|
| `HB` | `OK <reset_count>` |
| `STATUS` | `STATE <ARMED\|GRACE\|RESETTING\|POWER_CYCLE\|UNDERVOLTAGE> RESETS <n> CYCLES <n>` |
| other | `ERR` |

Electrical: 3.3 V logic. Reset output drives the OBC reset/RUN line through an
open-drain stage. Pin map: `firmware/watchdog-mcu/README.md`.

## 4. Ground API (IF-07)

OpenAPI is served by the backend at `/docs`. Summary:

| Method | Path | Auth |
|---|---|---|
| GET | `/api/health`, `/api/status` | — |
| GET | `/api/telemetry/latest`, `/api/telemetry/history?minutes&max_points` | — |
| GET | `/api/orbit/elements`, `/api/orbit/track`, `/api/orbit/passes` | — |
| GET | `/api/events`, `/api/commands`, `/api/commands/catalog`, `/api/images`, `/api/images/{id}/file`, `/api/images/{id}/thumbnail` | — |
| POST | `/api/commands` | operator |
| POST | `/api/commands/arm`, `/api/commands/execute` | admin |
| POST | `/api/events/{id}/ack` | operator |
| GET/POST | `/api/sim/control`, `/api/sim/faults` | POST: operator |
| WS | `/ws` | — (pushes `tick` messages: status + new events/commands/images) |

## 5. MQTT topics (IF-08)

`<MQTT_TOPIC_PREFIX>/telemetry` (decoded housekeeping JSON),
`<MQTT_TOPIC_PREFIX>/events`. QoS 0. Anonymous access disabled at the broker.
