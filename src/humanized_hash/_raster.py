"""Geometry and rasterisation: SPEC.md sections 5 to 8.

The specification defines a picture sample by sample: 16 samples per pixel, each tested against
the outline, the frame and the figure of its cell. Testing samples one at a time is too slow for
an interpreter, so this module evaluates whole sample rows at once. A sample row is an integer
used as a bit set, one bit per sample; every condition of sections 8.2 to 8.4 is, along one row,
an interval of samples whose ends come from an integer square root or a division, so a row costs
a handful of big-integer operations. The samples of each pixel are then counted with bit
arithmetic, and the counts select the pixel values through byte translation tables. The result
is exactly the per-sample definition; the test suite compares it with a plain transcription of
section 8.
"""

from __future__ import annotations

from binascii import hexlify
from functools import lru_cache
from math import isqrt
from typing import List, Tuple

from . import _contrast
from ._errors import ErrorCode, HhError
from ._model import Cell, Figure, FrameStyle, Mode, RenderOptions, Shape

MIN_SIZE = 16
MAX_SIZE = 1024

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# Figure code 0..7 of section 5.1 to the figure.
_FIGURES = (
    Figure.NONE,
    Figure.NONE,
    Figure.SQUARE,
    Figure.CIRCLE,
    Figure.TRIANGLE_UP,
    Figure.TRIANGLE_RIGHT,
    Figure.TRIANGLE_DOWN,
    Figure.TRIANGLE_LEFT,
)


def cells(fp: bytes) -> Tuple[Cell, ...]:
    """The 16 cells of a fingerprint (section 5.1)."""
    out = []
    for b in fp[:16]:
        figure = _FIGURES[b >> 5]
        out.append(Cell(figure, 0 if figure is Figure.NONE else (b >> 3) & 3))
    return tuple(out)


def tag(fp: bytes) -> str:
    """The six-character Crockford Base32 tag (section 5.3)."""
    v = int.from_bytes(fp[16:20], "big") >> 2
    return "".join(_CROCKFORD[(v >> shift) & 31] for shift in (25, 20, 15, 10, 5, 0))


def resolve_frame(frame: FrameStyle, mode: Mode, shape: Shape) -> FrameStyle:
    """What ``automatic`` stands for (section 6)."""
    if frame is not FrameStyle.AUTOMATIC:
        return frame
    if mode is Mode.KEYED and shape is Shape.SQUARE:
        return FrameStyle.ROUNDED
    return FrameStyle.NONE


def frame_allowed(resolved: FrameStyle, mode: Mode, shape: Shape) -> bool:
    """The table of section 6: which style goes with which shape and mode."""
    if resolved in (FrameStyle.NONE, FrameStyle.PLAIN):
        return True
    if mode is not Mode.KEYED:
        return False
    if resolved in (FrameStyle.ROUNDED, FrameStyle.CHAMFERED, FrameStyle.BRACKETS):
        return shape is Shape.SQUARE
    if resolved in (FrameStyle.TICKS, FrameStyle.GAPS):
        return shape is Shape.ROUND
    return resolved in (FrameStyle.DOUBLE, FrameStyle.THICK)


class Geometry:
    """Section 7. All values are pixels."""

    __slots__ = ("size", "line", "gutter", "cell", "grid", "offset")

    def __init__(self, size: int, shape: Shape, frame: FrameStyle) -> None:
        self.size = size
        self.line = max(1, size // 48)
        self.gutter = max(1, size // 48)
        if shape is Shape.ROUND:
            k = 3 if frame in (FrameStyle.DOUBLE, FrameStyle.THICK) else 1
            margin = k * self.line + self.gutter
            # The largest t with 2 * (4 * t + 3 * g)^2 <= (S - 2 * m)^2.
            side = isqrt((size - 2 * margin) ** 2 // 2)
            self.cell = max(0, (side - 3 * self.gutter) // 4)
        else:
            margin = max(4 * self.line, size // 12)
            self.cell = (size - 2 * margin - 3 * self.gutter) // 4
        self.grid = 4 * self.cell + 3 * self.gutter
        self.offset = (size - self.grid) // 2


def mix(
    fg: int, a: int, nf: int, nb: int, background: int, ab: int
) -> Tuple[int, int, int, int]:
    """``MIX`` of section 8.5: the pixel as (R, G, B, A)."""
    total = nf * (255 * a + ab * (255 - a)) + nb * 255 * ab
    alpha = (total + 2040) // 4080
    if alpha == 0:
        return (0, 0, 0, 0)
    out = []
    for shift in (16, 8, 0):
        f = (fg >> shift) & 0xFF
        b = (background >> shift) & 0xFF
        p = nf * (255 * a * f + ab * (255 - a) * b) + nb * 255 * ab * b
        out.append((p + total // 2) // total)
    return (out[0], out[1], out[2], alpha)


# A picture is first drawn as one code byte per pixel; four translation tables turn the codes
# into the R, G, B and A planes. A canvas pixel with nf frame samples and nb background samples
# (nf + nb <= 16) has the code _TRIANGLE[nf] + nb, 0..152. A cell pixel with n figure samples of
# the palette colour c has the code _FIGURE_BASE + 17 * c + n, 153..220.
_TRIANGLE = tuple(17 * nf - nf * (nf - 1) // 2 for nf in range(17))
_FIGURE_BASE = 153

# Pixel counts travel as bytes with an offset: 0x60 + n, the sum of two hexadecimal digits.
_COUNT_BASE = 0x60
_TO_TRIANGLE = bytes(
    _TRIANGLE[v - _COUNT_BASE] if 0 <= v - _COUNT_BASE <= 16 else 0 for v in range(256)
)
_TO_FIGURE_CODE = tuple(
    bytes(
        _FIGURE_BASE + 17 * colour + v - _COUNT_BASE if 0 <= v - _COUNT_BASE <= 16 else 0
        for v in range(256)
    )
    for colour in range(4)
)


@lru_cache(maxsize=16)
def _pixel_tables(background: int, ab: int, af: int) -> Tuple[bytes, bytes, bytes, bytes]:
    """The R, G, B and A value of every pixel code for one background and frame alpha."""
    pixels = [(0, 0, 0, 0)] * 256
    for nf in range(17):
        for nb in range(17 - nf):
            pixels[_TRIANGLE[nf] + nb] = mix(_contrast.FRAME_COLOUR, af, nf, nb, background, ab)
    for index, colour in enumerate(_contrast.PALETTE):
        for n in range(17):
            pixels[_FIGURE_BASE + 17 * index + n] = mix(colour, 255, n, 16 - n, background, ab)
    return (
        bytes(p[0] for p in pixels),
        bytes(p[1] for p in pixels),
        bytes(p[2] for p in pixels),
        bytes(p[3] for p in pixels),
    )


def _interval(lo: int, hi: int, n: int) -> int:
    """The samples ``lo <= k < hi`` of a row of ``n``. Sample 0 is the most significant bit."""
    lo = max(lo, 0)
    hi = min(hi, n)
    if hi <= lo:
        return 0
    return ((1 << (hi - lo)) - 1) << (n - hi)


class _Counter:
    """Counts, for every pixel of a row, the samples that four sample rows hold."""

    __slots__ = ("pixels", "_bits", "_m5", "_m3", "_low", "_empty")

    def __init__(self, pixels: int) -> None:
        self.pixels = pixels
        self._bits = 4 * pixels
        self._m5 = int("5" * (4 * pixels), 16)
        self._m3 = int("3" * (4 * pixels), 16)
        self._low = (1 << (8 * pixels)) - 1
        self._empty = int.from_bytes(bytes((_COUNT_BASE,)) * pixels, "big")

    def count(self, r0: int, r1: int, r2: int, r3: int) -> int:
        """One byte per pixel, packed big-endian into an integer: 0x60 plus the count 0..16."""
        bits = self._bits
        x = (((((r0 << bits) | r1) << bits) | r2) << bits) | r3
        if x == 0:
            return self._empty
        # Bits per nibble, as in any population count: pairs first, then nibbles (0..4).
        x -= (x >> 1) & self._m5
        x = (x & self._m3) + ((x >> 2) & self._m3)
        # Two sample rows per nibble (0..8) keep every sum a single hexadecimal digit.
        x = (x >> (2 * bits)) + (x & self._low)
        # Hexadecimal text spreads the nibbles into bytes: "0".."8" is 0x30..0x38.
        digits = hexlify(x.to_bytes(self.pixels, "big"))
        return int.from_bytes(digits[: self.pixels], "big") + int.from_bytes(
            digits[self.pixels :], "big"
        )


class _Canvas:
    """Sections 8.2 and 8.3 for whole sample rows.

    Along a row the distance ``du`` to the nearer vertical edge grows towards the middle, so the
    samples with ``du >= x`` are a centred interval, and every condition of the two sections
    reduces to such intervals: ``abs(dx) <= m`` is ``du >= r - m``.
    """

    def __init__(self, g: Geometry, shape: Shape, style: FrameStyle) -> None:
        self.round = shape is Shape.ROUND
        self.style = style
        self.n = 4 * g.size
        self.all = (1 << self.n) - 1
        self.s8 = 8 * g.size
        self.w8 = 8 * g.line
        self.r = 4 * g.size
        self.corner = min(16 * g.offset, 4 * g.size)
        self.diagonal = (self.w8 * 1414 + 500) // 1000
        self.chamfer = max(8, 8 * ((16 * g.offset - self.diagonal - self.w8) // 8))
        self.bracket = 8 * (g.size // 4)
        self.gap = 8 * max(1, g.size // 24)
        inner = self.r - self.w8
        self.tick_end = inner - max(8, (inner - 4 * g.grid) * 6 // 10)

    def deep(self, x: int) -> int:
        """The samples with ``du >= x``. ``U = 2 * k + 1``, so ``x // 2`` samples lie before."""
        skipped = max(0, x // 2)
        width = self.n - 2 * skipped
        return ((1 << width) - 1) << skipped if width > 0 else 0

    def shallow(self, x: int) -> int:
        """The samples with ``du < x``."""
        return self.all ^ self.deep(x)

    def row(self, v: int) -> Tuple[int, int]:
        """The samples of the row ``V = v`` inside the outline, and those of them on the frame."""
        dv = min(v, self.s8 - v)
        inside, frame = self._round_row(self.r - dv) if self.round else self._square_row(dv)
        return inside, frame & inside

    def _band(self, dv: int, width: int) -> int:
        """``e < width`` with ``e = min(du, dv)``."""
        return self.all if dv < width else self.shallow(width)

    def _square_row(self, dv: int) -> Tuple[int, int]:
        style = self.style
        w8 = self.w8
        if style is FrameStyle.NONE:
            return self.all, 0
        if style is FrameStyle.PLAIN:
            return self.all, self._band(dv, w8)
        if style is FrameStyle.DOUBLE:
            second = self._band(dv, 3 * w8) & ~self._band(dv, 2 * w8)
            return self.all, self._band(dv, w8) | second
        if style is FrameStyle.THICK:
            return self.all, self._band(dv, 3 * w8)
        if style is FrameStyle.BRACKETS:
            if dv >= self.bracket:
                return self.all, 0
            return self.all, self._band(dv, w8) & self.shallow(self.bracket)
        if style is FrameStyle.CHAMFERED:
            # Inside: du + dv >= C. Frame: e < W8, or du + dv - C < D.
            inside = self.deep(self.chamfer - dv)
            return inside, self._band(dv, w8) | self.shallow(self.chamfer + self.diagonal - dv)
        # Rounded corners: within R of two edges the circle of radius R decides.
        radius = self.corner
        if dv >= radius:
            return self.all, self._band(dv, w8)
        rise = radius - dv
        inside = self.deep(radius - isqrt(radius * radius - rise * rise))
        # (R - du)^2 + (R - dv)^2 > (R - W8)^2 for the samples with du < R.
        rest = (radius - w8) ** 2 - rise * rise
        arc = self.shallow(radius if rest < 0 else radius - isqrt(rest))
        return inside, arc | (self.deep(radius) & self._band(dv, w8))

    def _disc(self, radius: int, dy: int) -> int:
        """``d2 <= radius^2``."""
        rest = radius * radius - dy * dy
        return self.deep(self.r - isqrt(rest)) if rest >= 0 else 0

    def _round_row(self, dy: int) -> Tuple[int, int]:
        """``dy`` is ``abs(V - r)``; along the row ``abs(dx) = r - du``."""
        style = self.style
        r = self.r
        w8 = self.w8
        inside = self._disc(r, dy)
        if style is FrameStyle.NONE:
            return inside, 0
        if style is FrameStyle.THICK:
            return inside, ~self._disc(r - 3 * w8, dy)
        ring = ~self._disc(r - w8, dy)
        if style is FrameStyle.DOUBLE:
            return inside, ring | (self._disc(r - 2 * w8, dy) & ~self._disc(r - 3 * w8, dy))
        if style is FrameStyle.GAPS:
            # abs(abs(dx) - abs(dy)) >= gap: abs(dx) >= dy + gap, or abs(dx) <= dy - gap.
            away = self.shallow(r - dy - self.gap + 1) | self.deep(r - dy + self.gap)
            return inside, ring & away
        if style is FrameStyle.TICKS:
            frame = ring
            if dy >= self.tick_end:
                frame |= self.deep(r - w8 + 1)
            if dy < w8:
                frame |= self.shallow(r - self.tick_end + 1)
            return inside, frame
        return inside, ring


def _canvas_codes(g: Geometry, shape: Shape, style: FrameStyle) -> List[bytes]:
    """Step 1 of section 8.5: the code bytes of every pixel row of the canvas."""
    size = g.size
    canvas = _Canvas(g, shape, style)
    counter = _Counter(size)
    rows: List[bytes] = []
    previous = None
    # V and 8 * S - V give the same row, so the lower half mirrors the upper one.
    for y in range((size + 1) // 2):
        samples = [canvas.row(8 * y + offset) for offset in (1, 3, 5, 7)]
        if samples == previous:
            rows.append(rows[-1])
            continue
        previous = samples
        inside = counter.count(*[pair[0] for pair in samples])
        frame = counter.count(*[pair[1] for pair in samples])
        triangle = int.from_bytes(frame.to_bytes(size, "big").translate(_TO_TRIANGLE), "big")
        rows.append((triangle + inside - frame).to_bytes(size, "big"))
    return rows + rows[size // 2 - 1 :: -1]


def _figure_samples(figure: Figure, v: int, h: int) -> Tuple[int, int]:
    """Section 8.4 along the sample row ``v`` of a cell: the samples ``lo <= k < hi`` of the
    figure, with ``u = 2 * k + 1`` and ``H = h``."""
    if figure is Figure.SQUARE:
        return 0, h
    if figure is Figure.TRIANGLE_RIGHT:
        # 2 * abs(v - H) <= 2 * H - u
        return 0, h - abs(v - h)
    if figure is Figure.TRIANGLE_LEFT:
        # 2 * abs(v - H) <= u
        return abs(v - h), h
    # The other figures are centred: abs(u - H) <= half.
    if figure is Figure.CIRCLE:
        half = isqrt(h * h - (v - h) * (v - h))
    elif figure is Figure.TRIANGLE_UP:
        half = v // 2
    else:
        half = (2 * h - v) // 2
    return (h - half) // 2, (h + half + 1) // 2


@lru_cache(maxsize=64)
def _figure_counts(figure: Figure, t: int) -> Tuple[bytes, ...]:
    """For every pixel of a cell of side ``t``, row by row: 0x60 plus its samples in the figure."""
    counter = _Counter(t)
    rows = []
    for py in range(t):
        samples = [
            _interval(*_figure_samples(figure, 2 * (4 * py + q) + 1, 4 * t), 4 * t)
            for q in range(4)
        ]
        rows.append(counter.count(*samples).to_bytes(t, "big"))
    return tuple(rows)


def render(fp: bytes, mode: Mode, size: int, options: RenderOptions) -> bytes:
    """Renders ``size * size * 4`` RGBA bytes, with the checks of section 6 in their order."""
    if size < MIN_SIZE or size > MAX_SIZE:
        raise HhError(ErrorCode.INVALID_SIZE, f"the size must be {MIN_SIZE}..{MAX_SIZE}")
    style = resolve_frame(options.frame, mode, options.shape)
    if not frame_allowed(style, mode, options.shape):
        raise HhError(
            ErrorCode.INVALID_FRAME,
            f"the frame {style.value} is not allowed for a {options.shape.value}"
            f" {mode.name.lower()} picture",
        )
    if options.background_alpha == 255 and _contrast.figures_x100(options.background) < 200:
        raise HhError(ErrorCode.LOW_CONTRAST, "the background is too close to a palette colour")
    g = Geometry(size, options.shape, style)
    if g.cell < 1:
        raise HhError(ErrorCode.INVALID_SIZE, "the size leaves no room for the cells")

    codes = bytearray(b"".join(_canvas_codes(g, options.shape, style)))

    # Step 2 of section 8.5: every pixel of a non-empty cell is replaced.
    t = g.cell
    for index, cell in enumerate(cells(fp)):
        if cell.figure is Figure.NONE:
            continue
        x0 = g.offset + (index % 4) * (t + g.gutter)
        y0 = g.offset + (index // 4) * (t + g.gutter)
        to_code = _TO_FIGURE_CODE[cell.colour]
        for py, counts in enumerate(_figure_counts(cell.figure, t)):
            at = (y0 + py) * size + x0
            codes[at : at + t] = counts.translate(to_code)

    rgba = bytearray(4 * size * size)
    tables = _pixel_tables(options.background, options.background_alpha, options.frame_alpha)
    for channel in range(4):
        rgba[channel::4] = codes.translate(tables[channel])
    return bytes(rgba)
