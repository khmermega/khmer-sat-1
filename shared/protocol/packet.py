"""KHMER-SAT 1 space/ground packet format, protocol version 1.

Frame layout (big-endian), see docs/interfaces.md §2:

    offset size field
    0      2    sync word 0x4B53 ("KS")
    2      1    protocol version (currently 1)
    3      2    satellite id
    5      1    message type (MessageType)
    6      4    sequence number (uint32, per sender)
    10     8    UTC timestamp, milliseconds since Unix epoch (uint64)
    18     1    flags (bit0 = AUTHENTICATED)
    19     2    payload length N (uint16, <= MAX_PAYLOAD)
    21     N    payload body
    21+N   16   auth tag (only if AUTHENTICATED flag set) - truncated HMAC-SHA256
    ...    2    CRC-16/CCITT-FALSE over every preceding byte
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag

from .crc import crc16_ccitt

SYNC_WORD = 0x4B53
PROTOCOL_VERSION = 1
HEADER_FORMAT = ">HBHBIQBH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 21 bytes
AUTH_TAG_SIZE = 16
CRC_SIZE = 2
MAX_PAYLOAD = 8192


class MessageType(IntEnum):
    """Message types. Values are part of the ICD - never renumber."""

    HOUSEKEEPING = 0x01  # downlink: periodic telemetry
    EVENT = 0x02  # downlink: onboard event / alarm
    COMMAND_ACK = 0x03  # downlink: command accepted / rejected / completed
    IMAGE_META = 0x10  # downlink: image metadata (precedes chunks)
    IMAGE_CHUNK = 0x11  # downlink: binary image chunk
    COMMAND = 0x80  # uplink: authenticated telecommand


class Flags(IntFlag):
    NONE = 0
    AUTHENTICATED = 0x01


class PacketError(ValueError):
    """Raised for any malformed frame. ``reason`` is a stable machine-readable code."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass(slots=True)
class Packet:
    sat_id: int
    msg_type: MessageType
    seq: int
    timestamp_ms: int
    payload: bytes = b""
    flags: Flags = Flags.NONE
    auth_tag: bytes = b""
    version: int = PROTOCOL_VERSION
    # Filled in by decode() for diagnostics.
    raw_size: int = field(default=0, compare=False)

    def header_bytes(self) -> bytes:
        return struct.pack(
            HEADER_FORMAT,
            SYNC_WORD,
            self.version,
            self.sat_id,
            int(self.msg_type),
            self.seq,
            self.timestamp_ms,
            int(self.flags),
            len(self.payload),
        )

    def signed_region(self) -> bytes:
        """Bytes covered by the HMAC: header + payload."""
        return self.header_bytes() + self.payload


def _validate_fields(p: Packet) -> None:
    if not 0 <= p.sat_id <= 0xFFFF:
        raise PacketError("bad_sat_id", str(p.sat_id))
    if not 0 <= p.seq <= 0xFFFFFFFF:
        raise PacketError("bad_seq", str(p.seq))
    if not 0 <= p.timestamp_ms <= 0xFFFFFFFFFFFFFFFF:
        raise PacketError("bad_timestamp", str(p.timestamp_ms))
    if len(p.payload) > MAX_PAYLOAD:
        raise PacketError("payload_too_large", str(len(p.payload)))
    if p.flags & Flags.AUTHENTICATED and len(p.auth_tag) != AUTH_TAG_SIZE:
        raise PacketError("bad_auth_tag", "authenticated packet requires 16-byte tag")


def encode(p: Packet) -> bytes:
    """Serialise a packet into a frame, appending the CRC."""
    _validate_fields(p)
    body = p.signed_region()
    if p.flags & Flags.AUTHENTICATED:
        body += p.auth_tag
    return body + struct.pack(">H", crc16_ccitt(body))


def decode(frame: bytes) -> Packet:
    """Parse and integrity-check a frame. Raises PacketError on any defect."""
    if len(frame) < HEADER_SIZE + CRC_SIZE:
        raise PacketError("too_short", str(len(frame)))
    sync, version, sat_id, mtype, seq, ts, flags, plen = struct.unpack_from(HEADER_FORMAT, frame)
    if sync != SYNC_WORD:
        raise PacketError("bad_sync", hex(sync))
    if version != PROTOCOL_VERSION:
        raise PacketError("unsupported_version", str(version))
    if plen > MAX_PAYLOAD:
        raise PacketError("payload_too_large", str(plen))
    auth_len = AUTH_TAG_SIZE if flags & Flags.AUTHENTICATED else 0
    expected = HEADER_SIZE + plen + auth_len + CRC_SIZE
    if len(frame) != expected:
        raise PacketError("length_mismatch", f"expected {expected} got {len(frame)}")
    (crc_rx,) = struct.unpack_from(">H", frame, expected - CRC_SIZE)
    if crc16_ccitt(frame[: expected - CRC_SIZE]) != crc_rx:
        raise PacketError("crc_mismatch")
    try:
        msg_type = MessageType(mtype)
    except ValueError as exc:
        raise PacketError("unknown_type", hex(mtype)) from exc
    payload = frame[HEADER_SIZE : HEADER_SIZE + plen]
    tag = frame[HEADER_SIZE + plen : HEADER_SIZE + plen + auth_len]
    return Packet(
        sat_id=sat_id,
        msg_type=msg_type,
        seq=seq,
        timestamp_ms=ts,
        payload=payload,
        flags=Flags(flags),
        auth_tag=tag,
        version=version,
        raw_size=len(frame),
    )
