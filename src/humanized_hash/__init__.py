"""Humanized Hash (hh): an address, a public key or a hash as a small deterministic picture.

A 4 x 4 matrix of solid squares, circles and triangles in four colours that a person can compare
at a glance, made to catch address poisoning and clipboard substitution::

    from humanized_hash import BaseDigest, Fingerprint

    digest = BaseDigest.of_hex("0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed")  # slow: cache it
    fingerprint = Fingerprint.universal(digest)      # or Fingerprint.keyed(digest, key)
    image = fingerprint.render(128)                  # 128 x 128 RGBA pixels
    image.save("address.png")
    fingerprint.tag                                  # "TKSPVH", shown as TKS-PVH

Every output is byte-identical with hh-cpp, the reference implementation, which owns the
specification. The library uses integer arithmetic and the standard library only.
"""

from __future__ import annotations

from ._api import BaseDigest, Fingerprint, SecretKey
from ._errors import ErrorCode, HhError
from ._image import DEFAULT_JPEG_QUALITY, MAX_DIMENSION, Image
from ._model import (
    Cell,
    ContrastReport,
    Figure,
    FrameStyle,
    Layout,
    Mode,
    RenderOptions,
    Shape,
)
from ._raster import MAX_SIZE, MIN_SIZE
from ._version import __version__

__all__ = [
    "DEFAULT_JPEG_QUALITY",
    "MAX_DIMENSION",
    "MAX_SIZE",
    "MIN_SIZE",
    "BaseDigest",
    "Cell",
    "ContrastReport",
    "ErrorCode",
    "Figure",
    "Fingerprint",
    "FrameStyle",
    "HhError",
    "Image",
    "Layout",
    "Mode",
    "RenderOptions",
    "SecretKey",
    "Shape",
    "__version__",
]
