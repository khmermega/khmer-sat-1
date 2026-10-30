# KHMER-SAT 1 — Mission Requirements

| | |
|---|---|
| Document | KS1-REQ-001 |
| Revision | 0.1 (engineering prototype baseline) |
| Status | Draft — software prototype; **not flight qualified** |

## 1. Mission statement

KHMER-SAT 1 is a Cambodian Earth-observation 3U CubeSat **engineering
prototype**. Phase 1 (this repository) builds a software-first prototype —
flight software, simulator, ground segment and mission control — that can later
be connected to real sensors, a camera, power hardware and an *authorized*
ground link.

Nothing in this repository is flight qualified. No launch, orbit, frequency
coordination or licence exists. All orbital data is synthetic.

## 2. Conventions

- **Shall** = mandatory. **Should** = goal.
- `TBD` = value not yet known; it must not be invented. `TBC` = provisional.
- Verification methods: **T** test, **A** analysis, **I** inspection, **D** demonstration.
- Status: ✅ verified by automated test in this repo · 🟡 partially implemented · ⏳ pending.

## 3. Functional requirements

### 3.1 Payload (camera) — FR-CAM

| ID | Requirement | Acceptance criteria | V | Status |
|---|---|---|---|---|
| FR-CAM-001 | The system shall provide a camera abstraction with mock, USB/V4L2 and Raspberry Pi camera implementations. | `Camera` ABC with `MockCamera`, `V4L2Camera`, `PiCamera`; mock covered by unit tests; hardware adapters by HIL tests. | T, I | 🟡 mock ✅, HW adapters written, HIL pending |
| FR-CAM-002 | Image resolution shall be configurable between 64×64 and 4096×4096 px. | Out-of-range config rejected (`ValueError`), in-range honoured in output dimensions. | T | ✅ |
| FR-CAM-003 | Images shall be JPEG-compressed with configurable quality 10–95. | Output begins with JPEG SOI marker; quality outside range rejected. | T | ✅ |
| FR-CAM-004 | Every image shall carry a SHA-256 checksum computed onboard and verified on ground. | Ground recomputes hash; mismatch triggers NACK + retransmission, never storage. | T | ✅ |
| FR-CAM-005 | Every image shall carry an explicit-UTC capture timestamp and metadata (id, source, camera, size, resolution, position if GNSS fix, mode). | `ImageMeta` schema validated; naive timestamps rejected. | T | ✅ |
| FR-CAM-006 | Image provenance shall be recorded and displayed. Simulated orbital imagery and ground-test hardware imagery shall never be confused. | `ImageSource` ∈ {SIMULATED_ORBITAL, GROUND_TEST_HARDWARE, MOCK_SAMPLE}; physical cameras hard-code GROUND_TEST_HARDWARE; synthetic images stamped "SIMULATED" in pixels. | T, I | ✅ |
| FR-CAM-007 | Captures shall be schedulable at an absolute UTC time up to 7 days ahead. | SCHEDULE_CAPTURE accepted → executed at time → COMPLETED ack; past/too-far times rejected. | T | ✅ |
| FR-CAM-008 | Thumbnails shall be generated onboard (≤256 px) and on ground (≤320 px). | Thumbnail dimensions asserted. | T | ✅ |
| FR-CAM-009 | Captured images shall be queued locally and transferred to ground storage with retry. | Image survives link outage and reboot; delivered after recovery. | T | ✅ |

### 3.2 Orbit simulation — FR-ORB

| ID | Requirement | Acceptance criteria | V | Status |
|---|---|---|---|---|
| FR-ORB-001 | Orbit propagation shall use SGP4. | `python-sgp4` (Vallado reference implementation); epoch round-trip verified. | T | ✅ |
| FR-ORB-002 | All time handling shall use explicit UTC; naive datetimes shall be rejected. | `ensure_utc` raises on naive input; DB layer refuses naive writes and returns tz-aware values. | T | ✅ |
| FR-ORB-003 | Frame conversions (TEME→ECEF→geodetic, topocentric look angles) shall be unit tested against reference values. | GMST vs Vallado Ex. 3-5 within 1e-4°; JD vs sgp4 `jday`; geodetic round trip < 1 mm. | T | ✅ |
| FR-ORB-004 | Synthetic demonstration elements shall be clearly labelled and never presented as real tracking data. | Label "SYNTHETIC DEMO ORBIT - NOT REAL TRACKING DATA" in API and every dashboard orbit view. | T, I | ✅ |
| FR-ORB-005 | The ground station location shall be configurable; Phnom Penh shall be the default simulated site. | `GS_LAT/GS_LON/GS_ALT_M/GS_MIN_EL` env vars. Real site: TBD. | I | ✅ |
| FR-ORB-006 | The system shall display latitude, longitude, altitude, velocity, ground track and predicted ground-station passes. | Dashboard map + link panel; `/api/orbit/track`, `/api/orbit/passes`. | D, T | ✅ |

### 3.3 Onboard software — FR-OBC

| ID | Requirement | Acceptance criteria | V | Status |
|---|---|---|---|---|
| FR-OBC-001 | The flight software shall implement modes BOOT, NOMINAL, IMAGING, DOWNLINK, SAFE, FAULT with an explicit transition table. | Illegal transitions raise `TransitionError`; table in `docs/safety.md §1`. | T | ✅ |
| FR-OBC-002 | Periodic work shall run in an isolating scheduler; a failing task shall not stop others. | Faulty task counted; others continue; ≥5 errors → FAULT. | T | ✅ |
| FR-OBC-003 | Housekeeping telemetry shall be produced at a commandable period (0.5–60 s, default 2 s). | No gaps under nominal conditions over 120 s. | T | ✅ |
| FR-OBC-004 | Persistent state (boot count, acknowledged images, watchdog history) shall survive resets; writes shall be atomic. | Temp files cleaned on start; state reloaded after reset. | T | ✅ |
| FR-OBC-005 | The OBC shall send heartbeats to an independent watchdog MCU. | Missing heartbeat > timeout → reset; see FR-SAF-004. | T | ✅ (sim + firmware host tests) |
| FR-OBC-006 | Logs shall be structured (JSON lines) with UTC timestamps. | `onboard/logging_setup.py`. | I | ✅ |
| FR-OBC-007 | Hardware access shall go through a HAL so identical flight code runs in simulation and on hardware. | `onboard.app.Hal`; sim adapters only in `onboard/*/sim.py` & `simhal.py`. | I | ✅ |

### 3.4 Telemetry & telecommand — FR-TTC

| ID | Requirement | Acceptance criteria | V | Status |
|---|---|---|---|---|
| FR-TTC-001 | Packets shall carry satellite id, protocol version, sequence number, UTC timestamp, message type, payload length, CRC and payload body. | Format in `docs/interfaces.md §2`; round-trip tests. | T | ✅ |
| FR-TTC-002 | Every frame shall be integrity-checked (CRC-16/CCITT-FALSE). | Every single-bit flip in a frame is detected. | T | ✅ |
| FR-TTC-003 | Commands shall be authenticated (HMAC-SHA256, ≥256-bit key from environment). | Forged/tampered commands rejected with `bad_signature`. | T | ✅ |
| FR-TTC-004 | Commands shall be protected against replay. | Exact replay → `replay`; ±30 s window → `stale_timestamp`. | T | ✅ |
| FR-TTC-005 | Every command shall be acknowledged (ACCEPTED / REJECTED / COMPLETED / FAILED) with a reason; unacknowledged commands time out on ground. | Ack in audit trail; TIMEOUT after 60 s. | T | ✅ |
| FR-TTC-006 | Schemas shall be versioned and exported as JSON Schema. | `schema_version` field; `shared/schemas/json/*.schema.json`. | I | ✅ |
| FR-TTC-007 | The link simulation shall support packet loss, delay, duplication and corruption. | Configurable per channel; image still delivered under 10 % loss / 5 % corruption / 10 % duplication. | T | ✅ |
| FR-TTC-008 | Image transfer shall use selective repeat of missing chunks plus a whole-image timeout retry. | Ground NACKs missing chunk list after 5 s stall. | T | ✅ |

### 3.5 Safety & FDIR — FR-SAF

| ID | Requirement | Acceptance criteria | V | Status |
|---|---|---|---|---|
| FR-SAF-001 | Low battery (SoC < 30 % TBC) shall cause an autonomous transition to SAFE. | VC-06. | T | ✅ |
| FR-SAF-002 | Thermal limit violations shall cause SAFE (battery, payload over-temp, CPU) or imaging inhibit (payload under-temp). | VC-07 + unit rules. | T | ✅ |
| FR-SAF-003 | Leaving SAFE shall be interlocked (SoC ≥ 45 % TBC, no active SAFE-class fault). | NOMINAL rejected while interlock open. | T | ✅ |
| FR-SAF-004 | A watchdog reset shall reboot into SAFE; ≥3 watchdog resets per hour shall reboot into FAULT. | VC-08, VC-09. | T | ✅ |
| FR-SAF-005 | Safety-critical commands (CLEAR_FAULT, REBOOT, DELETE_ALL_IMAGES) shall require admin role and a two-step ARM/EXECUTE on ground plus onboard confirmation token. | Direct send → 409; operator arm → 403; onboard rejects without `confirm`. | T | ✅ |
| FR-SAF-006 | Repeated camera failures (≥3) shall latch CAMERA_FAILURE and inhibit imaging until CLEAR_FAULT. | VC-05. | T | ✅ |
| FR-SAF-007 | Storage below reserve shall inhibit imaging. | VC-10. | T | ✅ |

### 3.6 Ground segment & mission control — FR-GS

| ID | Requirement | Acceptance criteria | V | Status |
|---|---|---|---|---|
| FR-GS-001 | The dashboard shall show real-time status, mode, orbit/ground track, 3D attitude, battery SoC/V/A, temperatures, trends, camera control, gallery with metadata, command audit trail, link state, events/alarms. | Playwright e2e + manual review. | D, T | ✅ |
| FR-GS-002 | A SIMULATION / HARDWARE indicator shall be permanently visible. | Header badge + banner; e2e asserts. | T | ✅ |
| FR-GS-003 | Telemetry, events, commands and image metadata shall be stored in PostgreSQL (SQLite for local dev); images in S3-compatible storage (MinIO). | Compose stack; integration tests use SQLite + local object store. | T, I | 🟡 Postgres/MinIO path not yet executed in CI here |
| FR-GS-004 | Decoded telemetry shall be republished to an authenticated MQTT broker. | Broker rejects anonymous clients; bridge requires credentials. | I | 🟡 not yet tested against a live broker |
| FR-GS-005 | Commanding shall require operator authentication; reads may be unauthenticated on the local network (TBC). | 401 without token. | T | ✅ |
| FR-GS-006 | Critical alarms shall be acknowledgeable by an operator and the acknowledging identity recorded. | `/api/events/{id}/ack`. | T | ✅ |

### 3.7 Power & ADCS simulation — FR-PWR / FR-ADC

| ID | Requirement | Acceptance criteria | V | Status |
|---|---|---|---|---|
| FR-PWR-001 | An energy-balance model shall simulate solar generation (attitude-dependent), eclipse, battery charge/discharge and mode-dependent load. | Unit tests: discharge in eclipse, charge in sun, clamping, OCV monotonic. | T | ✅ |
| FR-PWR-002 | All power-model parameters shall be labelled as simulation assumptions until replaced by measured data. | Module docstring; `docs/budgets.md`. | I | ✅ |
| FR-ADC-001 | Attitude shall be represented as unit quaternions. | Quaternion unit tests. | T | ✅ |
| FR-ADC-002 | Mock IMU and magnetometer adapters shall be provided. | `SimImu`, `SimMagnetometer`. | T | ✅ |
| FR-ADC-003 | No pointing-control capability shall be claimed without validated actuator and sensor models. | Kinematic-only model, labelled in code and UI. | I | ✅ |

## 4. Non-functional requirements

| ID | Requirement | Acceptance criteria | V | Status |
|---|---|---|---|---|
| NFR-SEC-001 | No credentials shall be hard-coded; secrets come from environment / `.env` (git-ignored). | Inspection; `scripts/init_env.py` generates secrets. | I | ✅ |
| NFR-SEC-002 | Services shall bind to localhost by default in Docker. | `127.0.0.1:` port bindings. | I | ✅ |
| NFR-SEC-003 | No RF transmission shall be possible from this software without authorization. | No RF transport implemented; see safety.md §5. | I | ✅ |
| NFR-REL-001 | The ground segment shall continue operating during a database outage, serving degraded reads from memory. | VC-13. | T | ✅ |
| NFR-REL-002 | No telemetry shall be lost across a DB outage up to 100 000 buffered records. | Row count after restore equals frames received. | T | ✅ |
| NFR-REL-003 | Network disconnection shall not lose onboard images. | VC-11. | T | ✅ |
| NFR-MNT-001 | Code shall be modular, typed and linted (ruff) with CI on every push. | `.github/workflows/ci.yml`. | I | ✅ |
| NFR-MNT-002 | The system shall be runnable after every milestone with documented commands. | README quick start. | D | ✅ |
| NFR-PRF-001 | The ground engine shall sustain ≥60× real-time simulation on a laptop. | Seed: 30 sim-min in ~2 s. | T | ✅ (measured, not in CI) |
| NFR-HON-001 | Unknown values shall be marked TBD; synthetic data shall be labelled; no flight qualification shall be claimed. | Inspection of docs/UI. | I | ✅ |

## 5. Traceability

Requirement → verification case → automated test mapping is maintained in
[`verification-plan.md`](verification-plan.md).
