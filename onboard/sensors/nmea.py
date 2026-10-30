"""Minimal NMEA-0183 GGA parser for a serial GNSS receiver on the bench.

Note: most COTS GNSS modules enforce CoCom limits (altitude/velocity) and will
not produce fixes in orbit. Receiver choice for flight is TBD (risk R-09).
"""

from __future__ import annotations

from .interfaces import GnssFix, SensorError


def _checksum_ok(sentence: str) -> bool:
    if "*" not in sentence:
        return False
    body, cs = sentence[1:].split("*", 1)
    calc = 0
    for ch in body:
        calc ^= ord(ch)
    try:
        return calc == int(cs[:2], 16)
    except ValueError:
        return False


def _coord(value: str, hemi: str, deg_digits: int) -> float:
    deg = float(value[:deg_digits])
    minutes = float(value[deg_digits:])
    v = deg + minutes / 60.0
    return -v if hemi in ("S", "W") else v


def parse_gga(sentence: str) -> GnssFix:
    sentence = sentence.strip()
    if not sentence.startswith("$") or not _checksum_ok(sentence):
        raise SensorError("bad NMEA checksum")
    fields = sentence.split("*")[0].split(",")
    if not fields[0].endswith("GGA"):
        raise SensorError(f"not a GGA sentence: {fields[0]}")
    quality = int(fields[6] or 0)
    sats = int(fields[7] or 0)
    if quality == 0 or not fields[2]:
        return GnssFix(fix=False, sats=sats)
    return GnssFix(
        fix=True,
        sats=sats,
        lat_deg=_coord(fields[2], fields[3], 2),
        lon_deg=_coord(fields[4], fields[5], 3),
        alt_km=float(fields[9]) / 1000.0 if fields[9] else None,
    )
