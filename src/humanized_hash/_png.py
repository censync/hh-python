"""PNG: SPEC.md section 11. The deflate stream (RFC 1951) is written here, bit for bit."""

from __future__ import annotations

from binascii import crc32
from itertools import accumulate
from typing import List, Union

_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Length and distance codes of RFC 1951 section 3.2.5: base values and extra bits.
_LENGTH_BASE = (
    3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31,
    35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258,
)
_LENGTH_EXTRA = (
    0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2,
    3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0,
)
_DISTANCE_BASE = (
    1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769,
    1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577,
)
_DISTANCE_EXTRA = (
    0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8,
    9, 9, 10, 10, 11, 11, 12, 12, 13, 13,
)

_MAX_MATCH = 258
# Positions handled with one pair of mismatch maps, and tokens gathered before they are packed.
_WINDOW = 1 << 20
_FLUSH = 1 << 15
_PIECE = 4096

_NONZERO = bytes(1 if v else 0 for v in range(256))


def adler32(data: bytes) -> int:
    """Adler-32 (RFC 1950).

    ``b`` is the sum of the values ``a`` takes, so over a chunk of ``n`` bytes it grows by
    ``n * a`` plus the sum of the prefix sums of the chunk.
    """
    a = 1
    b = 0
    for start in range(0, len(data), 65536):
        chunk = data[start : start + 65536]
        b = (b + len(chunk) * a + sum(accumulate(chunk))) % 65521
        a = (a + sum(chunk)) % 65521
    return (b << 16) | a


def _bits(value: int, count: int) -> str:
    """Extra bits in stream order: least significant bit first."""
    return format(value, "b").zfill(count)[::-1] if count else ""


def _fixed_code(symbol: int) -> str:
    """The fixed literal/length code of RFC 1951 section 3.2.6, most significant bit first."""
    if symbol < 144:
        return format(0x30 + symbol, "08b")
    if symbol < 256:
        return format(0x190 + symbol - 144, "09b")
    if symbol < 280:
        return format(symbol - 256, "07b")
    return format(0xC0 + symbol - 280, "08b")


def _length_bits(length: int) -> str:
    index = max(i for i in range(29) if _LENGTH_BASE[i] <= length)
    return _fixed_code(257 + index) + _bits(length - _LENGTH_BASE[index], _LENGTH_EXTRA[index])


def _distance_bits(distance: int) -> str:
    index = max(i for i in range(30) if _DISTANCE_BASE[i] <= distance)
    return format(index, "05b") + _bits(distance - _DISTANCE_BASE[index], _DISTANCE_EXTRA[index])


# The stream is gathered as text of "0" and "1" in stream order and packed with int(text, 2).
_LITERAL = tuple(_fixed_code(symbol) for symbol in range(256))
_END_OF_BLOCK = _fixed_code(256)
_LENGTH = ("", "", "") + tuple(_length_bits(length) for length in range(3, _MAX_MATCH + 1))


def _pack(text: str) -> bytes:
    """Packs a whole number of bytes; deflate fills each byte from its least significant bit.

    The text is converted piece by piece, which keeps the cost linear on every interpreter.
    """
    pieces = []
    for at in range(0, len(text), _PIECE):
        piece = text[at : at + _PIECE]
        pieces.append(int(piece[::-1], 2).to_bytes(len(piece) // 8, "little"))
    return b"".join(pieces)


def _mismatches(raw: bytes, distance: int, start: int, stop: int) -> bytes:
    """One byte per position ``start <= p < stop``: 0 where ``raw[p] == raw[p - distance]``.

    Positions before ``distance`` have nothing to match and count as mismatches.
    """
    lead = max(0, min(distance, stop) - start)
    start += lead
    if start >= stop:
        return b"\x01" * lead
    here = int.from_bytes(raw[start:stop], "big")
    there = int.from_bytes(raw[start - distance : stop - distance], "big")
    return b"\x01" * lead + (here ^ there).to_bytes(stop - start, "big").translate(_NONZERO)


def deflate_fixed(raw: bytes, bpp: int, stride: int) -> bytes:
    """One final block with fixed Huffman codes; greedy matches at the distances bpp, stride."""
    n = len(raw)
    near_bits = _distance_bits(bpp)
    far_bits = _distance_bits(stride)
    literal = _LITERAL
    length_bits = _LENGTH
    out: List[bytes] = []
    parts: List[str] = ["110"]  # BFINAL = 1, BTYPE = 01
    i = 0
    while i < n:
        start = i
        stop = min(n, start + _WINDOW)
        # A match that starts inside the window may run past its end.
        reach = min(n, stop + _MAX_MATCH)
        near = _mismatches(raw, bpp, start, reach)
        far = _mismatches(raw, stride, start, reach)
        while i < stop:
            at = i - start
            limit = at + min(_MAX_MATCH, n - i)
            found = near.find(1, at, limit)
            best = (limit if found < 0 else found) - at
            distance_bits = near_bits
            found = far.find(1, at, limit)
            other = (limit if found < 0 else found) - at
            if other > best:
                best = other
                distance_bits = far_bits
            if best >= 3:
                parts.append(length_bits[best] + distance_bits)
                i += best
            else:
                parts.append(literal[raw[i]])
                i += 1
            if len(parts) >= _FLUSH:
                text = "".join(parts)
                whole = len(text) - len(text) % 8
                out.append(_pack(text[:whole]))
                parts = [text[whole:]]
    parts.append(_END_OF_BLOCK)
    text = "".join(parts)
    out.append(_pack(text + "0" * (-len(text) % 8)))
    return b"".join(out)


def _chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return len(data).to_bytes(4, "big") + body + crc32(body).to_bytes(4, "big")


def encode(width: int, height: int, rgba: bytes) -> bytes:
    """An 8-bit truecolour PNG; with alpha only if some pixel is not opaque."""
    opaque = rgba[3::4].count(255) == width * height
    bpp = 3 if opaque else 4
    pixels: Union[bytes, bytearray] = rgba
    if opaque:
        pixels = bytearray(3 * width * height)
        for channel in range(3):
            pixels[channel::3] = rgba[channel::4]
    row = width * bpp
    # Every row starts with the filter byte 00.
    raw = b"".join([b"\x00" + pixels[at : at + row] for at in range(0, row * height, row)])
    zlib_stream = b"\x78\x01" + deflate_fixed(raw, bpp, 1 + row) + adler32(raw).to_bytes(4, "big")
    colour_type = 2 if opaque else 6
    header = width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes((8, colour_type, 0, 0, 0))
    return b"".join(
        (
            _SIGNATURE,
            _chunk(b"IHDR", header),
            _chunk(b"sRGB", b"\x00"),
            _chunk(b"IDAT", zlib_stream),
            _chunk(b"IEND", b""),
        )
    )
