"""Link abstraction between the flight application and its transport.

Transports:
- ChannelLink: in-process simulated channel pair (simulator/communications).
- TcpFrameLink (tcp.py): wired Ethernet/USB-gadget link for bench tests.
RF transports are intentionally absent: no RF transmission is enabled
without licensing/authorization (docs/safety.md §5).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from simulator.communications.channel import Channel


class Link(Protocol):
    def send(self, frame: bytes) -> None: ...

    def receive(self) -> list[bytes]: ...


class ChannelLink:
    """One endpoint of a simulated duplex link (tx channel + rx channel)."""

    def __init__(self, tx: Channel, rx: Channel, clock: Callable[[], float]) -> None:
        self.tx, self.rx, self._clock = tx, rx, clock

    def send(self, frame: bytes) -> None:
        self.tx.send(frame, self._clock())

    def receive(self) -> list[bytes]:
        return self.rx.receive(self._clock())
