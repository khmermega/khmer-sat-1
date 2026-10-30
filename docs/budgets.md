# KHMER-SAT 1 — Preliminary Budgets

> **Status: preliminary.** Values marked *assumption* are the inputs used by
> the simulator so it can run; they are **not** component specifications and
> must be replaced with datasheet/measured values. Values marked *measured*
> were measured on this prototype software. Everything else is **TBD**.

## 1. Power budget

### 1.1 Loads by mode (simulation assumptions, `simulator/power/eps.py`)

| Mode | Assumed total load (W) | Real value |
|---|---|---|
| BOOT | 1.5 | TBD |
| NOMINAL | 2.0 | TBD |
| IMAGING | 4.5 | TBD |
| DOWNLINK | 5.0 | TBD (depends on radio, which is TBD) |
| SAFE | 1.2 | TBD |
| FAULT | 1.0 | TBD |

### 1.2 Generation and storage (simulation assumptions)

| Item | Assumption | Real value |
|---|---|---|
| Body-mounted panel peak, each long face (±X, ±Y) | 6.0 W at normal incidence | TBD (panel selection) |
| End faces (±Z) | 2.0 W | TBD |
| Battery capacity | 20 Wh, 2S Li-ion, generic OCV curve | TBD |
| Internal resistance | 0.12 Ω | TBD |
| Charge efficiency | 0.92 | TBD |

### 1.3 Orbit-average energy balance

`E_gen = Σ_faces P_face · <max(0, n̂·ŝ)> · t_sun`, `E_use = Σ_modes P_mode · t_mode`.
Required: `E_gen − E_use ≥ margin` (margin TBD, typically ≥ 20 %).
Eclipse fraction for the synthetic 500 km orbit depends on the beta angle and
varies through the year — it is **computed by the simulator**, not assumed.
A real budget requires panel, battery, EPS and radio selection (TBD).

## 2. Mass budget

| Subsystem | Mass (g) | Source |
|---|---|---|
| Structure (3U) | TBD | |
| OBC (prototype: Raspberry Pi — not flight hardware) | TBD | |
| Watchdog MCU board | TBD | |
| Camera + optics | TBD | |
| EPS + battery | TBD | |
| Solar panels | TBD | |
| Radio + antenna | TBD | |
| ADCS sensors / actuators | TBD | |
| Harness, fasteners | TBD | |
| **Total** | **TBD** | |
| Margin | TBD (≥ 20 % at this maturity) | |
| Limit | Per CubeSat Design Specification revision and launch-provider ICD — **verify current limits** | |

## 3. Storage budget

| Item | Size | Source |
|---|---|---|
| Housekeeping frame | 817 B (mean, JSON payload) | *measured* |
| Event frame | ~180 B | *measured* |
| Image 640×480, q85 | ~33 KB | *measured on synthetic scenes* |
| Image 1280×960, q85 | ~79 KB | *measured on synthetic scenes* |
| Image 1920×1440, q85 | ~128 KB | *measured on synthetic scenes* |
| Image 2592×1944, q85 | ~196 KB | *measured on synthetic scenes* |
| Onboard image quota (sim) | 64 MiB (configurable) | *assumption* |
| Reserve before imaging inhibit | 1 MiB | *assumption* |

Real Earth imagery will compress differently from synthetic noise terrain —
re-measure with the selected sensor. Capacity at 1280×960: 64 MiB / ~79 KB ≈ 850 images
(plus thumbnails ≈ +10 %).

## 4. Data-rate budget

| Flow | Rate | Notes |
|---|---|---|
| Housekeeping @ 2 s | 817 B / 2 s ≈ 3.3 kbit/s | *measured*; packed binary format would cut this substantially |
| Housekeeping @ 10 s | ≈ 0.65 kbit/s | |
| Image chunk frame | 3115 B (3072 B data + 43 B overhead, 1.4 %) | *measured* |
| One 1280×960 image | ~79 KB ≈ 26 chunks | |
| Radio data rate | **TBD** | radio and licence TBD |
| Pass duration (synthetic orbit, Phnom Penh, ≥10° mask) | ~5–7.5 min for high passes | *computed* by `/api/orbit/passes` for the synthetic orbit only |
| Images per pass | = (rate × pass time × efficiency − HK) / image size | TBD until rate known |

Example for planning only: at a hypothetical 9.6 kbit/s with 70 % efficiency,
a 7 min pass carries ≈ 350 KB ≈ 4 images at 1280×960. This is arithmetic, not
a performance claim.
