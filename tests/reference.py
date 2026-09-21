"""A plain transcription of SPEC.md sections 5 to 8: one sample at a time, no shortcuts.

It is slow and it is the yardstick: the rasteriser of the library must give these pixels.
Nothing here is shared with the library.
"""

from __future__ import annotations

from typing import Callable, List, Tuple

PALETTE = ((0x7A, 0x96, 0xC5), (0x89, 0x0A, 0xF0), (0xC1, 0x04, 0x45), (0xD4, 0x82, 0x00))
FRAME = (0x80, 0x80, 0x80)

Pixel = Tuple[int, int, int, int]


def resolve(frame: str, keyed: bool, shape: str) -> str:
    """Section 6: what ``automatic`` stands for."""
    if frame != "automatic":
        return frame
    return "rounded" if keyed and shape == "square" else "none"


class Reference:
    """One picture: a fingerprint, a size and the options, all as plain values."""

    def __init__(
        self,
        fp: bytes,
        keyed: bool,
        size: int,
        shape: str,
        frame: str,
        background: Tuple[int, int, int],
        ab: int,
        af: int,
    ) -> None:
        self.fp = fp
        self.size = size
        self.shape = shape
        self.style = resolve(frame, keyed, shape)
        self.background = background
        self.ab = ab
        self.af = af
        # Section 7.
        s = size
        self.w = max(1, s // 48)
        self.g = max(1, s // 48)
        if shape == "square":
            m = max(4 * self.w, s // 12)
            self.t = (s - 2 * m - 3 * self.g) // 4
        else:
            k = 3 if self.style in ("double", "thick") else 1
            m = k * self.w + self.g
            t = 0
            while 2 * (4 * (t + 1) + 3 * self.g) ** 2 <= (s - 2 * m) ** 2:
                t += 1
            self.t = t
        self.grid = 4 * self.t + 3 * self.g
        self.o = (s - self.grid) // 2
        self._inside, self._on_frame = self._tests()

    def mix(self, colour: Tuple[int, int, int], a: int, nf: int, nb: int) -> Pixel:
        """Section 8.5."""
        ab = self.ab
        total = nf * (255 * a + ab * (255 - a)) + nb * 255 * ab
        alpha = (total + 2040) // 4080
        if alpha == 0:
            return (0, 0, 0, 0)
        out = []
        for c in range(3):
            p = nf * (255 * a * colour[c] + ab * (255 - a) * self.background[c])
            p += nb * 255 * ab * self.background[c]
            out.append((p + total // 2) // total)
        return (out[0], out[1], out[2], alpha)

    def _tests(self) -> Tuple[Callable[[int, int], bool], Callable[[int, int], bool]]:
        """Sections 8.2 and 8.3 as two predicates of a sample (U, V)."""
        s = self.size
        s8 = 8 * s
        w8 = 8 * self.w
        r = 4 * s
        shape = self.shape
        style = self.style
        big_r = min(16 * self.o, 4 * s)
        big_d = (w8 * 1414 + 500) // 1000
        big_c = max(8, 8 * ((16 * self.o - big_d - w8) // 8))
        inner = r - w8
        big_q = inner - max(8, (inner - 4 * self.grid) * 6 // 10)

        def inside(u: int, v: int) -> bool:
            du = min(u, s8 - u)
            dv = min(v, s8 - v)
            if shape == "round":
                return (u - r) ** 2 + (v - r) ** 2 <= r * r
            if style == "rounded":
                return not (du < big_r and dv < big_r) or (
                    (big_r - du) ** 2 + (big_r - dv) ** 2 <= big_r * big_r
                )
            if style == "chamfered":
                return du + dv >= big_c
            return True

        def on_frame(u: int, v: int) -> bool:
            du = min(u, s8 - u)
            dv = min(v, s8 - v)
            e = min(du, dv)
            dx = u - r
            dy = v - r
            d2 = dx * dx + dy * dy
            if style == "none":
                return False
            if shape == "square":
                if style == "plain":
                    return e < w8
                if style == "double":
                    return e < w8 or 2 * w8 <= e < 3 * w8
                if style == "thick":
                    return e < 3 * w8
                if style == "brackets":
                    return e < w8 and max(du, dv) < 8 * (s // 4)
                if style == "chamfered":
                    return e < w8 or du + dv - big_c < big_d
                if style == "rounded":
                    if du < big_r and dv < big_r:
                        return (big_r - du) ** 2 + (big_r - dv) ** 2 > (big_r - w8) ** 2
                    return e < w8
            else:
                if style == "plain":
                    return d2 > (r - w8) ** 2
                if style == "double":
                    return d2 > (r - w8) ** 2 or (r - 3 * w8) ** 2 < d2 <= (r - 2 * w8) ** 2
                if style == "thick":
                    return d2 > (r - 3 * w8) ** 2
                if style == "gaps":
                    return d2 > (r - w8) ** 2 and abs(abs(dx) - abs(dy)) >= 8 * max(1, s // 24)
                if style == "ticks":
                    return (
                        d2 > (r - w8) ** 2
                        or (abs(dx) < w8 and abs(dy) >= big_q)
                        or (abs(dy) < w8 and abs(dx) >= big_q)
                    )
            raise AssertionError(f"{style} does not go with {shape}")

        return inside, on_frame

    def canvas_pixel(self, x: int, y: int) -> Pixel:
        """Step 1 of section 8.5 for one pixel."""
        inside, on_frame = self._inside, self._on_frame
        nin = 0
        nfr = 0
        for q in range(4):
            for p in range(4):
                u = 2 * (4 * x + p) + 1
                v = 2 * (4 * y + q) + 1
                if inside(u, v):
                    nin += 1
                    if on_frame(u, v):
                        nfr += 1
        return self.mix(FRAME, self.af, nfr, nin - nfr)

    def cell_pixel(self, index: int, px: int, py: int) -> Pixel:
        """Step 2 of section 8.5 for one pixel of a non-empty cell."""
        b = self.fp[index]
        code = b // 32
        colour = PALETTE[(b // 8) % 4]
        h = 4 * self.t
        nc = 0
        for q in range(4):
            for p in range(4):
                u = 2 * (4 * px + p) + 1
                v = 2 * (4 * py + q) + 1
                if code == 2:
                    hit = True
                elif code == 3:
                    hit = (u - h) ** 2 + (v - h) ** 2 <= h * h
                elif code == 4:
                    hit = 2 * abs(u - h) <= v
                elif code == 5:
                    hit = 2 * abs(v - h) <= 2 * h - u
                elif code == 6:
                    hit = 2 * abs(u - h) <= 2 * h - v
                else:
                    hit = 2 * abs(v - h) <= u
                if hit:
                    nc += 1
        return self.mix(colour, 255, nc, 16 - nc)

    def pixel(self, x: int, y: int) -> Pixel:
        """The final value of the pixel (x, y)."""
        for index in range(16):
            if self.fp[index] // 32 < 2:
                continue
            x0 = self.o + (index % 4) * (self.t + self.g)
            y0 = self.o + (index // 4) * (self.t + self.g)
            if x0 <= x < x0 + self.t and y0 <= y < y0 + self.t:
                return self.cell_pixel(index, x - x0, y - y0)
        return self.canvas_pixel(x, y)

    def row(self, y: int) -> bytes:
        """One pixel row as RGBA bytes."""
        out: List[int] = []
        for x in range(self.size):
            out.extend(self.pixel(x, y))
        return bytes(out)

    def render(self) -> bytes:
        """The whole picture as RGBA bytes."""
        return b"".join(self.row(y) for y in range(self.size))
