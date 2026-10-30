# Watchdog & health MCU firmware

An independent microcontroller that resets (and, if needed, power-cycles) the
prototype onboard computer (Raspberry Pi) when its heartbeats stop.

| File | Purpose |
|---|---|
| `include/watchdog.h`, `src/watchdog.c` | Portable C99 core state machine (no hardware dependencies) |
| `test/test_watchdog.c` | Host unit tests (ASan + UBSan, `-Werror -Wconversion`) |
| `src/main_rp2040.c` | Raspberry Pi Pico board port — **not yet built or run on hardware** |

## State machine

```
           heartbeat                 no HB > timeout                pulse done
  GRACE ─────────────▶ ARMED ───────────────────────▶ RESETTING ─────────────▶ GRACE
    │ grace expired                                       │
    └──────────────────────────▶ (reset) ◀────────────────┘
  ≥ 3 resets within 1 h ─▶ POWER_CYCLE (load switch off 5 s) ─▶ GRACE
  bus < UV threshold (any state) ─▶ UNDERVOLTAGE (hold reset) ─▶ GRACE when bus > threshold + hysteresis
```

UART protocol (115200 8N1, line-terminated): OBC sends `HB`, MCU answers
`OK <reset_count>`; `STATUS` returns `STATE <name> RESETS <n> CYCLES <n>`.
The Python twin is `onboard/safety/watchdog.py` (`SimWatchdogMCU`,
`SerialWatchdogMCU`).

## Build & test (host)

```bash
make test
```

## Bench wiring (placeholder — verify against your boards before powering)

| Pico pin | Signal | Raspberry Pi |
|---|---|---|
| GP0 (UART0 TX) | MCU → OBC | GPIO15 / RXD (pin 10) |
| GP1 (UART0 RX) | OBC → MCU | GPIO14 / TXD (pin 8) |
| GP15 | reset (via NPN/open-drain) | `RUN` header (Pi 4) / `PWR_BUT`/`RUN` (Pi 5) |
| GP14 | load-switch enable | OBC 5 V supply switch |
| GP26 / ADC0 | OBC rail via divider | 5 V rail (divider ratio TBD) |
| GND | common ground | GND |

Both boards use 3.3 V logic. Power the bench from a **current-limited** supply.
All thresholds in `ks_wdt_default_config()` are placeholders (TBD in
`docs/safety.md`).
