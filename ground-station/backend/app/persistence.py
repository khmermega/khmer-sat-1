"""Buffered, outage-tolerant database writer.

All writes go through an in-memory queue that is flushed once per engine tick.
If the database is unreachable the queue is retained (bounded) and flushed when
the database returns - telemetry continuity is preserved across DB outages up
to ``max_pending`` records (requirement NFR-REL-002).
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import sessionmaker

from .db import Base, TelemetryRow

log = logging.getLogger("ground.persistence")


class SimulatedOutage(RuntimeError):
    pass


class Persistence:
    def __init__(self, session_factory: sessionmaker, max_pending: int = 100_000) -> None:
        self._sf = session_factory
        self._pending: deque[Base] = deque()
        self._lock = threading.Lock()
        self._flush_lock = threading.Lock()
        self.max_pending = max_pending
        self.db_ok = True
        self.simulate_outage = False
        self.dropped = 0
        self.on_status_change: Callable[[bool], None] | None = None

    def add(self, row: Base) -> None:
        with self._lock:
            self._pending.append(row)
            while len(self._pending) > self.max_pending:
                # Shed oldest telemetry first; never shed commands/events/images.
                for i, r in enumerate(self._pending):
                    if isinstance(r, TelemetryRow):
                        del self._pending[i]
                        self.dropped += 1
                        break
                else:
                    break

    @property
    def pending(self) -> int:
        return len(self._pending)

    def flush(self) -> bool:
        # Serialise flushes (engine thread vs shutdown) and take ownership of the
        # batch atomically, so concurrent add() calls are never lost or double-written.
        with self._flush_lock:
            with self._lock:
                batch = list(self._pending)
                self._pending.clear()
            if not batch and self.db_ok and not self.simulate_outage:
                return True
            try:
                if self.simulate_outage:
                    raise SimulatedOutage("simulated database outage")
                with self._sf() as s:
                    for row in batch:
                        s.merge(row)
                    s.commit()
            except Exception as exc:  # noqa: BLE001 - any DB error means outage
                with self._lock:
                    self._pending.extendleft(reversed(batch))
                self._set_ok(False, exc)
                return False
            self._set_ok(True)
            return True

    def _set_ok(self, ok: bool, exc: Exception | None = None) -> None:
        if ok != self.db_ok:
            self.db_ok = ok
            if ok:
                log.info("database restored")
            else:
                log.error("database unavailable: %s", exc)
            if self.on_status_change:
                self.on_status_change(ok)

    def query(self, fn: Callable[[Any], Any]) -> Any:
        """Run a read query; raises if the DB is down (callers fall back to caches)."""
        if self.simulate_outage:
            raise SimulatedOutage("simulated database outage")
        with self._sf() as s:
            return fn(s)
