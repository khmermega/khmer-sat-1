"""REQ: FR-TTC-001..006 - packet format, integrity, authentication, anti-replay."""

import random

import pytest

from shared.protocol import (
    MAX_PAYLOAD,
    AuthError,
    Flags,
    MessageType,
    Packet,
    PacketError,
    ReplayGuard,
    crc16_ccitt,
    decode,
    decode_chunk,
    encode,
    encode_chunk,
    encode_json,
    parse_key,
    sign,
    verify,
)

KEY = bytes(range(32))


def make(payload=b'{"a":1}', mtype=MessageType.HOUSEKEEPING, seq=7, ts=1_700_000_000_000):
    return Packet(0x4B31, mtype, seq, ts, payload)


def test_crc_check_value():
    assert crc16_ccitt(b"123456789") == 0x29B1


def test_roundtrip_preserves_all_fields():
    p = make()
    q = decode(encode(p))
    assert (q.sat_id, q.msg_type, q.seq, q.timestamp_ms, q.payload) == (p.sat_id, p.msg_type, p.seq, p.timestamp_ms, p.payload)
    assert q.version == 1


def test_every_single_bit_flip_is_detected():
    frame = encode(make())
    for bit in range(len(frame) * 8):
        buf = bytearray(frame)
        buf[bit // 8] ^= 1 << (bit % 8)
        with pytest.raises(PacketError):
            decode(bytes(buf))


@pytest.mark.parametrize(
    "mutate,reason",
    [
        (lambda f: f[:5], "too_short"),
        (lambda f: b"\x00\x00" + f[2:], "bad_sync"),
        (lambda f: f + b"\x00", "length_mismatch"),
    ],
)
def test_malformed_frames(mutate, reason):
    with pytest.raises(PacketError) as e:
        decode(mutate(encode(make())))
    assert e.value.reason == reason


def test_payload_size_limit():
    with pytest.raises(PacketError):
        encode(make(payload=b"x" * (MAX_PAYLOAD + 1)))


def test_random_garbage_never_crashes():
    rng = random.Random(1)
    for _ in range(2000):
        blob = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 64)))
        with pytest.raises(PacketError):
            decode(blob)


def test_sign_and_verify():
    p = sign(KEY, make(mtype=MessageType.COMMAND))
    q = decode(encode(p))
    assert q.flags & Flags.AUTHENTICATED
    verify(KEY, q)


def test_tampered_payload_fails_auth_even_with_valid_crc():
    p = sign(KEY, make(mtype=MessageType.COMMAND))
    p.payload = b'{"a":2}'  # attacker re-computes CRC via encode(), but not the HMAC
    with pytest.raises(AuthError, match="bad_signature"):
        verify(KEY, decode(encode(p)))


def test_wrong_key_and_unsigned_rejected():
    p = sign(KEY, make(mtype=MessageType.COMMAND))
    with pytest.raises(AuthError):
        verify(bytes(32), p)
    with pytest.raises(AuthError, match="unauthenticated"):
        verify(KEY, make(mtype=MessageType.COMMAND))


def test_parse_key_requires_256_bits():
    assert parse_key("00" * 32) == bytes(32)
    with pytest.raises(ValueError):
        parse_key("00" * 16)
    with pytest.raises(ValueError):
        parse_key("zz" * 32)


def test_replay_guard():
    g = ReplayGuard(window_ms=30_000)
    now = 1_700_000_000_000
    p = make(ts=now, seq=1)
    g.check_and_record(p, now)
    with pytest.raises(AuthError, match="replay"):
        g.check_and_record(p, now + 1000)
    with pytest.raises(AuthError, match="stale"):
        g.check_and_record(make(ts=now - 31_000, seq=2), now)
    with pytest.raises(AuthError, match="stale"):
        g.check_and_record(make(ts=now + 31_000, seq=3), now)
    # Same seq after a ground restart, new timestamp -> accepted.
    g.check_and_record(make(ts=now + 5, seq=1), now)


def test_chunk_codec():
    iid = "0b5d6c3e-6f5e-4d55-9a3c-2a7f1c2d9e01"
    body = encode_chunk(iid, 3, 10, b"hello")
    assert decode_chunk(body) == (iid, 3, 10, b"hello")
    with pytest.raises(PacketError):
        decode_chunk(encode_chunk(iid, 10, 10, b""))


def test_json_payload_is_canonical():
    assert encode_json({"b": 1, "a": 2}) == b'{"a":2,"b":1}'
