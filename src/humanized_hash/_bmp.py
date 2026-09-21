"""BMP: SPEC.md section 12."""

from __future__ import annotations

from ._flatten import flatten


def encode(width: int, height: int, rgba: bytes, matte: int) -> bytes:
    """A bottom-up 24-bit ``BI_RGB`` file of the pixels flattened over the matte."""
    row = 4 * ((3 * width + 3) // 4)
    size = row * height
    header = b"".join(
        (
            b"BM",
            (54 + size).to_bytes(4, "little"),
            bytes(4),
            (54).to_bytes(4, "little"),
            (40).to_bytes(4, "little"),
            width.to_bytes(4, "little"),
            height.to_bytes(4, "little"),
            (1).to_bytes(2, "little"),
            (24).to_bytes(2, "little"),
            bytes(4),
            size.to_bytes(4, "little"),
            (2835).to_bytes(4, "little"),
            (2835).to_bytes(4, "little"),
            bytes(8),
        )
    )
    red, green, blue = flatten(rgba, matte)
    out = bytearray(size)
    for y in range(height):
        source = slice(y * width, (y + 1) * width)
        at = (height - 1 - y) * row
        out[at : at + 3 * width : 3] = blue[source]
        out[at + 1 : at + 3 * width : 3] = green[source]
        out[at + 2 : at + 3 * width : 3] = red[source]
    return header + bytes(out)
