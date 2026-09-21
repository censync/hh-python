"""The encoders checked with independent decoders and with plain transcriptions of the
specification."""

from __future__ import annotations

import random
import unittest
from typing import List, Tuple

from humanized_hash import Fingerprint, FrameStyle, Image, Mode, RenderOptions, Shape
from humanized_hash import _jpeg, _png

from .decoders import decode_bmp, decode_jpeg, decode_png
from .support import pattern


def sample(size: int, mode: Mode, options: RenderOptions = RenderOptions()) -> Image:
    fp = bytes((i * 37 + 11) % 256 for i in range(32))
    return Fingerprint.from_bytes(fp, mode).render(size, options)


def flattened(image: Image, matte: int) -> List[Tuple[int, int, int]]:
    """Section 10, one pixel at a time."""
    m = (matte >> 16, (matte >> 8) & 0xFF, matte & 0xFF)
    rgba = image.rgba
    out = []
    for p in range(0, len(rgba), 4):
        a = rgba[p + 3]
        out.append(tuple((a * rgba[p + c] + (255 - a) * m[c] + 127) // 255 for c in range(3)))
    return out


def reference_deflate(raw: bytes, bpp: int, stride: int) -> List[Tuple[int, int]]:
    """The matching loop of section 11, literally: (0, literal) or (length, distance)."""
    n = len(raw)
    tokens = []
    i = 0
    while i < n:
        best = 0
        dist = 0
        for d in (bpp, stride):
            if i >= d:
                length = 0
                while length < min(258, n - i) and raw[i + length] == raw[i - d + length]:
                    length += 1
                if length > best:
                    best, dist = length, d
        if best >= 3:
            tokens.append((best, dist))
            i += best
        else:
            tokens.append((0, raw[i]))
            i += 1
    return tokens


def reference_bits(tokens: List[Tuple[int, int]]) -> bytes:
    """RFC 1951 section 3.2: the tokens as one final block with fixed Huffman codes."""
    bits: List[int] = [1, 1, 0]

    def huffman(code: int, length: int) -> None:
        bits.extend((code >> (length - 1 - k)) & 1 for k in range(length))

    def extra(value: int, length: int) -> None:
        bits.extend((value >> k) & 1 for k in range(length))

    def symbol(value: int) -> None:
        if value < 144:
            huffman(0b00110000 + value, 8)
        elif value < 256:
            huffman(0b110010000 + value - 144, 9)
        elif value < 280:
            huffman(value - 256, 7)
        else:
            huffman(0b11000000 + value - 280, 8)

    length_base = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83,
                   99, 115, 131, 163, 195, 227, 258]
    length_extra = [0] * 8 + [1] * 4 + [2] * 4 + [3] * 4 + [4] * 4 + [5] * 4 + [0]
    dist_base = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769,
                 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577]
    for length, value in tokens:
        if length == 0:
            symbol(value)
            continue
        index = max(i for i in range(29) if length_base[i] <= length)
        symbol(257 + index)
        extra(length - length_base[index], length_extra[index])
        index = max(i for i in range(30) if dist_base[i] <= value)
        huffman(index, 5)
        extra(value - dist_base[index], max(0, index // 2 - 1))
    symbol(256)
    bits.extend([0] * (-len(bits) % 8))
    return bytes(
        sum(bit << k for k, bit in enumerate(bits[at : at + 8])) for at in range(0, len(bits), 8)
    )


class PngTest(unittest.TestCase):
    def test_renders_decode_to_the_same_pixels(self) -> None:
        look = RenderOptions(Shape.ROUND, FrameStyle.GAPS, 0x121212, 200, 100)
        images = [sample(16, Mode.UNIVERSAL), sample(33, Mode.KEYED), sample(128, Mode.KEYED, look)]
        for image in images:
            width, height, bpp, pixels = decode_png(image.encode_png())
            self.assertEqual(image.size, (width, height))
            opaque = all(a == 255 for a in image.rgba[3::4])
            self.assertEqual(3 if opaque else 4, bpp)
            if opaque:
                self.assertEqual(bytes(v for i, v in enumerate(image.rgba) if i % 4 != 3), pixels)
            else:
                self.assertEqual(image.rgba, pixels)

    def test_arbitrary_pixels_decode(self) -> None:
        for number, (width, height) in enumerate([(1, 1), (3, 5), (64, 9), (300, 3), (2, 600)]):
            for kind in ("noise", "opaque"):
                image = Image(width, height, pattern(f"{kind}:{number + 1}", width, height))
                decoded = decode_png(image.encode_png())
                self.assertEqual((width, height, 4 if kind == "noise" else 3), decoded[:3])

    def test_one_transparent_pixel_makes_the_file_carry_alpha(self) -> None:
        rgba = bytearray(b"\x10\x20\x30\xff" * 12)
        self.assertEqual(3, decode_png(Image(4, 3, rgba).encode_png())[2])
        rgba[-1] = 254
        self.assertEqual(4, decode_png(Image(4, 3, rgba).encode_png())[2])

    def test_the_stream_is_the_greedy_matching_of_the_specification(self) -> None:
        generator = random.Random(21)
        streams = [b"", b"a", b"ab", b"aaa", b"\x00" * 1000, bytes(range(256)) * 3]
        for _ in range(40):
            # Few symbols and many runs, so that matches of every length and overlap appear.
            alphabet = generator.randbytes(generator.choice((1, 2, 3, 8)))
            streams.append(
                b"".join(
                    bytes((generator.choice(alphabet),)) * generator.choice((1, 1, 2, 3, 7, 300))
                    for _ in range(generator.randrange(1, 120))
                )
            )
        for raw in streams:
            for bpp, stride in ((3, 10), (4, 9), (3, 1 + 3 * 5), (4, 1 + 4 * 300)):
                expected = reference_bits(reference_deflate(raw, bpp, stride))
                self.assertEqual(expected, _png.deflate_fixed(raw, bpp, stride), (raw[:20], bpp))

    def test_windows_and_flushes_do_not_show_in_the_stream(self) -> None:
        generator = random.Random(22)
        raw = b"".join(
            bytes((generator.randrange(4),)) * generator.choice((1, 2, 5, 40, 700))
            for _ in range(400)
        )
        expected = reference_bits(reference_deflate(raw, 3, 61))
        window, flush = _png._WINDOW, _png._FLUSH
        try:
            for _png._WINDOW, _png._FLUSH in ((1, 1), (7, 3), (64, 2), (259, 50), (1000, 9)):
                self.assertEqual(expected, _png.deflate_fixed(raw, 3, 61))
        finally:
            _png._WINDOW, _png._FLUSH = window, flush


class BmpTest(unittest.TestCase):
    def test_renders_decode_to_the_flattened_pixels(self) -> None:
        look = RenderOptions(Shape.ROUND, FrameStyle.TICKS, 0x123456, 77, 99)
        for image in (sample(33, Mode.KEYED), sample(50, Mode.KEYED, look)):
            for matte in (0xFFFFFF, 0x0048FF, 0x000000):
                width, height, pixels = decode_bmp(image.encode_bmp(matte))
                self.assertEqual(image.size, (width, height))
                self.assertEqual(flattened(image, matte), pixels)

    def test_every_row_padding_decodes(self) -> None:
        for width in (1, 2, 3, 4, 5):
            image = Image(width, 3, pattern("noise:4", width, 3))
            width_out, height, pixels = decode_bmp(image.encode_bmp(0x808080))
            self.assertEqual((width, 3), (width_out, height))
            self.assertEqual(flattened(image, 0x808080), pixels)


class JpegTest(unittest.TestCase):
    def assert_close(self, image: Image, matte: int, quality: int, mean: float, worst: int) -> None:
        width, height, pixels = decode_jpeg(image.encode_jpeg(quality, matte))
        self.assertEqual(image.size, (width, height))
        expected = flattened(image, matte)
        errors = [abs(a - b) for p, q in zip(expected, pixels) for a, b in zip(p, q)]
        self.assertLess(sum(errors) / len(errors), mean, quality)
        self.assertLessEqual(max(errors), worst, quality)

    def test_a_render_decodes_close_to_its_pixels(self) -> None:
        image = sample(100, Mode.UNIVERSAL)  # not a multiple of 8
        for quality, mean, worst in ((100, 0.3, 6), (92, 1.5, 70), (50, 4.0, 140)):
            self.assert_close(image, 0xFFFFFF, quality, mean, worst)

    def test_transparent_corners_are_flattened_over_the_matte(self) -> None:
        self.assert_close(sample(52, Mode.KEYED), 0x0048FF, 100, 0.5, 6)

    def test_noise_and_odd_sizes_decode(self) -> None:
        for number, (width, height) in enumerate([(1, 1), (7, 9), (8, 8), (17, 24)]):
            image = Image(width, height, pattern(f"noise:{number + 30}", width, height))
            for quality in (50, 100):
                decoded = decode_jpeg(image.encode_jpeg(quality, 0x808080))
                self.assertEqual((width, height), decoded[:2])

    def test_a_flat_image_decodes_exactly(self) -> None:
        image = Image(20, 12, pattern("flat:7a96c5ff", 20, 12))
        pixels = decode_jpeg(image.encode_jpeg(100))[2]
        for pixel in pixels:
            for got, want in zip(pixel, (0x7A, 0x96, 0xC5)):
                self.assertLessEqual(abs(got - want), 1)

    def test_forgetting_coded_blocks_does_not_show_in_the_file(self) -> None:
        image = Image(40, 24, pattern("noise:77", 40, 24))
        expected = image.encode_jpeg(75)
        limit = _jpeg._MAX_REMEMBERED
        try:
            _jpeg._MAX_REMEMBERED = 1
            self.assertEqual(expected, image.encode_jpeg(75))
        finally:
            _jpeg._MAX_REMEMBERED = limit

    def test_the_tables_are_well_formed(self) -> None:
        self.assertEqual(list(range(64)), sorted(_jpeg.ZIGZAG))
        # The zigzag walks the anti-diagonals in turn.
        diagonals = [k // 8 + k % 8 for k in _jpeg.ZIGZAG]
        self.assertEqual(sorted(diagonals), diagonals)
        tables = (
            (_jpeg.DC_LUMINANCE, 12),
            (_jpeg.DC_CHROMINANCE, 12),
            (_jpeg.AC_LUMINANCE, 162),
            (_jpeg.AC_CHROMINANCE, 162),
        )
        for (counts, symbols), size in tables:
            self.assertEqual(16, len(counts))
            self.assertEqual(size, sum(counts))
            self.assertEqual(size, len(set(symbols)))
            # Kraft: the code lengths describe a prefix code that leaves the all-ones code free.
            used = sum(count << (16 - bits) for bits, count in enumerate(counts, 1))
            self.assertLess(used, 1 << 16)
        for table in (_jpeg.LUMINANCE_QUANTISER, _jpeg.CHROMINANCE_QUANTISER):
            self.assertEqual(64, len(table))
        self.assertEqual(3688, sum(_jpeg.LUMINANCE_QUANTISER))
        self.assertEqual(5505, sum(_jpeg.CHROMINANCE_QUANTISER))


if __name__ == "__main__":
    unittest.main()
