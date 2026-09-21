"""Error codes and the exception of the library (SPEC.md section 14)."""

from __future__ import annotations

import enum
from typing import Any, Tuple


class ErrorCode(enum.IntEnum):
    """The error conditions of the specification, with the numeric values of the C ABI.

    The values 0 (``ok``), 12 (``buffer_too_small``) and 13 (``out_of_memory``) of the C ABI have
    no counterpart here: success is a return value, buffers are managed by the interpreter and
    memory exhaustion is Python's own ``MemoryError``.
    """

    EMPTY_INPUT = 1
    """The input has no bytes."""
    INPUT_TOO_LARGE = 2
    """The input is longer than 1 048 576 bytes."""
    INVALID_HEX = 3
    """The string is not an even, non-zero number of hexadecimal digits with an optional 0x."""
    INVALID_KEY = 4
    """The key is not 32 bytes, is all zero, or was closed."""
    INVALID_DIGEST = 5
    """The base digest is not 32 bytes."""
    INVALID_FINGERPRINT = 6
    """The fingerprint is not 32 bytes or its mode is unknown."""
    INVALID_SIZE = 7
    """The image size is outside 16..1024 or leaves no room for the cells."""
    INVALID_FRAME = 8
    """The frame style is not allowed for the shape or the mode."""
    LOW_CONTRAST = 9
    """The opaque background is too close to a palette colour."""
    INVALID_QUALITY = 10
    """The JPEG quality is outside 50..100."""
    INVALID_IMAGE = 11
    """The image dimensions or the length of its buffer are invalid."""
    INVALID_ARGUMENT = 14
    """A text holds a lone surrogate, a colour or an alpha is out of range, or a file name has
    an unknown extension or cannot name a file."""

    @property
    def spec_name(self) -> str:
        """The name as the specification and the golden vectors spell it (``invalid_hex``)."""
        return self.name.lower()


class HhError(ValueError):
    """Raised for every invalid value. ``code`` is the :class:`ErrorCode` of the specification.

    Arguments of the wrong type, a released ``memoryview`` among them, raise ``TypeError`` as
    usual in Python; nothing else is raised by the library apart from ``MemoryError`` and, in
    :meth:`Image.save`, ``OSError``.
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code

    def __reduce__(self) -> Tuple[Any, ...]:
        # Keeps the code when the exception crosses a process boundary (pickle, multiprocessing).
        return (type(self), (self.code, str(self)))
