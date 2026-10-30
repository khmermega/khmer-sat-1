"""Command authentication (HMAC-SHA256, truncated to 128 bits) and anti-replay.

Threat model and limitations are documented in docs/safety.md §4. Notably:
- Commands are authenticated, NOT encrypted (amateur-band rules generally forbid
  obscuring content; confidentiality is TBD pending licensing advice).
- The shared key is loaded from the environment (COMMAND_HMAC_KEY) - never hardcoded.
"""

from __future__ import annotations

import hashlib
import hmac
from collections import OrderedDict

from .packet import AUTH_TAG_SIZE, Flags, Packet


class AuthError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def parse_key(hex_key: str) -> bytes:
    """Parse a hex-encoded key; require at least 256 bits."""
    try:
        key = bytes.fromhex(hex_key.strip())
    except ValueError as exc:
        raise ValueError("COMMAND_HMAC_KEY must be hex encoded") from exc
    if len(key) < 32:
        raise ValueError("COMMAND_HMAC_KEY must be at least 32 bytes (64 hex chars)")
    return key


def compute_tag(key: bytes, packet: Packet) -> bytes:
    return hmac.new(key, packet.signed_region(), hashlib.sha256).digest()[:AUTH_TAG_SIZE]


def sign(key: bytes, packet: Packet) -> Packet:
    """Set the AUTHENTICATED flag and attach the tag (mutates and returns packet)."""
    packet.flags |= Flags.AUTHENTICATED
    packet.auth_tag = compute_tag(key, packet)
    return packet


def verify(key: bytes, packet: Packet) -> None:
    if not packet.flags & Flags.AUTHENTICATED:
        raise AuthError("unauthenticated")
    if not hmac.compare_digest(compute_tag(key, packet), packet.auth_tag):
        raise AuthError("bad_signature")


class ReplayGuard:
    """Rejects stale or previously-seen commands.

    A command is accepted only if
      1. |timestamp - now| <= window_ms, and
      2. the (timestamp_ms, seq) pair has not been seen inside the window.

    Keying on (timestamp, seq) rather than a bare counter means a ground-station
    restart (which resets its sequence counter) does not lock out commanding,
    while an exact replay is still rejected.
    """

    def __init__(self, window_ms: int = 30_000, max_entries: int = 10_000) -> None:
        self.window_ms = window_ms
        self.max_entries = max_entries
        self._seen: OrderedDict[tuple[int, int], int] = OrderedDict()

    def check_and_record(self, packet: Packet, now_ms: int) -> None:
        self._expire(now_ms)
        if abs(packet.timestamp_ms - now_ms) > self.window_ms:
            raise AuthError("stale_timestamp")
        key = (packet.timestamp_ms, packet.seq)
        if key in self._seen:
            raise AuthError("replay")
        self._seen[key] = packet.timestamp_ms
        while len(self._seen) > self.max_entries:
            self._seen.popitem(last=False)

    def _expire(self, now_ms: int) -> None:
        cutoff = now_ms - 2 * self.window_ms
        stale = [k for k, ts in self._seen.items() if ts < cutoff]
        for k in stale:
            del self._seen[k]
