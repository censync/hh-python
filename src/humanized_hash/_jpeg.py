"""JPEG: SPEC.md section 13 and appendix B. Baseline sequential JFIF, 4:4:4, ITU-T T.81."""

from __future__ import annotations

import struct
from typing import Callable, Dict, List, Sequence, Tuple

from ._flatten import flatten

# zigzag[i] is the natural index of the i-th coefficient.
ZIGZAG = (
    0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5,
    12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63,
)

# The base quantiser tables of T.81 annex K in natural (row-major) order.
LUMINANCE_QUANTISER = (
    16, 11, 10, 16, 24, 40, 51, 61,
    12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56,
    14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77,
    24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101,
    72, 92, 95, 98, 112, 100, 103, 99,
)
CHROMINANCE_QUANTISER = (
    17, 18, 24, 47, 99, 99, 99, 99,
    18, 21, 26, 66, 99, 99, 99, 99,
    24, 26, 56, 99, 99, 99, 99, 99,
    47, 66, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
)

# Huffman tables of T.81 annex K: the number of codes of each length 1..16, then the symbols.
DC_LUMINANCE = (
    (0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0),
    tuple(range(12)),
)
DC_CHROMINANCE = (
    (0, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0),
    tuple(range(12)),
)
AC_LUMINANCE = (
    (0, 2, 1, 3, 3, 2, 4, 3, 5, 5, 4, 4, 0, 0, 1, 0x7D),
    (
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
        0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
        0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
        0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
        0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
        0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
        0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
        0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
        0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
        0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
        0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA,
    ),
)
AC_CHROMINANCE = (
    (0, 2, 1, 2, 4, 4, 3, 4, 7, 5, 4, 4, 0, 1, 2, 0x77),
    (
        0x00, 0x01, 0x02, 0x03, 0x11, 0x04, 0x05, 0x21, 0x31, 0x06, 0x12, 0x41,
        0x51, 0x07, 0x61, 0x71, 0x13, 0x22, 0x32, 0x81, 0x08, 0x14, 0x42, 0x91,
        0xA1, 0xB1, 0xC1, 0x09, 0x23, 0x33, 0x52, 0xF0, 0x15, 0x62, 0x72, 0xD1,
        0x0A, 0x16, 0x24, 0x34, 0xE1, 0x25, 0xF1, 0x17, 0x18, 0x19, 0x1A, 0x26,
        0x27, 0x28, 0x29, 0x2A, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44,
        0x45, 0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58,
        0x59, 0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74,
        0x75, 0x76, 0x77, 0x78, 0x79, 0x7A, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87,
        0x88, 0x89, 0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A,
        0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4,
        0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7,
        0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA,
        0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF2, 0xF3, 0xF4,
        0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA,
    ),
)

_F0298 = 2446
_F0390 = 3196
_F0541 = 4433
_F0765 = 6270
_F0899 = 7373
_F1175 = 9633
_F1501 = 12299
_F1847 = 15137
_F1961 = 16069
_F2053 = 16819
_F2562 = 20995
_F3072 = 25172

# Coded blocks remembered within one image; flat and repeated blocks are most of a picture.
_MAX_REMEMBERED = 8192
# Bits converted to bytes at a time.
_PIECE = 4096

_HuffmanSpec = Tuple[Tuple[int, ...], Tuple[int, ...]]


def _codes(spec: _HuffmanSpec) -> Dict[int, str]:
    """Canonical code assignment of T.81 annex C: symbol to its code as text of 0 and 1."""
    counts, symbols = spec
    out = {}
    code = 0
    k = 0
    for length in range(1, 17):
        for _ in range(counts[length - 1]):
            out[symbols[k]] = format(code, "b").zfill(length)
            code += 1
            k += 1
        code <<= 1
    return out


class _Lazy(Dict[int, str]):
    """A table that is filled on demand."""

    def __init__(self, make: Callable[[int], str]) -> None:
        super().__init__()
        self._make = make

    def __missing__(self, key: int) -> str:
        value = self[key] = self._make(key)
        return value


def _additional_bits(value: int) -> str:
    """The low ``category`` bits of ``v``, or of ``v - 1`` for a negative ``v`` (T.81 F.1.2)."""
    category = abs(value).bit_length()
    if category == 0:
        return ""
    if value < 0:
        value += (1 << category) - 1
    return format(value, "b").zfill(category)


_VALUE_BITS = _Lazy(_additional_bits)
_DC_CODES = (_codes(DC_LUMINANCE), _codes(DC_CHROMINANCE))
_AC_CODES = (_codes(AC_LUMINANCE), _codes(AC_CHROMINANCE))


def _dc_bits(codes: Dict[int, str]) -> _Lazy:
    """A DC difference as its category code and additional bits."""

    def make(diff: int) -> str:
        return codes[abs(diff).bit_length()] + _VALUE_BITS[diff]

    return _Lazy(make)


_DC_BITS = tuple(_dc_bits(codes) for codes in _DC_CODES)


def _dct_pass(d: Sequence[int], first: bool) -> Tuple[int, ...]:
    """One pass of section 13.5 over eight values; ``>>`` on a negative value is a floor."""
    d0, d1, d2, d3, d4, d5, d6, d7 = d
    t0 = d0 + d7
    t7 = d0 - d7
    t1 = d1 + d6
    t6 = d1 - d6
    t2 = d2 + d5
    t5 = d2 - d5
    t3 = d3 + d4
    t4 = d3 - d4
    t10 = t0 + t3
    t13 = t0 - t3
    t11 = t1 + t2
    t12 = t1 - t2
    if first:
        n = 11
        out0 = (t10 + t11) * 4
        out4 = (t10 - t11) * 4
    else:
        n = 15
        out0 = (t10 + t11 + 2) >> 2
        out4 = (t10 - t11 + 2) >> 2
    half = 1 << (n - 1)
    z1 = (t12 + t13) * _F0541
    out2 = (z1 + t13 * _F0765 + half) >> n
    out6 = (z1 - t12 * _F1847 + half) >> n

    z5 = (t4 + t6 + t5 + t7) * _F1175
    z1 = -(t4 + t7) * _F0899
    z2 = -(t5 + t6) * _F2562
    z3 = -(t4 + t6) * _F1961 + z5
    z4 = -(t5 + t7) * _F0390 + z5
    return (
        out0,
        (t7 * _F1501 + z1 + z4 + half) >> n,
        out2,
        (t6 * _F3072 + z2 + z3 + half) >> n,
        out4,
        (t5 * _F2053 + z2 + z4 + half) >> n,
        out6,
        (t4 * _F0298 + z1 + z3 + half) >> n,
    )


def _forward_dct(d: List[int]) -> None:
    """Section 13.5: the transform in place, on each row, then on each column."""
    for row in range(0, 64, 8):
        d[row : row + 8] = _dct_pass(d[row : row + 8], True)
    for column in range(8):
        d[column::8] = _dct_pass(d[column::8], False)


def _code_block(
    samples: Sequence[int], divisors: Sequence[int], ac_codes: Dict[int, str]
) -> Tuple[int, str]:
    """Sections 13.5 to 13.7 for one block: the DC value and the coded AC coefficients."""
    d = [sample - 128 for sample in samples]
    _forward_dct(d)
    # Section 13.6; divisors are 8 * Qt in zigzag order.
    dv = divisors[0]
    c = d[0]
    dc = (c + dv // 2) // dv if c >= 0 else -((-c + dv // 2) // dv)
    parts = []
    run = 0
    for i in range(1, 64):
        dv = divisors[i]
        c = d[ZIGZAG[i]]
        value = (c + dv // 2) // dv if c >= 0 else -((-c + dv // 2) // dv)
        if value == 0:
            run += 1
            continue
        # The baseline AC tables stop at 10 bits.
        value = min(max(value, -1023), 1023)
        while run >= 16:
            parts.append(ac_codes[0xF0])
            run -= 16
        parts.append(ac_codes[run * 16 + abs(value).bit_length()])
        parts.append(_VALUE_BITS[value])
        run = 0
    if run:
        parts.append(ac_codes[0x00])
    return dc, "".join(parts)


def _scaled(base: Sequence[int], quality: int) -> List[int]:
    """Section 13.2, natural order."""
    scale = 200 - 2 * quality
    return [min(max((value * scale + 50) // 100, 1), 255) for value in base]


def _huffman_segment(identifier: int, spec: _HuffmanSpec) -> bytes:
    counts, symbols = spec
    body = bytes((identifier,)) + bytes(counts) + bytes(symbols)
    return b"\xff\xc4" + (2 + len(body)).to_bytes(2, "big") + body


def _widen(plane: bytes) -> int:
    """One 32-bit lane per sample, so that a whole plane is scaled and summed at once."""
    wide = bytearray(4 * len(plane))
    wide[3::4] = plane
    return int.from_bytes(wide, "big")


def _convert(red: bytes, green: bytes, blue: bytes) -> Tuple[bytes, bytes, bytes]:
    """Section 13.3. Every numerator is 0..2^24 - 1, so byte 2 of a lane is the result."""
    n = len(red)
    r = _widen(red)
    g = _widen(green)
    b = _widen(blue)
    ones = _widen(b"\x01" * n)
    y = 19595 * r + 38470 * g + 7471 * b + 32768 * ones
    cb = 32768 * b + 8421375 * ones - 11059 * r - 21709 * g
    cr = 32768 * r + 8421375 * ones - 27439 * g - 5329 * b
    return (
        y.to_bytes(4 * n, "big")[1::4],
        cb.to_bytes(4 * n, "big")[1::4],
        cr.to_bytes(4 * n, "big")[1::4],
    )


def encode(width: int, height: int, rgba: bytes, quality: int, matte: int) -> bytes:
    """A baseline JFIF file of the pixels flattened over the matte."""
    quantisers = (_scaled(LUMINANCE_QUANTISER, quality), _scaled(CHROMINANCE_QUANTISER, quality))
    out = [b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x00\x00"]
    for identifier, table in enumerate(quantisers):
        out.append(b"\xff\xdb\x00\x43" + bytes((identifier,)) + bytes(table[k] for k in ZIGZAG))
    out.append(
        b"\xff\xc0\x00\x11\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    )
    out.append(_huffman_segment(0x00, DC_LUMINANCE))
    out.append(_huffman_segment(0x10, AC_LUMINANCE))
    out.append(_huffman_segment(0x01, DC_CHROMINANCE))
    out.append(_huffman_segment(0x11, AC_CHROMINANCE))
    out.append(b"\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00")

    planes = flatten(rgba, matte)
    divisors = [[8 * table[k] for k in ZIGZAG] for table in quantisers]
    # Component to its tables: Y uses the luminance set, Cb and Cr the chrominance set.
    tables = (0, 1, 1)
    remembered: List[Dict[Tuple[int, ...], Tuple[int, str]]] = [{}, {}, {}]
    previous_dc = [0, 0, 0]
    pad = -width % 8
    across = (width + pad) // 8
    pending = ""
    unpack = struct.Struct("64B").unpack
    pack = struct.Struct("8Q").pack
    for top in range(0, height, 8):
        # Section 13.4: eight rows, the last column and the last row repeated to full blocks.
        rows = [min(top + j, height - 1) * width for j in range(8)]
        band = _convert(
            *(
                b"".join(
                    plane[at : at + width] + plane[at + width - 1 : at + width] * pad
                    for at in rows
                )
                for plane in planes
            )
        )
        # Eight bytes of a row are one 64-bit item, so a block is a tuple of eight items.
        blocks = []
        for plane in band:
            items = memoryview(plane).cast("Q").tolist()
            blocks.append(zip(*(items[j * across : (j + 1) * across] for j in range(8))))
        parts = [pending]
        for mcu in zip(*blocks):
            for component in range(3):
                key = mcu[component]
                memory = remembered[component]
                coded = memory.get(key)
                if coded is None:
                    if len(memory) >= _MAX_REMEMBERED:
                        memory.clear()
                    which = tables[component]
                    coded = memory[key] = _code_block(
                        unpack(pack(*key)), divisors[which], _AC_CODES[which]
                    )
                dc, ac_bits = coded
                parts.append(_DC_BITS[tables[component]][dc - previous_dc[component]])
                parts.append(ac_bits)
                previous_dc[component] = dc
        text = "".join(parts)
        whole = len(text) - len(text) % 8
        pending = text[whole:]
        # Section 13.7: most significant bit first, FF followed by 00. The text is converted
        # piece by piece, which keeps the cost linear on every interpreter.
        for at in range(0, whole, _PIECE):
            piece = text[at : min(at + _PIECE, whole)]
            packed = int(piece, 2).to_bytes(len(piece) // 8, "big")
            out.append(packed.replace(b"\xff", b"\xff\x00"))
    if pending:
        last = int(pending + "1" * (8 - len(pending)), 2)
        out.append(b"\xff\x00" if last == 0xFF else bytes((last,)))
    out.append(b"\xff\xd9")
    return b"".join(out)
