# KHMER-SAT 1 — Hardware BOM & Bench Integration

> No component specifications are invented here. Parts are listed by role;
> part numbers, masses, power and prices are **TBD** until selected and
> verified against datasheets.

## 1. Prototype vs flight separation

| Role | Prototype / bench (now) | Future flight-qualified (TBD) |
|---|---|---|
| Onboard computer | Raspberry Pi (4/5 or Zero 2 W) running `onboard/` | Space-grade or radiation-tolerant OBC, TBD |
| Watchdog / health MCU | Raspberry Pi Pico (RP2040) running `firmware/watchdog-mcu` | Rad-tolerant MCU with flight firmware, TBD |
| Camera | USB UVC webcam or Raspberry Pi camera module | EO imager with qualified optics, TBD |
| GNSS | COTS NMEA receiver (UART) — CoCom-limited | Space GNSS receiver, TBD |
| IMU / magnetometer | COTS I²C breakout, TBD | Qualified ADCS sensors, TBD |
| EPS / battery | Current-limited bench supply (**no Li-ion cells yet**) | CubeSat EPS + protected battery pack, TBD |
| Communications | Wired Ethernet / USB link to ground PC (TCP) | Licensed radio (UHF/S-band TBD) |
| Structure | Bench fixture / 3D-printed mock-up (`cad/`) | 3U CubeSat structure, TBD |

## 2. Bench BOM (roles only)

| # | Item | Qty | Part | Notes |
|---|---|---|---|---|
| 1 | Raspberry Pi + power supply + microSD | 1 | TBD | Raspberry Pi OS 64-bit |
| 2 | Raspberry Pi camera module **or** USB UVC camera | 1 | TBD | |
| 3 | Raspberry Pi Pico | 1 | TBD | watchdog MCU |
| 4 | NPN transistor / MOSFET + resistors | 1 set | TBD | open-drain reset drive |
| 5 | Load switch module | 1 | TBD | OBC power cycling |
| 6 | GNSS module (UART, NMEA) + antenna | 1 | TBD | |
| 7 | IMU + magnetometer breakout (I²C) | 1 | TBD | |
| 8 | Lab bench power supply, current-limited | 1 | TBD | |
| 9 | Ethernet cable / USB-C gadget link | 1 | — | wired comms only |
| 10 | Logic analyser / USB-UART adapter | 1 | TBD | debugging |

## 3. Wiring (bench)

```
 Bench PSU (current-limited) ──▶ load switch ──▶ Raspberry Pi 5V
                                   ▲ EN
 Pico GP14 ────────────────────────┘
 Pico GP15 ──▶ NPN/open-drain ──▶ Pi RUN/reset
 Pico GP0 (TX) ──▶ Pi GPIO15 RXD      Pico GP1 (RX) ◀── Pi GPIO14 TXD
 Pico GP26/ADC0 ◀── divider ◀── Pi 5V rail
 GNSS TX ──▶ Pi UART (second UART / USB-serial), 3.3 V
 IMU/mag SDA/SCL ──▶ Pi GPIO2/GPIO3 (I²C1), 3.3 V
 Camera ──▶ CSI ribbon or USB
 Pi Ethernet ──▶ ground-station PC
 Common GND for all boards
```

Verify every pin against the exact board revision before powering. All logic is 3.3 V.

## 4. Bring-up procedure (milestone M3)

1. Power the Pi alone from the bench supply with a current limit; record idle current.
2. Install: `sudo apt install python3-picamera2` (CSI camera) and clone this repo; `uv sync --extra hardware`.
3. Camera HIL: `KS_HIL=1 uv run pytest -m hil tests/hardware-in-loop -k camera`. Confirm images are tagged `GROUND_TEST_HARDWARE`.
4. Flash the Pico (Pico SDK build of `src/main_rp2040.c`), connect UART only (reset line disconnected), verify `HB` → `OK 0`.
5. Connect the reset line; stop heartbeats; confirm the Pi resets after the timeout.
6. GNSS: confirm NMEA GGA parsing on the bench (fix outdoors).
7. Wired link: run `onboard` with `TcpFrameLink` to the ground PC (ground TCP client — M3 deliverable).
8. Only then integrate the remaining sensors one at a time.

## 5. Configuration

| Setting | Where |
|---|---|
| UART for watchdog | `SerialWatchdogMCU(port="/dev/serial0")` |
| Camera device | `V4L2Camera(device=0)` / `PiCamera(camera_num=0)` |
| HMAC key | `COMMAND_HMAC_KEY` env on both ground and Pi (same value) |
| Thresholds | `onboard/config.py` |
