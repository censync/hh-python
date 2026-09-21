"""The command line tool: ``humanized-hash`` or ``python -m humanized_hash``.

    humanized-hash 0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed --out address.png
    humanized-hash --text bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4 --size 256 --out a.png
    humanized-hash <hex> --key <64 hex digits> --shape round --frame double --out private.png

The single-render options and the output are those of ``hh_cli`` of hh-cpp. ``--batch`` and
``--generate`` serve the differential test (``tools/crosscheck.sh``): both tools must print the
same lines and write the same files.

The batch format is defined at the head of ``examples/hh_cli.cpp`` of hh-cpp and followed to the
letter:

- The file is bytes. Lines end with LF; one CR before it is dropped. A line that is then empty
  or begins with ``#`` is skipped and not counted. Cases are numbered from 1.
- A case is exactly 11 fields separated by runs of ASCII spaces or tabs:
  ``hex|text  input  key|-  size  shape  frame  background  frame-alpha  format  quality  matte``
- size, frame-alpha and quality are 1 to 10 ASCII digits without a sign. A frame alpha above 255
  is a bad case; a size or a quality of any magnitude is the library's to refuse.
- For ``text`` the input is the hexadecimal form of the UTF-8 bytes, which reach the library
  verbatim; for ``hex`` it is passed on as written. background is 8 and matte 6 hexadecimal
  digits.
- A line that breaks these rules, or names an unknown kind, shape or frame, prints its number
  and ``bad_case``, separated by a tab. Everything else is the library's answer: the number and
  the error name and, for ``ok``, the base digest, the fingerprint, the tag and the key check
  value (or ``-``), and the file ``DIR/case-<n>.<format>``. An unknown format is
  ``invalid_argument`` and the last error to be reported.

The numeric options of a single render follow the same rule; a malformed one is wrong usage.

This is a demonstration and a test tool. A real host never takes a key from the command line,
where other processes can read it.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple, TypeVar, Union

from ._api import BaseDigest, Fingerprint, SecretKey
from ._errors import ErrorCode, HhError
from ._image import DEFAULT_JPEG_QUALITY
from ._model import Figure, FrameStyle, RenderOptions, Shape

_FORMATS = ("png", "bmp", "jpeg", "rgba")
# What --out may end in to choose a format; any other name gives PNG.
_EXTENSIONS = {"bmp": "bmp", "rgba": "rgba", "jpg": "jpeg", "jpeg": "jpeg"}
_NUMBER = re.compile(r"[0-9]{1,10}")
_SEPARATORS = re.compile(r"[ \t]+")
_LARGEST_NUMBER = 0x7FFFFFFF
_T = TypeVar("_T")
_FIGURE_MARKS = {
    Figure.NONE: ".",
    Figure.SQUARE: "S",
    Figure.CIRCLE: "O",
    Figure.TRIANGLE_UP: "^",
    Figure.TRIANGLE_RIGHT: ">",
    Figure.TRIANGLE_DOWN: "v",
    Figure.TRIANGLE_LEFT: "<",
}


class _BadCase(Exception):
    """A batch line that is not a case."""


@dataclass
class _Request:
    """One picture to make."""

    text: Union[str, bytes, None] = None  # a text input; bytes are UTF-8 taken verbatim
    hex: str = ""
    key: Optional[str] = None
    size: int = 128
    options: RenderOptions = RenderOptions()
    format: str = "png"
    quality: int = DEFAULT_JPEG_QUALITY
    matte: int = 0xFFFFFF


def _strict_hex(text: str, length: int) -> Optional[bytes]:
    """``length`` bytes from hexadecimal digits of either case, or None."""
    if len(text) != 2 * length or any(c not in "0123456789abcdefABCDEF" for c in text):
        return None
    return bytes.fromhex(text)


def _run(request: _Request) -> Tuple[BaseDigest, Fingerprint, Optional[bytes], bytes]:
    """The digest, the fingerprint, the key check value and the encoded picture, in the order
    in which ``hh_cli`` detects errors."""
    if request.text is not None:
        digest = BaseDigest.of_text(request.text)
    else:
        digest = BaseDigest.of_hex(request.hex)
    check_value = None
    if request.key is None:
        fingerprint = Fingerprint.universal(digest)
    else:
        # A key that is not hexadecimal is as invalid as one of the wrong length.
        with SecretKey(bytes.fromhex(request.key) if _is_hex(request.key) else b"") as key:
            check_value = key.check_value
            fingerprint = Fingerprint.keyed(digest, key)
    image = fingerprint.render(request.size, request.options)
    if request.format == "png":
        data = image.encode_png()
    elif request.format == "bmp":
        data = image.encode_bmp(request.matte)
    elif request.format == "jpeg":
        data = image.encode_jpeg(request.quality, request.matte)
    elif request.format == "rgba":
        data = image.rgba
    else:
        raise HhError(ErrorCode.INVALID_ARGUMENT, f"unknown format {request.format}")
    return digest, fingerprint, check_value, data


def _is_hex(text: str) -> bool:
    return len(text) % 2 == 0 and all(c in "0123456789abcdefABCDEF" for c in text)


def _number(text: str) -> int:
    """1 to 10 ASCII digits without a sign, as ``hh_cli`` reads a number.

    Values beyond what the library takes are clamped to a value that is just as invalid, which
    is what a tool with 32-bit numbers has to do.
    """
    if not _NUMBER.fullmatch(text):
        raise ValueError(text)
    return min(int(text), _LARGEST_NUMBER)


def _frame_alpha(text: str) -> int:
    value = _number(text)
    if value > 255:
        raise ValueError(text)
    return value


def _background(text: str) -> Tuple[int, int]:
    rgba = _strict_hex(text, 4)
    if rgba is None:
        raise ValueError(text)
    return int.from_bytes(rgba[:3], "big"), rgba[3]


def _matte(text: str) -> int:
    rgb = _strict_hex(text, 3)
    if rgb is None:
        raise ValueError(text)
    return int.from_bytes(rgb, "big")


def _case(fields: Sequence[str]) -> _Request:
    """A batch line: hex|text <input> <key|-> <size> <shape> <frame> <background>
    <frame alpha> <format> <quality> <matte>."""
    if len(fields) != 11 or fields[0] not in ("hex", "text"):
        raise _BadCase()
    request = _Request()
    try:
        if fields[0] == "text":
            if not _is_hex(fields[1]):
                raise _BadCase()
            request.text = bytes.fromhex(fields[1])
        else:
            request.hex = fields[1]
        request.key = None if fields[2] == "-" else fields[2]
        request.size = _number(fields[3])
        background, background_alpha = _background(fields[6])
        request.options = RenderOptions(
            Shape(fields[4]),
            FrameStyle(fields[5]),
            background,
            background_alpha,
            _frame_alpha(fields[7]),
        )
        request.format = fields[8]
        request.quality = _number(fields[9])
        request.matte = _matte(fields[10])
    except ValueError:
        raise _BadCase() from None
    return request


def _batch(path: str, directory: str) -> int:
    try:
        with open(path, "rb") as file:
            content = file.read()
    except OSError:
        print(f"cannot read {path}", file=sys.stderr)
        return 1
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError:
        # Reported when the first file cannot be written, as hh_cli does.
        pass
    number = 0
    # ISO-8859-1 maps every byte to one character, so any file can be read and only the ASCII
    # space and tab separate fields.
    for line in content.decode("iso-8859-1").split("\n"):
        if line.endswith("\r"):
            line = line[:-1]
        if not line or line.startswith("#"):
            continue
        number += 1
        try:
            request = _case([field for field in _SEPARATORS.split(line) if field])
            digest, fingerprint, check_value, data = _run(request)
        except _BadCase:
            print(f"{number}\tbad_case")
            continue
        except HhError as error:
            print(f"{number}\t{error.code.spec_name}")
            continue
        kcv = "-" if check_value is None else check_value.hex()
        values = f"{number}\tok\t{digest.hex()}\t{fingerprint.hex()}\t{fingerprint.tag}\t{kcv}"
        # The line ends once the file is written, as in hh_cli.
        print(values, end="")
        try:
            with open(os.path.join(directory, f"case-{number}.{request.format}"), "wb") as file:
                file.write(data)
        except OSError:
            print(f"cannot write into {directory}", file=sys.stderr)
            return 1
        print()
    return 0


class _Random:
    """The xorwow generator behind ``kotlin.random.Random(seed)``.

    With it ``--generate`` prints the very cases that the tool of hh-kotlin prints for a seed.
    """

    def __init__(self, seed: int) -> None:
        seed &= 0xFFFFFFFF
        sign = 0xFFFFFFFF if seed & 0x80000000 else 0
        self._x = seed
        self._y = sign
        self._z = 0
        self._w = 0
        self._v = seed ^ 0xFFFFFFFF
        self._addend = ((seed << 10) ^ (sign >> 4)) & 0xFFFFFFFF
        for _ in range(64):
            self._next()

    def _next(self) -> int:
        """32 bits, modulo 2^32 throughout."""
        t = self._x
        t ^= t >> 2
        self._x, self._y, self._z = self._y, self._z, self._w
        v0 = self._v
        self._w = v0
        t = (t ^ (t << 1) ^ v0 ^ (v0 << 4)) & 0xFFFFFFFF
        self._v = t
        self._addend = (self._addend + 362437) & 0xFFFFFFFF
        return (t + self._addend) & 0xFFFFFFFF

    def _bits(self, count: int) -> int:
        value = self._next()
        return value >> (32 - count) if count else 0

    def below(self, bound: int) -> int:
        """A value in ``0 <= v < bound``."""
        if bound & (bound - 1) == 0:
            return self._bits(bound.bit_length() - 1)
        while True:
            bits = self._next() >> 1
            value = bits % bound
            if bits - value + (bound - 1) < 0x80000000:
                return value

    def boolean(self) -> bool:
        return self._bits(1) != 0

    def bytes(self, count: int) -> bytes:
        out = bytearray()
        for _ in range(count // 4):
            out += self._next().to_bytes(4, "little")
        rest = count % 4
        out += self._bits(8 * rest).to_bytes(4, "little")[:rest]
        return bytes(out)


def _generate(count: int, seed: int) -> int:
    """Prints pseudo-random cases, valid and invalid ones, for ``--batch``."""
    random = _Random(seed)
    frames = [style.value for style in FrameStyle]
    backgrounds = [
        "ffffffff", "ffffffff", "00000000", "00000000",
        "121212ff", "000000ff", "f2f2f2ff", "9e9e9eff",
    ]
    texts = [
        "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4",
        "caf\u00e9 \u20ac \U00010348",
        "T",
        "  spaced  ",
    ]
    print(f"# {count} cases, seed {seed}")
    for _ in range(count):
        text = random.below(6) == 0
        if text:
            chosen = texts[random.below(len(texts))]
            data = (chosen + str(random.below(1000))).encode("utf-8").hex()
        elif random.below(25) == 0:
            data = ["zz", "abc", "0x", "12_34"][random.below(4)]
        else:
            prefix = "0x" if random.boolean() else ""
            data = prefix + random.bytes(1 + random.below(40)).hex()
        choice = random.below(8)
        if choice < 3:
            key = "-"
        elif choice == 3:
            key = "00" * 32 if random.below(4) == 0 else random.bytes(31).hex()
        else:
            key = random.bytes(32).hex()
        choice = random.below(30)
        size = (15, 1025, 1024, 16)[choice] if choice < 4 else 17 + random.below(240)
        if random.below(3) == 0:
            background = random.bytes(4).hex()
        else:
            background = backgrounds[random.below(len(backgrounds))]
        round_shape = random.boolean()
        # Mostly a frame that fits the mode and the shape, so that most cases render.
        if key == "-":
            fitting = ["automatic", "none", "plain"]
        elif round_shape:
            fitting = ["automatic", "none", "plain", "double", "thick", "ticks", "gaps"]
        else:
            fitting = [
                "automatic", "none", "plain", "rounded", "chamfered", "double", "thick", "brackets",
            ]
        if random.below(8) == 0:
            frame = frames[random.below(len(frames))]
        else:
            frame = fitting[random.below(len(fitting))]
        picture_format = ["png", "png", "bmp", "jpeg", "rgba"][random.below(5)]
        quality = 40 + random.below(70) if random.below(12) == 0 else 50 + random.below(51)
        frame_alpha = random.below(256)
        matte = random.bytes(3).hex()
        shape = "round" if round_shape else "square"
        print(
            "text" if text else "hex", data, key, size, shape, frame, background, frame_alpha,
            picture_format, quality, matte,
        )
    return 0


def _option(parse: Callable[[str], _T], what: str) -> Callable[[str], _T]:
    """``parse`` as the type of an option: a value it refuses is wrong usage."""

    def convert(text: str) -> _T:
        try:
            return parse(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{text!r} is not {what}") from None

    return convert


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="humanized-hash",
        description="Humanized Hash: an address or a hash in, a picture out.",
        epilog="a case of --batch is 11 fields separated by spaces or tabs: hex|text <input> "
        "<key|-> <size> <shape> <frame> <background> <frame alpha> <format> <quality> <matte> "
        "(the input of a text case is the hex form of its bytes; numbers are 1 to 10 digits "
        "without a sign)",
    )
    parser.add_argument(
        "input", nargs="?", help="hexadecimal bytes (optional 0x), or text with --text"
    )
    parser.add_argument("--text", action="store_true", help="hash the input as UTF-8 text")
    parser.add_argument(
        "--key", metavar="HEX", help="64 hex digits: render the keyed (private) picture"
    )
    parser.add_argument(
        "--size",
        type=_option(_number, "1 to 10 digits without a sign"),
        default=128,
        metavar="N",
        help="16..1024 pixels (default 128)",
    )
    parser.add_argument(
        "--shape", choices=[shape.value for shape in Shape], default="square", help="default square"
    )
    parser.add_argument(
        "--frame",
        choices=[style.value for style in FrameStyle],
        default="automatic",
        help="default automatic",
    )
    parser.add_argument(
        "--background",
        type=_option(_background, "8 hexadecimal digits"),
        default=(0xFFFFFF, 255),
        metavar="RRGGBBAA",
        help="background colour and alpha (default ffffffff)",
    )
    parser.add_argument(
        "--frame-alpha",
        type=_option(_frame_alpha, "0..255 in digits without a sign"),
        default=255,
        metavar="N",
        help="0..255 (default 255)",
    )
    parser.add_argument(
        "--format",
        choices=_FORMATS,
        help="default png, or what --out ends in: .bmp, .rgba, .jpg or .jpeg in lower case",
    )
    parser.add_argument(
        "--quality",
        type=_option(_number, "1 to 10 digits without a sign"),
        default=DEFAULT_JPEG_QUALITY,
        metavar="N",
        help="JPEG quality 50..100 (default 92)",
    )
    parser.add_argument(
        "--matte",
        type=_option(_matte, "6 hexadecimal digits"),
        default=0xFFFFFF,
        metavar="RRGGBB",
        help="what BMP and JPEG flatten transparency over (default ffffff)",
    )
    parser.add_argument(
        "--out", metavar="FILE", help="write the picture; without it only the values are printed"
    )
    parser.add_argument(
        "--batch",
        nargs=2,
        metavar=("FILE", "DIR"),
        help="run the cases of FILE, write case-<n>.<format> into DIR",
    )
    parser.add_argument(
        "--generate",
        nargs=2,
        type=int,
        metavar=("COUNT", "SEED"),
        help="print COUNT pseudo-random cases for --batch",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Runs the tool and returns its exit status: 0, 1 for an error, 2 for wrong usage."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.generate is not None:
        return _generate(args.generate[0], args.generate[1])
    if args.batch is not None:
        return _batch(args.batch[0], args.batch[1])
    if args.input is None:
        parser.error("an input is required")

    request = _Request()
    if args.text:
        try:
            # The bytes of the argument as the shell passed them.
            request.text = args.input.encode("utf-8", "surrogateescape")
        except UnicodeEncodeError:
            request.text = args.input
    else:
        request.hex = args.input
    request.key = args.key or None
    request.size = args.size
    request.options = RenderOptions(
        Shape(args.shape),
        FrameStyle(args.frame),
        args.background[0],
        args.background[1],
        args.frame_alpha,
    )
    request.quality = args.quality
    request.matte = args.matte
    if args.format is not None:
        request.format = args.format
    elif args.out is not None and len(args.out) > 4:
        # What follows the last dot, compared as it is written: hh_cli does the same.
        request.format = _EXTENSIONS.get(args.out[args.out.rfind(".") + 1 :], "png")

    try:
        digest, fingerprint, check_value, data = _run(request)
    except HhError as error:
        print(f"error: {error.code.spec_name}: {error}", file=sys.stderr)
        return 1
    tag = fingerprint.tag
    print(f"mode         {fingerprint.mode.name.lower()}")
    print(f"base digest  {digest.hex()}")
    print(f"fingerprint  {fingerprint.hex()}")
    print(f"tag          {tag[:3]}-{tag[3:]}")
    if check_value is not None:
        print(f"key check    {check_value.hex()}")
    cells = fingerprint.layout.cells
    for row in range(4):
        marks = "".join(
            _FIGURE_MARKS[cell.figure]
            + (" " if cell.figure is Figure.NONE else str(cell.colour))
            + " "
            for cell in cells[4 * row : 4 * row + 4]
        )
        print(("cells        " if row == 0 else "             ") + marks)
    if args.out is not None:
        try:
            with open(args.out, "wb") as file:
                file.write(data)
        except OSError:
            print(f"cannot write {args.out}", file=sys.stderr)
            return 1
        print(f"wrote        {args.out} ({len(data)} bytes)")
    return 0
