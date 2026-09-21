"""Flattening over a matte for the formats without alpha: SPEC.md section 10."""

from __future__ import annotations

from functools import lru_cache
from typing import Tuple


@lru_cache(maxsize=1024)
def _table(alpha: int, matte: int) -> bytes:
    """``flat = floor((pa * value + (255 - pa) * M + 127) / 255)`` for every channel value."""
    return bytes((alpha * value + (255 - alpha) * matte + 127) // 255 for value in range(256))


def flatten(rgba: bytes, matte: int) -> Tuple[bytes, bytes, bytes]:
    """The R, G and B planes of the pixels laid over the matte colour ``0xRRGGBB``."""
    alpha = rgba[3::4]
    planes = [rgba[0::4], rgba[1::4], rgba[2::4]]
    levels = set(alpha)
    if levels == {255}:
        return planes[0], planes[1], planes[2]
    # Pixels are taken one alpha level at a time: a translation table flattens a whole plane
    # as if every pixel had that alpha, and a mask keeps the pixels that do.
    n = len(alpha)
    flat = [0, 0, 0]
    for level in levels:
        mask = int.from_bytes(alpha.translate(bytes(level) + b"\xff" + bytes(255 - level)), "big")
        for channel in range(3):
            table = _table(level, (matte >> (16 - 8 * channel)) & 0xFF)
            flat[channel] |= int.from_bytes(planes[channel].translate(table), "big") & mask
    return flat[0].to_bytes(n, "big"), flat[1].to_bytes(n, "big"), flat[2].to_bytes(n, "big")
