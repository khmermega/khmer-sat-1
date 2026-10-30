# KHMER-SAT 1 — Safety, Modes and Fault Handling

> Prototype software. All thresholds below are placeholders chosen for the
> simulator and bench; flight values are **TBD** from component datasheets,
> qualification tests and a hazard analysis.

## 1. Operating modes

| Mode | Purpose | Payload | Downlink | Attitude (sim) |
|---|---|---|---|---|
| BOOT | Startup, persistent-state load, hardware init (5 s) | off | HK only | tumble |
| NOMINAL | Housekeeping, ready for tasks | standby | HK | ideal nadir (kinematic) |
| IMAGING | Capture in progress (5 s hold, then auto-return) | on | HK | ideal nadir |
| DOWNLINK | Transferring queued images | standby | HK + images | ideal nadir |
| SAFE | Minimal load, wait for ground | off | HK | tumble |
| FAULT | Unrecoverable condition latched; wait for ground | off | HK | tumble |

### Transition table

| From \ To | BOOT | NOMINAL | IMAGING | DOWNLINK | SAFE | FAULT |
|---|---|---|---|---|---|---|
| BOOT | – | boot OK | ✗ | ✗ | boot after watchdog / SAFE fault | watchdog storm |
| NOMINAL | reset | – | cmd / capture | cmd / auto | cmd / FDIR | task errors |
| IMAGING | reset | hold expiry / FDIR inhibit | – | ✗ | FDIR / cmd | task errors |
| DOWNLINK | reset | queue empty / link lost / cmd | ✗ | – | FDIR / cmd | task errors |
| SAFE | reset | **cmd, interlocked** | ✗ | ✗ | – | task errors |
| FAULT | reset | ✗ | ✗ | ✗ | **CLEAR_FAULT** | – |

✗ = rejected with `illegal_transition_<FROM>_to_<TO>`. "reset" = processor
reset only (REBOOT command or watchdog). FAULT is never commandable directly.

### Recovery behaviour

- After a **watchdog** reset the OBC boots into **SAFE** (conservative) — the
  operator returns it to NOMINAL once the cause is understood.
- After **≥3 watchdog resets within 1 h** it boots into **FAULT**. CLEAR_FAULT
  (critical) clears the history and moves to SAFE. The MCU additionally
  power-cycles the OBC on a reset storm (firmware).
- After a **commanded** reboot or power-on it boots into NOMINAL if no
  SAFE-class fault is active.
- Volatile state (scheduled captures, replay cache, in-flight transfers) is
  lost on reset; persistent state (boot count, images, acknowledged images,
  watchdog history) survives. Un-acknowledged images are re-queued.

## 2. FDIR rules (evaluated every 1 s)

| Fault | Condition (placeholder) | Action | Latched |
|---|---|---|---|
| LOW_BATTERY | SoC < 30 % | → SAFE | no |
| BATTERY_TEMP | battery < 0 °C or > 45 °C | → SAFE | no |
| PAYLOAD_OVERTEMP | payload > 45 °C | → SAFE | no |
| PAYLOAD_UNDERTEMP | payload < −10 °C | inhibit imaging | no |
| CPU_OVERTEMP | CPU > 75 °C | → SAFE | no |
| CAMERA_FAILURE | ≥ 3 consecutive capture failures | inhibit imaging | **yes** (CLEAR_FAULT) |
| STORAGE_FULL | free < 1 MiB reserve | inhibit imaging | no |
| GNSS_NO_FIX | no fix | informational | no |
| task errors | any scheduler task ≥ 5 exceptions | → FAULT | yes |

SAFE-entry recovery interlock: SoC ≥ 45 % **and** no SAFE-class fault active.

## 3. Command safety

1. **Authentication** — HMAC-SHA256 with a ≥256-bit key from `COMMAND_HMAC_KEY`.
2. **Anti-replay** — ±30 s timestamp window plus (timestamp, seq) de-duplication.
3. **Validation** — schema (`extra="forbid"`), argument ranges, mode legality.
4. **Interlocks** — onboard power/thermal/fault checks before execution.
5. **Two-layer critical command interlock**
   - Ground: admin role, `POST /api/commands/arm` then `/execute` within 30 s,
     single use, same principal. Direct send returns 409.
   - Onboard: critical commands rejected unless `args.confirm == <type>`, which
     only the ground adds after ARM/EXECUTE.
6. **Audit** — every command (operator, seq, args, ack status, reason, times) is
   persisted and shown in the dashboard; interlock tokens are not echoed.

## 4. Security notes and limitations

- Prototype operator auth = two static bearer tokens (operator, admin). Per-user
  identity (OIDC), MFA, key rotation and HSM-backed command keys are future work (R-11).
- Read-only API endpoints are unauthenticated on the assumption of a trusted
  local network; Docker binds to 127.0.0.1. Do not expose to the internet.
- The shared HMAC key on a Raspberry Pi SD card is extractable by anyone with
  physical access — acceptable on the bench only.
- Downlink frames are not authenticated in v1.

## 5. Bench & RF safety

- **No RF transmission.** This repository contains no radio driver. Any RF
  transmission requires the applicable national authorisation (Cambodia: the
  Telecommunication Regulator of Cambodia — TRC), frequency coordination (e.g.
  IARU for amateur-satellite bands) and ITU filings as applicable. Status: TBD.
- Use a **current-limited bench power supply** for all hardware integration;
  set the limit just above the measured idle draw and increase deliberately.
- Li-ion cells: do not integrate real cells until a battery protection circuit,
  charge controller and fire-safe handling procedure are in place.
- ESD precautions for camera sensors and the OBC.
- Never point optics at the sun during ground testing.
