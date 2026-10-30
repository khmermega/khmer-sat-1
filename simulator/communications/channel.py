"""Simulated space-ground link with configurable impairments.

Impairments (all probabilities per frame): loss, duplication, single-bit
corruption, plus a fixed latency. A link can also be taken DOWN entirely
(disconnection, or no ground-station visibility in orbital link mode).
No RF is modelled or emitted - this is a software channel only.
"""

from __future__ import annotations

import heapq
import itertools
import random
from dataclasses import dataclass, field


@dataclass(slots=True)
class Impairments:
    loss: float = 0.0
    duplicate: float = 0.0
    corrupt: float = 0.0
    delay_s: float = 0.0

    def validate(self) -> None:
        for name in ("loss", "duplicate", "corrupt"):
            v = getattr(self, name)
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{name} probability must be within [0, 1]")
        if self.delay_s < 0:
            raise ValueError("delay must be >= 0")


@dataclass(slots=True)
class ChannelStats:
    sent: int = 0
    delivered: int = 0
    dropped: int = 0
    duplicated: int = 0
    corrupted: int = 0
    blocked: int = 0
    bytes_delivered: int = 0


@dataclass
class Channel:
    name: str
    impairments: Impairments = field(default_factory=Impairments)
    seed: int | None = None
    up: bool = True
    stats: ChannelStats = field(default_factory=ChannelStats)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)
        self._queue: list[tuple[float, int, bytes]] = []
        self._counter = itertools.count()

    def send(self, frame: bytes, now: float) -> None:
        self.stats.sent += 1
        if not self.up:
            self.stats.blocked += 1
            return
        imp = self.impairments
        if self._rng.random() < imp.loss:
            self.stats.dropped += 1
            return
        copies = 1
        if self._rng.random() < imp.duplicate:
            copies = 2
            self.stats.duplicated += 1
        for _ in range(copies):
            data = frame
            if data and self._rng.random() < imp.corrupt:
                buf = bytearray(data)
                bit = self._rng.randrange(len(buf) * 8)
                buf[bit // 8] ^= 1 << (bit % 8)
                data = bytes(buf)
                self.stats.corrupted += 1
            heapq.heappush(self._queue, (now + imp.delay_s, next(self._counter), data))

    def receive(self, now: float) -> list[bytes]:
        out: list[bytes] = []
        while self._queue and self._queue[0][0] <= now:
            _, _, data = heapq.heappop(self._queue)
            out.append(data)
            self.stats.delivered += 1
            self.stats.bytes_delivered += len(data)
        return out

    def pending(self) -> int:
        return len(self._queue)
