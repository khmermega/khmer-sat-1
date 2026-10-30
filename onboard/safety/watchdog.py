"""Watchdog heartbeat interface to the independent health MCU.

The MCU (firmware/watchdog-mcu) resets the onboard computer if heartbeats stop
for longer than its timeout. SimWatchdogMCU mirrors the C state machine in
firmware/watchdog-mcu/src/watchdog.c so the reset path can be exercised in
software; SerialWatchdogMCU talks to the real MCU over UART.
"""

from __future__ import annotations

from typing import Protocol


class WatchdogMCU(Protocol):
    def kick(self, now_s: float) -> None: ...

    def poll(self, now_s: float) -> bool:
        """Return True if the MCU has asserted a reset since the last poll."""
        ...

    @property
    def reset_count(self) -> int: ...


class SimWatchdogMCU:
    def __init__(self, timeout_s: float = 10.0) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout must be positive")
        self.timeout_s = timeout_s
        self._last_kick: float | None = None
        self._reset_count = 0

    def kick(self, now_s: float) -> None:
        self._last_kick = now_s

    def poll(self, now_s: float) -> bool:
        if self._last_kick is None:
            self._last_kick = now_s  # arm on first poll (MCU boots with the OBC)
            return False
        if now_s - self._last_kick > self.timeout_s:
            self._reset_count += 1
            self._last_kick = now_s  # MCU re-arms after asserting reset
            return True
        return False

    @property
    def reset_count(self) -> int:
        return self._reset_count


class SerialWatchdogMCU:  # pragma: no cover - requires hardware
    """UART protocol: OBC sends b"HB\\n"; MCU replies b"OK <resets>\\n".

    A reset by the real MCU power-cycles this computer, so poll() only reports
    the reset counter change observed after boot.
    """

    def __init__(self, port: str, baud: int = 115200) -> None:
        import serial  # type: ignore[import-not-found]

        self._ser = serial.Serial(port, baud, timeout=0.2)
        self._resets = 0

    def kick(self, now_s: float) -> None:
        self._ser.write(b"HB\n")
        line = self._ser.readline().decode(errors="replace").strip()
        if line.startswith("OK "):
            self._resets = int(line.split()[1])

    def poll(self, now_s: float) -> bool:
        return False

    @property
    def reset_count(self) -> int:
        return self._resets
