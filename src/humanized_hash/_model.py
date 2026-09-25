"""The value types of the public API: enumerations, cells, layout and rendering options."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Tuple, Union

from . import _contrast
from ._errors import ErrorCode, HhError


class Mode(enum.IntEnum):
    """Universal pictures are the same for everyone; keyed pictures need the secret key.

    The two pictures of one input are unrelated. The values are those of the specification.
    """

    UNIVERSAL = 1
    """The same for everyone: what two parties compare."""
    KEYED = 2
    """Private to the holders of the key: the default inside an application."""


class Shape(enum.Enum):
    """The outline of the picture. The values are the names of the specification."""

    SQUARE = "square"
    """The default."""
    ROUND = "round"
    """The 4 x 4 grid inscribed in a circle; no cell is clipped, the cells are smaller."""


class FrameStyle(enum.Enum):
    """The frame of a picture. The values are the names of the specification.

    Every style is available in both modes. ``NONE``, ``PLAIN``, ``DOUBLE`` and ``THICK`` fit
    either shape; ``ROUNDED``, ``CHAMFERED`` and ``BRACKETS`` need the square shape, ``TICKS``
    and ``GAPS`` the round one, and rendering refuses a style that does not fit the shape with
    ``INVALID_FRAME``. A host that marks its keyed pictures with a frame picks the style;
    ``AUTOMATIC`` gives keyed square pictures rounded corners.
    """

    AUTOMATIC = "automatic"
    """Keyed and square: ``ROUNDED``; otherwise ``NONE``."""
    NONE = "none"
    """No frame."""
    PLAIN = "plain"
    """A thin square frame, or a thin ring."""
    ROUNDED = "rounded"
    """Square only: rounded corners."""
    CHAMFERED = "chamfered"
    """Square only: four cut corners."""
    DOUBLE = "double"
    """Two thin lines."""
    THICK = "thick"
    """One line three times as thick."""
    BRACKETS = "brackets"
    """Square only: corner brackets."""
    TICKS = "ticks"
    """Round only: a ring with four ticks."""
    GAPS = "gaps"
    """Round only: a ring with four gaps."""


class Figure(enum.IntEnum):
    """What a cell shows. The value is the layout value of the specification."""

    NONE = 0
    """An empty cell."""
    SQUARE = 1
    """The full cell."""
    CIRCLE = 2
    """The disc inscribed in the cell."""
    TRIANGLE_UP = 3
    """Base on the bottom side, apex at the middle of the top side."""
    TRIANGLE_RIGHT = 4
    """Base on the left side."""
    TRIANGLE_DOWN = 5
    """Base on the top side."""
    TRIANGLE_LEFT = 6
    """Base on the right side."""


@dataclass(frozen=True)
class Cell:
    """One cell of the 4 x 4 matrix.

    ``colour`` is a palette index 0..3 and is 0 for an empty cell.
    """

    figure: Figure
    colour: int


@dataclass(frozen=True)
class Layout:
    """What a fingerprint shows, for hosts that draw vectors themselves.

    ``cells`` are row-major from the top left; colours are ``0xRRGGBB``. The raster of
    :meth:`Fingerprint.render` is the canonical form and the only one covered by byte-exact
    vectors.
    """

    mode: Mode
    cells: Tuple[Cell, ...]
    palette: Tuple[int, ...]
    frame_colour: int


@dataclass(frozen=True)
class ContrastReport:
    """WCAG contrast ratios times 100 (300 means 3:1), rounded down."""

    figures_x100: int
    """The weakest palette colour against the background."""
    frame_x100: int
    """The frame against the background."""


def as_bytes(data: Union[bytes, bytearray, memoryview], name: str) -> bytes:
    """A copy of a bytes-like argument; anything else, a released view too, is a ``TypeError``."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError(f"{name} must be bytes-like, not {type(data).__name__}")
    try:
        return bytes(data)
    except ValueError:
        raise TypeError(f"{name} is a released memoryview") from None


def check_colour(value: int, name: str) -> None:
    """Refuses anything but an ``int`` in ``0..0xFFFFFF``."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an int 0xRRGGBB, not {type(value).__name__}")
    if not 0 <= value <= 0xFFFFFF:
        raise HhError(ErrorCode.INVALID_ARGUMENT, f"{name} must be 0..0xFFFFFF")


def _check_alpha(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an int, not {type(value).__name__}")
    if not 0 <= value <= 255:
        raise HhError(ErrorCode.INVALID_ARGUMENT, f"{name} must be 0..255")


@dataclass(frozen=True)
class RenderOptions:
    """The look of a render. The cells, the palette and the geometry are fixed.

    Raises :class:`HhError` with ``INVALID_ARGUMENT`` for a colour outside ``0..0xFFFFFF`` or an
    alpha outside ``0..255``.
    """

    shape: Shape = Shape.SQUARE
    """Square or round."""
    frame: FrameStyle = FrameStyle.AUTOMATIC
    """The frame style: any style that fits the shape, in either mode; see :class:`FrameStyle`."""
    background: int = 0xFFFFFF
    """The background colour as ``0xRRGGBB``."""
    background_alpha: int = 255
    """0 (transparent) to 255 (opaque). Outside rounded or chamfered corners and outside the
    disc the picture is always transparent."""
    frame_alpha: int = 255
    """0 to 255; the frame colour itself is fixed (``808080``)."""

    def __post_init__(self) -> None:
        if not isinstance(self.shape, Shape):
            raise TypeError(f"shape must be a Shape, not {type(self.shape).__name__}")
        if not isinstance(self.frame, FrameStyle):
            raise TypeError(f"frame must be a FrameStyle, not {type(self.frame).__name__}")
        check_colour(self.background, "background")
        _check_alpha(self.background_alpha, "background_alpha")
        _check_alpha(self.frame_alpha, "frame_alpha")

    def measure_contrast(self, page: int = 0xFFFFFF) -> ContrastReport:
        """Measures what these options give over a page of the colour ``page`` (``0xRRGGBB``).

        For an opaque background the page does not matter. Rendering refuses an opaque
        background with ``figures_x100`` below 200; hosts should warn below 300.
        """
        check_colour(page, "page")
        seen = _contrast.over(self.background, self.background_alpha, page)
        frame = _contrast.over(_contrast.FRAME_COLOUR, self.frame_alpha, seen)
        return ContrastReport(_contrast.figures_x100(seen), _contrast.ratio_x100(frame, seen))


DEFAULT_OPTIONS = RenderOptions()
