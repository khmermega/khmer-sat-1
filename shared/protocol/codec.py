"""Payload codecs per message type.

JSON (UTF-8, compact) is used for structured messages to keep the prototype
inspectable. IMAGE_CHUNK uses a compact binary body. A future revision may
switch housekeeping to a fixed binary layout to save downlink bandwidth
(see docs/interfaces.md §2.4 data-rate budget).
"""

from __future__ import annotations

import json
import struct
import uuid
from typing import Any

from .packet import PacketError

_CHUNK_HDR = ">16sHH"  # image uuid, chunk index, total chunks
CHUNK_HEADER_SIZE = struct.calcsize(_CHUNK_HDR)


def encode_json(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")


def decode_json(payload: bytes) -> dict[str, Any]:
    try:
        obj = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PacketError("bad_payload", "invalid JSON") from exc
    if not isinstance(obj, dict):
        raise PacketError("bad_payload", "JSON payload must be an object")
    return obj


def encode_chunk(image_id: str, index: int, total: int, data: bytes) -> bytes:
    return struct.pack(_CHUNK_HDR, uuid.UUID(image_id).bytes, index, total) + data


def decode_chunk(payload: bytes) -> tuple[str, int, int, bytes]:
    if len(payload) < CHUNK_HEADER_SIZE:
        raise PacketError("bad_payload", "chunk too short")
    raw_id, index, total = struct.unpack_from(_CHUNK_HDR, payload)
    if total == 0 or index >= total:
        raise PacketError("bad_payload", f"chunk index {index}/{total}")
    return str(uuid.UUID(bytes=raw_id)), index, total, payload[CHUNK_HEADER_SIZE:]
