"""Time-tagged capture schedule (executed by the flight application)."""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from datetime import datetime

from simulator.orbit.frames import ensure_utc

MAX_SCHEDULED = 100


@dataclass(order=True, slots=True)
class ScheduledCapture:
    at_utc: datetime
    order: int
    command_id: str = field(compare=False)
    width: int | None = field(default=None, compare=False)
    height: int | None = field(default=None, compare=False)
    jpeg_quality: int | None = field(default=None, compare=False)


class CaptureScheduler:
    def __init__(self) -> None:
        self._heap: list[ScheduledCapture] = []
        self._order = itertools.count()

    def add(self, at_utc: datetime, command_id: str, **cfg: int | None) -> ScheduledCapture:
        if len(self._heap) >= MAX_SCHEDULED:
            raise ValueError("capture schedule full")
        item = ScheduledCapture(ensure_utc(at_utc), next(self._order), command_id, **cfg)
        heapq.heappush(self._heap, item)
        return item

    def due(self, now: datetime) -> list[ScheduledCapture]:
        out = []
        while self._heap and self._heap[0].at_utc <= now:
            out.append(heapq.heappop(self._heap))
        return out

    def clear(self) -> None:
        self._heap.clear()

    def __len__(self) -> int:
        return len(self._heap)
