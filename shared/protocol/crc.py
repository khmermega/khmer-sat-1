"""CRC-16/CCITT-FALSE used as the frame integrity field.

Parameters: poly=0x1021, init=0xFFFF, refin=False, refout=False, xorout=0x0000.
Check value for b"123456789" is 0x29B1 (verified in tests/unit/test_protocol.py).

The CRC detects accidental corruption only. Authenticity of commands is provided
separately by the HMAC tag (see shared/protocol/auth.py).
"""

from __future__ import annotations

_POLY = 0x1021


def _build_table() -> list[int]:
    table: list[int] = []
    for byte in range(256):
        crc = byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ _POLY) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
        table.append(crc)
    return table


_TABLE = _build_table()


def crc16_ccitt(data: bytes, init: int = 0xFFFF) -> int:
    """Compute CRC-16/CCITT-FALSE over ``data``."""
    crc = init
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ _TABLE[((crc >> 8) ^ b) & 0xFF]
    return crc
