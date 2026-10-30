"""Cooperative periodic task scheduler for the flight application.

Deterministic and single-threaded: the application calls ``run_due(now)``
once per tick. A task that raises is isolated (logged + counted) so one
faulty task cannot stop the others; repeated errors escalate via FDIR.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

log = logging.getLogger("onboard.scheduler")


@dataclass
class Task:
    name: str
    period_s: float
    fn: Callable[[float], None]
    next_run: float = 0.0
    runs: int = 0
    errors: int = 0
    last_error: str = ""


class TaskScheduler:
    def __init__(self) -> None:
        self.tasks: dict[str, Task] = {}

    def add(self, name: str, period_s: float, fn: Callable[[float], None]) -> None:
        if period_s <= 0:
            raise ValueError("period must be positive")
        self.tasks[name] = Task(name, period_s, fn)

    def set_period(self, name: str, period_s: float) -> None:
        if period_s <= 0:
            raise ValueError("period must be positive")
        self.tasks[name].period_s = period_s

    def run_due(self, now: float) -> None:
        for t in self.tasks.values():
            if now + 1e-9 < t.next_run:
                continue
            try:
                t.fn(now)
            except Exception as exc:  # noqa: BLE001 - task isolation is the point
                t.errors += 1
                t.last_error = repr(exc)
                log.exception("task %s failed", t.name)
            t.runs += 1
            t.next_run = now + t.period_s

    def reset(self) -> None:
        for t in self.tasks.values():
            t.next_run = 0.0
