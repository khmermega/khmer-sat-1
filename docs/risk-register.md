# KHMER-SAT 1 — Preliminary Risk Register

Likelihood (L) and impact (I): 1 (low) – 5 (high). Score = L × I.

| ID | Risk | L | I | Score | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|---|
| R-01 | Regulatory: no frequency coordination / licence for RF downlink | 4 | 5 | 20 | Engage TRC early; IARU coordination if amateur band; wired-only until authorised | TBD | Open |
| R-02 | Python OBC prototype unsuitable for flight (timing, memory, radiation) | 4 | 4 | 16 | Independent watchdog MCU; HAL keeps logic portable; plan flight OBC trade study | TBD | Open |
| R-03 | COTS Raspberry Pi / camera not radiation tolerant | 5 | 3 | 15 | Treat as engineering model only; flight parts TBD | TBD | Open |
| R-04 | Downlink capacity insufficient for imaging objectives | 3 | 4 | 12 | Binary HK format, on-board thumbnails, selective downlink, compression trade | TBD | Open |
| R-05 | Thermal behaviour unknown (simulator coefficients are assumptions) | 4 | 3 | 12 | Thermal analysis + bench thermal tests; replace model parameters | TBD | Open |
| R-06 | Power budget not closed (all values assumptions) | 4 | 4 | 16 | Select EPS/panels/battery; measure loads per mode on the bench | TBD | Open |
| R-07 | No validated ADCS: imaging pointing not guaranteed | 4 | 4 | 16 | Kinematic model only; validated sensor/actuator models before any control law | TBD | Open |
| R-08 | Synthetic data mistaken for real data | 2 | 4 | 8 | Labels in API, UI banner, image pixels and metadata provenance | — | Mitigated |
| R-09 | COTS GNSS CoCom limits prevent fixes in orbit | 4 | 3 | 12 | Space-capable receiver; onboard propagation from uplinked elements | TBD | Open |
| R-10 | Clock drift breaks anti-replay window | 3 | 3 | 9 | GNSS time, ground time-sync command (M4), wider window in SAFE | TBD | Open |
| R-11 | Static shared tokens / HMAC key compromise | 3 | 4 | 12 | Per-user auth (OIDC), key rotation, HSM/secure element, downlink auth | TBD | Open |
| R-12 | Database or object store outage loses data | 2 | 3 | 6 | Buffered persistence, degraded reads, onboard retention until ACK | — | Mitigated (tested) |
| R-13 | Li-ion battery hazard during integration | 2 | 5 | 10 | Bench supply only; protection circuit and procedure before cells | TBD | Open |
| R-14 | Single developer / knowledge concentration | 3 | 3 | 9 | Docs, ADRs, CI, traceability | TBD | Open |
| R-15 | Launch opportunity and mass/volume limits unknown | 3 | 4 | 12 | Track CDS revision; early contact with launch brokers | TBD | Open |
