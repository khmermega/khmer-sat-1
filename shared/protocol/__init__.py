"""KHMER-SAT 1 telemetry & telecommand protocol (version 1)."""

from .auth import AuthError, ReplayGuard, compute_tag, parse_key, sign, verify
from .codec import decode_chunk, decode_json, encode_chunk, encode_json
from .crc import crc16_ccitt
from .packet import (
    MAX_PAYLOAD,
    PROTOCOL_VERSION,
    Flags,
    MessageType,
    Packet,
    PacketError,
    decode,
    encode,
)

__all__ = [
    "AuthError",
    "Flags",
    "MAX_PAYLOAD",
    "MessageType",
    "PROTOCOL_VERSION",
    "Packet",
    "PacketError",
    "ReplayGuard",
    "compute_tag",
    "crc16_ccitt",
    "decode",
    "decode_chunk",
    "decode_json",
    "encode",
    "encode_chunk",
    "encode_json",
    "parse_key",
    "sign",
    "verify",
]
