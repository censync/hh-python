"""Deterministic pseudo-random loops: any input gives a result or an HhError, nothing else."""

from __future__ import annotations

import random
import unittest

from humanized_hash import (
    BaseDigest,
    ErrorCode,
    Fingerprint,
    FrameStyle,
    HhError,
    Image,
    Mode,
    RenderOptions,
    Shape,
    _derive,
)
from humanized_hash import _raster

from .decoders import decode_bmp, decode_png


class RobustnessTest(unittest.TestCase):
    def test_random_fingerprints_render_with_random_options(self) -> None:
        generator = random.Random(0xF00D)
        expected_errors = {ErrorCode.INVALID_SIZE, ErrorCode.INVALID_FRAME, ErrorCode.LOW_CONTRAST}
        rendered = 0
        for _ in range(1500):
            fp = Fingerprint.from_bytes(generator.randbytes(32), generator.choice(list(Mode)))
            options = RenderOptions(
                shape=generator.choice(list(Shape)),
                frame=generator.choice(list(FrameStyle)),
                background=generator.randrange(0x1000000),
                background_alpha=255 if generator.randrange(3) == 0 else generator.randrange(256),
                frame_alpha=generator.randrange(256),
            )
            if generator.randrange(100) == 0:
                size = generator.randrange(2000)
            else:
                size = 8 + generator.randrange(90)
            try:
                image = fp.render(size, options)
            except HhError as error:
                self.assertIn(error.code, expected_errors)
                continue
            rendered += 1
            self.assertEqual((size, size), image.size)
            rgba = image.rgba
            self.assertEqual(size * size * 4, len(rgba))
            # A transparent pixel is 00 00 00 00.
            alpha = rgba[3::4]
            for channel in range(3):
                plane = rgba[channel::4]
                self.assertFalse(any(v for v, a in zip(plane, alpha) if a == 0))
        self.assertGreater(rendered, 200)

    def test_random_renders_survive_every_encoder(self) -> None:
        generator = random.Random(0xBEEF)
        for _ in range(40):
            fp = Fingerprint.from_bytes(generator.randbytes(32), Mode.KEYED)
            options = RenderOptions(
                background=generator.randrange(0x1000000),
                background_alpha=generator.randrange(255),
                frame_alpha=generator.randrange(256),
            )
            image = fp.render(16 + generator.randrange(60), options)
            bpp, pixels = decode_png(image.encode_png())[2:]
            self.assertEqual(4, bpp)
            self.assertEqual(image.rgba, pixels)
            bmp = image.encode_bmp(generator.randrange(0x1000000))
            self.assertEqual(image.size, decode_bmp(bmp)[:2])
            jpeg = image.encode_jpeg(50 + generator.randrange(51), generator.randrange(0x1000000))
            self.assertEqual(b"\xff\xd8", jpeg[:2])
            self.assertEqual(b"\xff\xd9", jpeg[-2:])

    def test_hexadecimal_parsing_agrees_with_a_simple_oracle(self) -> None:
        generator = random.Random(0xA11CE)
        alphabet = "0123456789abcdefABCDEFxXgG -:\n"
        for _ in range(4000):
            text = generator.choice(("0x", "0X")) if generator.randrange(4) == 0 else ""
            for _ in range(generator.randrange(12)):
                limit = 22 if generator.randrange(10) < 9 else 30
                text += alphabet[generator.randrange(limit)]
            digits = text[2:] if text[:2] in ("0x", "0X") else text
            valid = (
                len(digits) > 0
                and len(digits) % 2 == 0
                and all(c in "0123456789abcdefABCDEF" for c in digits)
            )
            try:
                decoded = _derive.decode_hex(text)
            except HhError as error:
                self.assertIs(ErrorCode.INVALID_HEX, error.code)
                self.assertFalse(valid, repr(text))
            else:
                self.assertTrue(valid, repr(text))
                self.assertEqual(digits.lower(), decoded.hex())

    def test_images_of_random_dimensions_and_buffers(self) -> None:
        generator = random.Random(0xD1CE)
        accepted = 0
        for _ in range(300):
            width = generator.randrange(-2, 12)
            height = generator.randrange(-2, 12)
            length = max(0, width * height * 4 + generator.choice((0, 0, 0, -1, 1, 4)))
            try:
                image = Image(width, height, generator.randbytes(length))
            except HhError as error:
                self.assertIs(ErrorCode.INVALID_IMAGE, error.code)
                self.assertFalse(width >= 1 and height >= 1 and length == width * height * 4)
                continue
            accepted += 1
            self.assertEqual((width, height), decode_png(image.encode_png())[:2])
            self.assertEqual((width, height), decode_bmp(image.encode_bmp())[:2])
            self.assertEqual(b"\xff\xd9", image.encode_jpeg(50 + generator.randrange(51))[-2:])
        self.assertGreater(accepted, 50)

    def test_the_geometry_leaves_the_cells_clear_of_the_frame(self) -> None:
        # Section 8.5: every cell pixel lies wholly inside the outline and off the frame, for
        # every size and look. Checked on the sample rows that cross the grid.
        for size in range(16, 1025):
            for shape in Shape:
                for style in FrameStyle:
                    if style is FrameStyle.AUTOMATIC:
                        continue
                    if not _raster.frame_allowed(style, shape):
                        continue
                    g = _raster.Geometry(size, shape, style)
                    if g.cell < 1:
                        self.assertTrue(size < 18 and shape is Shape.ROUND, (size, shape, style))
                        continue
                    self.assertGreaterEqual(g.offset, 1)
                    self.assertLessEqual(g.offset + g.grid, size)
                    canvas = _raster._Canvas(g, shape, style)
                    grid = _raster._interval(4 * g.offset, 4 * (g.offset + g.grid), 4 * size)
                    for v in (8 * g.offset + 1, 8 * (g.offset + g.grid) - 1):
                        inside, frame = canvas.row(v)
                        self.assertEqual(grid, inside & grid, (size, shape, style))
                        self.assertEqual(0, frame & grid, (size, shape, style))


if __name__ == "__main__":
    unittest.main()
