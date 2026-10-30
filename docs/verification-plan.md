# KHMER-SAT 1 — Verification Plan & Traceability

## 1. Test levels

| Level | Location | Runner | In CI |
|---|---|---|---|
| Unit (Python) | `tests/unit` | `uv run pytest tests/unit` | ✅ |
| Integration (engine: flight SW ↔ link ↔ ground ↔ DB) | `tests/integration/test_flight_ground.py` | pytest | ✅ |
| Integration (HTTP/WebSocket API, live engine) | `tests/integration/test_api.py` | pytest | ✅ |
| End-to-end (browser) | `ground-station/frontend/e2e` | Playwright (Chromium) | ✅ |
| Firmware unit (host, ASan/UBSan) | `firmware/watchdog-mcu/test` | `make test` | ✅ |
| Hardware-in-the-loop | `tests/hardware-in-loop` | `KS_HIL=1 pytest -m hil` | ❌ (bench only) |
| Docker stack | `docker-compose.yml` | `docker compose build` | ✅ build only |

## 2. Verification cases

| VC | Scenario | Test | Requirements |
|---|---|---|---|
| VC-01 | Telemetry continuity, 120 s, no gaps | `test_telemetry_continuity` | FR-OBC-003 |
| VC-02 | Capture → JPEG → SHA-256 → chunked downlink → verified storage | `test_ping_and_capture_downlink_verified`, e2e capture | FR-CAM-003..006, FR-CAM-009, FR-GS-003 |
| VC-03 | Forged, replayed, stale commands rejected | `test_forged_and_replayed_commands_rejected` | FR-TTC-003, FR-TTC-004 |
| VC-04 | Invalid commands rejected with reasons | `test_invalid_commands_rejected_with_reason` | FR-OBC-001, FR-TTC-005, FR-SAF-005 |
| VC-05 | Camera failure latch & CLEAR_FAULT | `test_camera_failure_latches_until_clear_fault` | FR-SAF-006 |
| VC-06 | Power loss → SAFE; interlocked recovery | `test_power_loss_enters_safe_and_recovery_is_interlocked` | FR-SAF-001, FR-SAF-003, FR-PWR-001 |
| VC-07 | Payload over-temperature → SAFE | `test_payload_overtemperature_enters_safe` | FR-SAF-002 |
| VC-08 | Watchdog recovery → SAFE | `test_watchdog_recovery`, firmware tests | FR-SAF-004, FR-OBC-005 |
| VC-09 | Watchdog storm → FAULT → CLEAR_FAULT | `test_watchdog_storm_enters_fault_then_clear` | FR-SAF-004 |
| VC-10 | Storage exhaustion inhibits imaging | `test_storage_exhaustion_inhibits_imaging`, `test_storage_save_load_and_exhaustion` | FR-SAF-007 |
| VC-11 | Network disconnection & recovery | `test_network_disconnection_and_recovery` | NFR-REL-003, FR-TTC-005 |
| VC-12 | Packet loss / corruption / duplication | `test_packet_loss_corruption_duplication`, `test_every_single_bit_flip_is_detected` | FR-TTC-002, FR-TTC-007, FR-TTC-008 |
| VC-13 | Database outage buffering & back-fill | `test_database_outage_buffers_and_backfills`, `test_telemetry_history_and_db_outage_fallback` | NFR-REL-001, NFR-REL-002 |
| VC-14 | Visibility-gated link (AOS/LOS) | `test_orbital_link_mode_follows_visibility` | FR-ORB-006 |
| VC-15 | Reboot preserves & re-queues images | `test_commanded_reboot_requeues_unacked_images` | FR-OBC-004 |
| VC-16 | Time & frame conversions | `tests/unit/test_frames_and_orbit.py` | FR-ORB-001..003 |
| VC-17 | Synthetic orbit labelling | `test_synthetic_elements_are_labelled`, `test_orbit_endpoints`, e2e | FR-ORB-004, NFR-HON-001 |
| VC-18 | SIMULATION indicator | e2e `dashboard shows live simulated telemetry…` | FR-GS-002 |
| VC-19 | Auth & critical-command interlock | `test_command_requires_auth`, `test_critical_command_interlock`, e2e | FR-GS-005, FR-SAF-005 |
| VC-20 | Explicit-UTC timestamps from DB | `test_timestamps_from_database_are_explicit_utc` | FR-ORB-002 |
| VC-21 | Quaternion / attitude kinematics | `tests/unit/test_models.py` | FR-ADC-001..003 |
| VC-22 | USB camera on bench tagged GROUND_TEST_HARDWARE | `test_usb_camera_capture_is_labelled_ground_test` (HIL) | FR-CAM-001, FR-CAM-006 |
| VC-23 | Watchdog MCU over UART | `test_watchdog_mcu_responds_to_heartbeat` (HIL) | FR-OBC-005 |

## 3. Demonstration scenarios

Against a running ground station (`scripts/demo_scenarios.py`):
`imaging-pass`, `lossy-link`, `watchdog-recovery`, `power-emergency`,
`critical-command`, `orbital-pass`.

## 4. Not yet verified

- PostgreSQL / MinIO / MQTT path end-to-end (Compose stack builds in CI; a full-stack smoke test is pending).
- All hardware adapters (camera, GNSS serial, IMU, EPS, watchdog MCU on hardware).
- RP2040 firmware port compile and run.
- Any flight environment (thermal-vacuum, vibration, radiation, EMC): out of scope.
