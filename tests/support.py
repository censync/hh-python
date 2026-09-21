"""Helpers shared by the tests: the golden vectors, test images and option parsing."""

from __future__ import annotations

import os
from typing import List, Tuple

from humanized_hash import Fingerprint, FrameStyle, Mode, RenderOptions, Shape

TESTDATA = os.environ.get("HH_TESTDATA_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "testdata"
)


def read_bytes(*parts: str) -> bytes:
    """A file below ``testdata/``."""
    with open(os.path.join(TESTDATA, *parts), "rb") as file:
        return file.read()


def records(kind: str) -> List[List[str]]:
    """The records of one type of ``testdata/vectors.tsv`` (SPEC.md section 15)."""
    lines = read_bytes("vectors.tsv").decode("utf-8").split("\n")
    rows = [line.split("\t") for line in lines if line and not line.startswith("#")]
    return [row for row in rows if row[0] == kind]


def vector_input(field: str) -> bytes:
    """``hex:<bytes>`` or ``fill:<byte>:<count>``."""
    if field.startswith("hex:"):
        return bytes.fromhex(field[4:])
    kind, value, count = field.split(":")
    assert kind == "fill"
    return bytes.fromhex(value) * int(count)


def options_of(shape: str, frame: str, background: str, frame_alpha: str) -> RenderOptions:
    """Options from their spelling in the vectors; a background is ``RRGGBBAA``."""
    return RenderOptions(
        shape=Shape(shape),
        frame=FrameStyle(frame),
        background=int(background[:6], 16),
        background_alpha=int(background[6:], 16),
        frame_alpha=int(frame_alpha),
    )


def render_case(fields: List[str]) -> Tuple[Fingerprint, int, RenderOptions]:
    """The fields fp, mode, size, shape, frame, background, frame alpha."""
    fp = Fingerprint.from_bytes(bytes.fromhex(fields[0]), Mode[fields[1].upper()])
    return fp, int(fields[2]), options_of(fields[3], fields[4], fields[5], fields[6])


def pattern(name: str, width: int, height: int) -> bytes:
    """The test images of section 15: ``flat:<RRGGBBAA>``, ``noise:<seed>``, ``opaque:<seed>``."""
    kind, argument = name.split(":")
    if kind == "flat":
        return bytes.fromhex(argument) * (width * height)
    assert kind in ("noise", "opaque")
    x = int(argument)
    rgba = bytearray(width * height * 4)
    for i in range(len(rgba)):
        x = (x * 1103515245 + 12345) % 2**31
        rgba[i] = (x >> 16) % 256
    if kind == "opaque":
        rgba[3::4] = b"\xff" * (width * height)
    return bytes(rgba)
