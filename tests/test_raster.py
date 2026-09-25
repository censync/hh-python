"""The rasteriser against a per-sample transcription of SPEC.md section 8.

The library evaluates whole sample rows with bit arithmetic; ``tests/reference.py`` tests one
sample at a time. Both must give the same bytes for every size, shape, frame, background and
alpha.
"""

from __future__ import annotations

import random
import unittest
from typing import Iterator, List, Tuple

from humanized_hash import Fingerprint, FrameStyle, Mode, RenderOptions, Shape

from .reference import Reference

# Every pair of a shape and a frame that renders, each with a mode: True is keyed. Only automatic
# depends on the mode, so it comes in both; the other styles are spread over the two modes.
LOOKS: List[Tuple[str, str, bool]] = [
    ("square", "automatic", False),
    ("square", "automatic", True),
    ("square", "none", True),
    ("square", "plain", False),
    ("square", "rounded", False),
    ("square", "chamfered", True),
    ("square", "double", False),
    ("square", "thick", True),
    ("square", "brackets", False),
    ("round", "automatic", False),
    ("round", "none", True),
    ("round", "plain", False),
    ("round", "double", True),
    ("round", "thick", False),
    ("round", "ticks", False),
    ("round", "gaps", True),
]

# Backgrounds that pass the contrast rule when opaque, with a range of alphas.
BACKGROUNDS = [
    (0xFFFFFF, 255),
    (0x121212, 255),
    (0x000000, 0),
    (0xF2F2F2, 255),
    (0x123456, 128),
    (0x9E9E9E, 1),
    (0xFFFFFF, 254),
    (0x00FF00, 37),
]
FRAME_ALPHAS = [255, 0, 1, 100, 200, 254]


def fingerprints(seed: int) -> Iterator[bytes]:
    """First every figure in every colour, then pseudo-random bytes."""
    yield bytes(((2 + i % 6) << 5) | ((i // 3 % 4) << 3) | (i % 8) for i in range(32))
    generator = random.Random(seed)
    while True:
        yield generator.randbytes(32)


class Case:
    """One render, by the library and by the reference."""

    def __init__(self, fp: bytes, size: int, look: Tuple[str, str, bool], variant: int) -> None:
        shape, frame, keyed = look
        background, ab = BACKGROUNDS[variant % len(BACKGROUNDS)]
        af = FRAME_ALPHAS[variant % len(FRAME_ALPHAS)]
        self.name = f"{size} {shape} {frame} keyed={keyed} {background:06x}/{ab} frame alpha {af}"
        self.size = size
        options = RenderOptions(Shape(shape), FrameStyle(frame), background, ab, af)
        mode = Mode.KEYED if keyed else Mode.UNIVERSAL
        self.rgba = Fingerprint.from_bytes(fp, mode).render(size, options).rgba
        colour = (background >> 16, (background >> 8) & 0xFF, background & 0xFF)
        self.reference = Reference(fp, keyed, size, shape, frame, colour, ab, af)

    def library_row(self, y: int) -> bytes:
        return self.rgba[4 * self.size * y : 4 * self.size * (y + 1)]


class RasterTest(unittest.TestCase):
    def test_whole_pictures_of_every_size_from_16_to_96(self) -> None:
        source = fingerprints(1)
        for size in range(16, 97):
            # Two looks per size, so that every look meets many sizes and every variant.
            for step in (0, 7):
                look = LOOKS[(size + step) % len(LOOKS)]
                if look[0] == "round" and look[1] in ("double", "thick") and size < 18:
                    look = LOOKS[0]
                case = Case(next(source), size, look, size + step)
                with self.subTest(case.name):
                    self.assertEqual(case.reference.render(), case.rgba)

    def test_rows_of_every_look_at_every_size_from_16_to_96(self) -> None:
        source = fingerprints(2)
        chooser = random.Random(3)
        for size in range(16, 97):
            for number, look in enumerate(LOOKS):
                if look[0] == "round" and look[1] in ("double", "thick") and size < 18:
                    continue
                case = Case(next(source), size, look, size * 5 + number)
                rows = {0, size // 12, chooser.randrange(size), chooser.randrange(size)}
                for y in sorted(rows):
                    with self.subTest(case.name, row=y):
                        self.assertEqual(case.reference.row(y), case.library_row(y))

    def test_rows_of_large_pictures(self) -> None:
        source = fingerprints(4)
        chooser = random.Random(5)
        sizes = [97, 127, 128, 129, 191, 255, 256, 383, 500, 512, 767, 1000, 1023, 1024]
        for size in sizes:
            for number, look in enumerate(LOOKS):
                case = Case(next(source), size, look, size + number)
                for y in (chooser.randrange(size // 8), chooser.randrange(size)):
                    with self.subTest(case.name, row=y):
                        self.assertEqual(case.reference.row(y), case.library_row(y))

    def test_the_lower_half_mirrors_the_upper_half_only_in_the_canvas(self) -> None:
        # The figures are not symmetric; a picture with empty cells only is.
        for size in (16, 17, 64, 65):
            image = Fingerprint.from_bytes(bytes(32), Mode.KEYED).render(size)
            rows = [image.rgba[4 * size * y : 4 * size * (y + 1)] for y in range(size)]
            self.assertEqual(rows, rows[::-1])


if __name__ == "__main__":
    unittest.main()
