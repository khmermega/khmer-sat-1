"""Image downlink queue with selective repeat, acknowledgement timeout and retry.

Flow: IMAGE_META, then IMAGE_CHUNK x N. The ground reassembles and verifies
the SHA-256, then replies with an authenticated IMAGE_ACK command:
  ok=true                    -> transfer complete, image removed from queue
  ok=false, missing=[i, ...] -> resend only those chunks (selective repeat)
  ok=false, need_meta=true   -> resend IMAGE_META
  ok=false (no list)         -> checksum failure: resend the whole image
If nothing at all is heard within ``ack_timeout_s`` the whole image is re-sent,
up to ``max_retries`` times before the transfer is abandoned (image stays
stored onboard and is re-queued after the next reboot).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum

MAX_NACKS = 50


class TransferState(StrEnum):
    QUEUED = "QUEUED"
    SENDING = "SENDING"
    AWAIT_ACK = "AWAIT_ACK"


@dataclass
class Transfer:
    image_id: str
    total_chunks: int
    state: TransferState = TransferState.QUEUED
    next_chunk: int = 0
    attempts: int = 0
    nacks: int = 0
    sent_at: float = 0.0
    meta_sent: bool = False
    resend: deque[int] = field(default_factory=deque)

    def next_index(self) -> int | None:
        """Next chunk index to transmit, or None when this round is done."""
        if self.resend:
            return self.resend.popleft()
        if self.next_chunk < self.total_chunks:
            i = self.next_chunk
            self.next_chunk += 1
            return i
        return None


@dataclass
class TransferResult:
    abandoned: list[str] = field(default_factory=list)


class DownlinkQueue:
    def __init__(self, ack_timeout_s: float = 60.0, max_retries: int = 3) -> None:
        self.ack_timeout_s = ack_timeout_s
        self.max_retries = max_retries
        self._q: deque[Transfer] = deque()

    def enqueue(self, image_id: str, total_chunks: int) -> None:
        if any(t.image_id == image_id for t in self._q):
            return
        self._q.append(Transfer(image_id, total_chunks))

    def __len__(self) -> int:
        return len(self._q)

    def ids(self) -> list[str]:
        return [t.image_id for t in self._q]

    def active(self) -> Transfer | None:
        return self._q[0] if self._q else None

    def ack(self, image_id: str) -> bool:
        for t in list(self._q):
            if t.image_id == image_id:
                self._q.remove(t)
                return True
        return False

    def nack(self, image_id: str, missing: list[int] | None = None, need_meta: bool = False) -> None:
        for t in self._q:
            if t.image_id != image_id:
                continue
            t.nacks += 1
            if t.nacks > MAX_NACKS:
                return  # ignore NACK storms; the ACK timeout path still applies
            if missing is None and not need_meta:
                # checksum failure - restart the whole image
                t.state, t.next_chunk, t.meta_sent = TransferState.QUEUED, 0, False
                t.resend.clear()
                return
            valid = sorted({i for i in (missing or []) if 0 <= i < t.total_chunks})
            t.resend.extend(i for i in valid if i not in t.resend)
            t.next_chunk = t.total_chunks  # only the requested chunks
            if need_meta:
                t.meta_sent = False
            t.state = TransferState.SENDING
            return

    def check_timeouts(self, now: float) -> TransferResult:
        res = TransferResult()
        t = self.active()
        if t and t.state is TransferState.AWAIT_ACK and now - t.sent_at > self.ack_timeout_s:
            if t.attempts >= self.max_retries:
                self._q.popleft()
                res.abandoned.append(t.image_id)
            else:
                t.state, t.next_chunk, t.meta_sent = TransferState.QUEUED, 0, False
                t.resend.clear()
        return res
