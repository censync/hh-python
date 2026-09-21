"""Small independent decoders for the three file formats, for the tests only.

The standard library inflates the PNG stream (``zlib``); BMP and baseline JPEG are read here,
straight from their specifications. Floating point is fine in a test.
"""

from __future__ import annotations

import binascii
import math
import struct
import unittest
from typing import Dict, List, Tuple

try:
    import zlib
except ImportError:  # zlib is optional in CPython builds
    zlib = None

Rgb = Tuple[int, int, int]


def decode_png(data: bytes) -> Tuple[int, int, int, bytes]:
    """Width, height, bytes per pixel and the pixels of a PNG as the library writes it."""
    if zlib is None:
        raise unittest.SkipTest("this interpreter has no zlib")
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    chunks = []
    at = 8
    while at < len(data):
        (length,) = struct.unpack(">I", data[at : at + 4])
        kind = data[at + 4 : at + 8]
        body = data[at + 8 : at + 8 + length]
        (crc,) = struct.unpack(">I", data[at + 8 + length : at + 12 + length])
        assert crc == binascii.crc32(kind + body), kind
        chunks.append((kind, body))
        at += 12 + length
    assert [kind for kind, _ in chunks] == [b"IHDR", b"sRGB", b"IDAT", b"IEND"]
    width, height, depth, colour_type, compression, png_filter, interlace = struct.unpack(
        ">IIBBBBB", chunks[0][1]
    )
    assert (depth, compression, png_filter, interlace) == (8, 0, 0, 0)
    assert colour_type in (2, 6)
    assert chunks[1][1] == b"\x00" and chunks[3][1] == b""
    stream = chunks[2][1]
    # zlib header 78 01, then one final block with fixed Huffman codes: BFINAL 1, BTYPE 01.
    assert stream[:2] == b"\x78\x01" and stream[2] & 7 == 3
    raw = zlib.decompress(stream)
    bpp = 3 if colour_type == 2 else 4
    stride = 1 + width * bpp
    assert len(raw) == stride * height
    rows = []
    for y in range(height):
        assert raw[y * stride] == 0, "every row uses filter 0"
        rows.append(raw[y * stride + 1 : (y + 1) * stride])
    return width, height, bpp, b"".join(rows)


def decode_bmp(data: bytes) -> Tuple[int, int, List[Rgb]]:
    """Width, height and the pixels, top row first, of a 24-bit BI_RGB file."""
    magic, file_size, reserved, offset = struct.unpack("<2sIII", data[:14])
    assert (magic, file_size, reserved, offset) == (b"BM", len(data), 0, 54)
    header = struct.unpack("<IiiHHIIiiII", data[14:54])
    size, width, height, planes, bits, compression, image_size, xppm, yppm, used, important = header
    assert (size, planes, bits, compression, used, important) == (40, 1, 24, 0, 0, 0)
    assert (xppm, yppm) == (2835, 2835)
    row = (3 * width + 3) // 4 * 4
    assert image_size == row * height and len(data) == 54 + image_size
    pixels = []
    for y in range(height):
        at = 54 + (height - 1 - y) * row
        line = data[at : at + row]
        assert line[3 * width :] == bytes(row - 3 * width), "padding is zero"
        pixels.extend((line[3 * x + 2], line[3 * x + 1], line[3 * x]) for x in range(width))
    return width, height, pixels


class _BitReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.at = 0
        self.bit = 0

    def read(self, count: int) -> int:
        value = 0
        for _ in range(count):
            value = (value << 1) | ((self.data[self.at] >> (7 - self.bit)) & 1)
            self.bit += 1
            if self.bit == 8:
                self.bit = 0
                self.at += 1
        return value

    def symbol(self, table: Dict[Tuple[int, int], int]) -> int:
        code = 0
        for length in range(1, 17):
            code = (code << 1) | self.read(1)
            if (length, code) in table:
                return table[(length, code)]
        raise AssertionError("no such Huffman code")

    def value(self, category: int) -> int:
        """T.81 F.2.2.1: the additional bits as a signed value."""
        if category == 0:
            return 0
        bits = self.read(category)
        return bits if bits >> (category - 1) else bits - (1 << category) + 1


_ZIGZAG = (
    0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5,
    12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63,
)
_COS = [[math.cos((2 * x + 1) * u * math.pi / 16) for u in range(8)] for x in range(8)]
_SCALE = [math.sqrt(0.5)] + [1.0] * 7


def _inverse_dct(block: List[float]) -> List[float]:
    """T.81 A.3.3, separable."""
    half = [0.0] * 64
    for y in range(8):
        for x in range(8):
            half[8 * y + x] = sum(_SCALE[u] * block[8 * y + u] * _COS[x][u] for u in range(8)) / 2
    out = [0.0] * 64
    for x in range(8):
        for y in range(8):
            out[8 * y + x] = sum(_SCALE[v] * half[8 * v + x] * _COS[y][v] for v in range(8)) / 2
    return out


def decode_jpeg(data: bytes) -> Tuple[int, int, List[Rgb]]:
    """Width, height and the pixels of a baseline, non-subsampled, three-component JFIF file."""
    assert data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9"
    quantisers: Dict[int, List[int]] = {}
    huffman: Dict[Tuple[int, int], Dict[Tuple[int, int], int]] = {}
    components: List[Tuple[int, int]] = []  # identifier, quantiser
    selectors: List[Tuple[int, int]] = []  # DC table, AC table
    width = height = 0
    at = 2
    while True:
        assert data[at] == 0xFF
        marker = data[at + 1]
        (length,) = struct.unpack(">H", data[at + 2 : at + 4])
        body = data[at + 4 : at + 2 + length]
        at += 2 + length
        if marker == 0xE0:
            assert body == b"JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x00\x00"
        elif marker == 0xDB:
            assert len(body) == 65 and body[0] in (0, 1), "one 8-bit table per segment"
            quantisers[body[0]] = list(body[1:])
        elif marker == 0xC0:
            precision, height, width, count = struct.unpack(">BHHB", body[:6])
            assert (precision, count) == (8, 3)
            for i in range(3):
                identifier, sampling, table = body[6 + 3 * i : 9 + 3 * i]
                assert sampling == 0x11, "no subsampling"
                components.append((identifier, table))
        elif marker == 0xC4:
            counts = body[1:17]
            assert len(body) == 17 + sum(counts)
            table: Dict[Tuple[int, int], int] = {}
            code = 0
            k = 17
            for bits in range(1, 17):
                for _ in range(counts[bits - 1]):
                    table[(bits, code)] = body[k]
                    code += 1
                    k += 1
                code <<= 1
            huffman[(body[0] >> 4, body[0] & 15)] = table
        elif marker == 0xDA:
            assert body[0] == 3 and body[7:] == b"\x00\x3f\x00"
            for i in range(3):
                assert body[1 + 2 * i] == components[i][0]
                selectors.append((body[2 + 2 * i] >> 4, body[2 + 2 * i] & 15))
            break
        else:
            raise AssertionError(f"unexpected marker {marker:02x}")
    scan = data[at:-2]
    # Inside the scan FF is always followed by 00: no restart markers, no other markers.
    assert scan.count(b"\xff") == scan.count(b"\xff\x00")
    reader = _BitReader(scan.replace(b"\xff\x00", b"\xff") + b"\xff")
    across = (width + 7) // 8
    down = (height + 7) // 8
    planes = [[0.0] * (across * 8 * down * 8) for _ in range(3)]
    previous = [0, 0, 0]
    for by in range(down):
        for bx in range(across):
            for c in range(3):
                dc_table = huffman[(0, selectors[c][0])]
                ac_table = huffman[(1, selectors[c][1])]
                quantiser = quantisers[components[c][1]]
                coefficients = [0.0] * 64
                previous[c] += reader.value(reader.symbol(dc_table))
                coefficients[0] = previous[c] * quantiser[0]
                k = 1
                while k < 64:
                    symbol = reader.symbol(ac_table)
                    if symbol == 0x00:
                        break
                    if symbol == 0xF0:
                        k += 16
                        continue
                    k += symbol >> 4
                    coefficients[_ZIGZAG[k]] = reader.value(symbol & 15) * quantiser[k]
                    k += 1
                assert k <= 64
                samples = _inverse_dct(coefficients)
                for j in range(8):
                    start = (8 * by + j) * across * 8 + 8 * bx
                    planes[c][start : start + 8] = samples[8 * j : 8 * j + 8]
    # What is left is the fill of 1 bits in the last byte.
    assert reader.at >= len(scan.replace(b"\xff\x00", b"\xff")) - 1
    pixels = []
    for y in range(height):
        for x in range(width):
            i = y * across * 8 + x
            luma = planes[0][i] + 128
            cb = planes[1][i]
            cr = planes[2][i]
            rgb = (luma + 1.402 * cr, luma - 0.344136 * cb - 0.714136 * cr, luma + 1.772 * cb)
            pixels.append(tuple(min(255, max(0, round(v))) for v in rgb))
    return width, height, pixels
