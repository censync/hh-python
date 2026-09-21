"""The image type and its encoders: SPEC.md sections 10 to 13."""

from __future__ import annotations

import operator
import os
from typing import Any, NoReturn, Tuple, Union

from . import _bmp, _jpeg, _png
from ._errors import ErrorCode, HhError
from ._model import as_bytes, check_colour

DEFAULT_JPEG_QUALITY = 92
"""The JPEG quality used when none is given."""

MAX_DIMENSION = 4096
"""The largest width and height the encoders accept."""


class Image:
    """Pixels, not pictures: ``width * height`` RGBA pixels with straight alpha.

    The pixels are row-major from the top left, 4 bytes each in the order R, G, B, A, not
    premultiplied. Turning them into a toolkit image belongs to the host; with Pillow it is
    ``PIL.Image.frombytes("RGBA", image.size, image.rgba)``.

    The encoders are deterministic: the same image gives the same bytes in every implementation
    of hh. An image is immutable, hashable and compares by value.

    Raises :class:`HhError` with ``INVALID_IMAGE`` unless both dimensions are 1..4096 and
    ``rgba``, a bytes-like object, has ``width * height * 4`` bytes.
    """

    __slots__ = ("_width", "_height", "_rgba")
    _width: int
    _height: int
    _rgba: bytes

    def __init__(self, width: int, height: int, rgba: Union[bytes, bytearray, memoryview]) -> None:
        width = operator.index(width)
        height = operator.index(height)
        pixels = as_bytes(rgba, "rgba")
        if (
            not 1 <= width <= MAX_DIMENSION
            or not 1 <= height <= MAX_DIMENSION
            or len(pixels) != width * height * 4
        ):
            raise HhError(
                ErrorCode.INVALID_IMAGE,
                f"the dimensions must be 1..{MAX_DIMENSION}, the buffer width * height * 4 bytes",
            )
        object.__setattr__(self, "_width", width)
        object.__setattr__(self, "_height", height)
        object.__setattr__(self, "_rgba", pixels)

    @property
    def width(self) -> int:
        """The number of pixels in a row."""
        return self._width

    @property
    def height(self) -> int:
        """The number of rows."""
        return self._height

    @property
    def size(self) -> Tuple[int, int]:
        """``(width, height)``."""
        return (self._width, self._height)

    @property
    def rgba(self) -> bytes:
        """The pixels: ``width * height * 4`` bytes, R, G, B, A with straight alpha."""
        return self._rgba

    def encode_png(self) -> bytes:
        """An 8-bit truecolour PNG; with alpha only if some pixel is not opaque."""
        return _png.encode(self._width, self._height, self._rgba)

    def encode_bmp(self, matte: int = 0xFFFFFF) -> bytes:
        """A 24-bit BMP; transparent pixels are flattened over ``matte`` (``0xRRGGBB``).

        Raises :class:`HhError` with ``INVALID_ARGUMENT`` unless ``matte`` is ``0..0xFFFFFF``.
        """
        check_colour(matte, "matte")
        return _bmp.encode(self._width, self._height, self._rgba, matte)

    def encode_jpeg(self, quality: int = DEFAULT_JPEG_QUALITY, matte: int = 0xFFFFFF) -> bytes:
        """Baseline JFIF, 4:4:4; transparent pixels are flattened over ``matte``.

        Offered for compatibility: JPEG rings on flat colour edges, prefer PNG.

        Raises :class:`HhError` with ``INVALID_QUALITY`` unless ``quality`` is 50..100, or with
        ``INVALID_ARGUMENT`` unless ``matte`` is ``0..0xFFFFFF``.
        """
        quality = operator.index(quality)
        if not 50 <= quality <= 100:
            raise HhError(ErrorCode.INVALID_QUALITY, "the JPEG quality must be 50..100")
        check_colour(matte, "matte")
        return _jpeg.encode(self._width, self._height, self._rgba, quality, matte)

    def save(
        self,
        path: Union[str, bytes, "os.PathLike[str]", "os.PathLike[bytes]"],
        *,
        quality: int = DEFAULT_JPEG_QUALITY,
        matte: int = 0xFFFFFF,
    ) -> None:
        """Writes the image to ``path`` in the format its extension names.

        ``.png``, ``.bmp``, and ``.jpg`` or ``.jpeg``, in upper or lower case; ``quality``
        applies to JPEG, ``matte`` to BMP and JPEG. ``path`` is what ``open`` takes: a ``str``,
        ``bytes`` or an ``os.PathLike``. The image is encoded before the file is opened.

        Raises :class:`HhError` with ``INVALID_ARGUMENT`` for any other extension and for a name
        that cannot name a file (an embedded NUL, a lone surrogate), what the encoder raises,
        and ``OSError`` when the file cannot be written.
        """
        name = os.fspath(path)
        if isinstance(name, bytes):
            extension = os.path.splitext(name)[1].decode("latin-1").lower()
        else:
            extension = os.path.splitext(name)[1].lower()
        if extension == ".png":
            data = self.encode_png()
        elif extension == ".bmp":
            data = self.encode_bmp(matte)
        elif extension in (".jpg", ".jpeg"):
            data = self.encode_jpeg(quality, matte)
        else:
            raise HhError(
                ErrorCode.INVALID_ARGUMENT, "the file name must end in .png, .bmp, .jpg or .jpeg"
            )
        try:
            file = open(name, "wb")
        except ValueError as error:
            raise HhError(
                ErrorCode.INVALID_ARGUMENT, f"the file name cannot be used: {error}"
            ) from None
        with file:
            file.write(data)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Image):
            return NotImplemented
        return self.size == other.size and self._rgba == other._rgba

    def __hash__(self) -> int:
        return hash((self._width, self._height, self._rgba))

    def __setattr__(self, name: str, value: Any) -> NoReturn:
        raise AttributeError("an Image is immutable")

    def __delattr__(self, name: str) -> NoReturn:
        raise AttributeError("an Image is immutable")

    def __reduce__(self) -> Tuple[Any, ...]:
        return (Image, (self._width, self._height, self._rgba))

    def __repr__(self) -> str:
        return f"<Image {self._width}x{self._height} RGBA>"
