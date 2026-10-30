"""Operating-mode state machine.

Allowed transitions (docs/safety.md §1). Anything not listed is rejected.

    BOOT     -> NOMINAL | SAFE | FAULT
    NOMINAL  -> IMAGING | DOWNLINK | SAFE | FAULT
    IMAGING  -> NOMINAL | SAFE | FAULT
    DOWNLINK -> NOMINAL | SAFE | FAULT
    SAFE     -> NOMINAL (interlocked) | FAULT
    FAULT    -> SAFE (CLEAR_FAULT only)
    any      -> BOOT (reset only - REBOOT command or watchdog)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from shared.schemas import Mode

ALLOWED: dict[Mode, frozenset[Mode]] = {
    Mode.BOOT: frozenset({Mode.NOMINAL, Mode.SAFE, Mode.FAULT}),
    Mode.NOMINAL: frozenset({Mode.IMAGING, Mode.DOWNLINK, Mode.SAFE, Mode.FAULT}),
    Mode.IMAGING: frozenset({Mode.NOMINAL, Mode.SAFE, Mode.FAULT}),
    Mode.DOWNLINK: frozenset({Mode.NOMINAL, Mode.SAFE, Mode.FAULT}),
    Mode.SAFE: frozenset({Mode.NOMINAL, Mode.FAULT}),
    Mode.FAULT: frozenset({Mode.SAFE}),
}

#: Modes an operator may request directly with SET_MODE.
COMMANDABLE: frozenset[Mode] = frozenset({Mode.NOMINAL, Mode.IMAGING, Mode.DOWNLINK, Mode.SAFE})


class TransitionError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(slots=True)
class Transition:
    utc: datetime
    from_mode: Mode
    to_mode: Mode
    reason: str


class ModeManager:
    def __init__(self, on_change: Callable[[Transition], None] | None = None) -> None:
        self.mode = Mode.BOOT
        self.entered_at: datetime | None = None
        self.history: list[Transition] = []
        self._on_change = on_change

    def can_transition(self, target: Mode) -> bool:
        return target in ALLOWED[self.mode]

    def transition(self, target: Mode, reason: str, now: datetime) -> Transition:
        if target == self.mode:
            raise TransitionError(f"already_in_{target.value}")
        if not self.can_transition(target):
            raise TransitionError(f"illegal_transition_{self.mode.value}_to_{target.value}")
        return self._set(target, reason, now)

    def reset(self, reason: str, now: datetime) -> Transition:
        """Processor reset: always lands in BOOT regardless of current mode."""
        return self._set(Mode.BOOT, reason, now)

    def _set(self, target: Mode, reason: str, now: datetime) -> Transition:
        tr = Transition(now, self.mode, target, reason)
        self.mode = target
        self.entered_at = now
        self.history.append(tr)
        del self.history[:-200]
        if self._on_change:
            self._on_change(tr)
        return tr
