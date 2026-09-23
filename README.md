# hh - Humanized Hash (Python)

hh turns a blockchain address, a public key or any hash into a small deterministic picture that a
person can compare at a glance: a 4 x 4 matrix of solid squares, circles and triangles in four
colours. It exists to catch address poisoning and clipboard substitution, which work because
people check only the first and last characters of a long string. The colours are chosen so that
people with a colour vision deficiency can tell them apart as well.

| `0x1234567890abcdef00112233445566778899aabb` | `0x12345678f1e2d3c4b5a69788796a5b4c8899aabb` |
|---|---|
| ![picture of the first address](https://raw.githubusercontent.com/censync/hh-python/v1.0.0/testdata/golden/poison-a-universal-128.png) | ![picture of the second address](https://raw.githubusercontent.com/censync/hh-python/v1.0.0/testdata/golden/poison-b-universal-128.png) |

The two addresses agree in their first and last eight hex digits. Their pictures are unrelated.

This is the Python implementation, hh-python, published on PyPI as `humanized-hash`. It is pure
Python, depends on the standard library only, supports CPython 3.9 to 3.14 and PyPy 3.10, and
produces, byte for byte, the output of the C++ reference implementation
[hh-cpp](https://github.com/censync/hh-cpp), which owns the
[specification](https://github.com/censync/hh-cpp/blob/v1.0.0/docs/SPEC.md) and the golden vectors.
`testdata/` is a byte-identical copy of those vectors; `testdata/SOURCE` names the hh-cpp release
they came from.

## Implementations

Every implementation produces the same pictures, tags and encoded files, byte for byte, and its
tests check it against a copy of the golden vectors of hh-cpp.

| Language | Repository | Package | Install |
|---|---|---|---|
| C++17, C ABI | [hh-cpp](https://github.com/censync/hh-cpp), the reference: specification and golden vectors | CMake `hh::hh`, pkg-config `hh` ([releases](https://github.com/censync/hh-cpp/releases)) | CMake `FetchContent` or `find_package(hh)` |
| Kotlin and Java: JVM, Android | [hh-kotlin](https://github.com/censync/hh-kotlin) | Maven Central [`io.github.censync:hh`](https://central.sonatype.com/artifact/io.github.censync/hh) | `implementation("io.github.censync:hh:1.0.0")` |
| TypeScript and JavaScript: browsers, Node.js, Deno, Bun | [hh-ts](https://github.com/censync/hh-ts) | npm [`@censync/hh`](https://www.npmjs.com/package/@censync/hh) | `npm install @censync/hh` |
| Go | [go-hh](https://github.com/censync/go-hh) | [`github.com/censync/go-hh`](https://pkg.go.dev/github.com/censync/go-hh) | `go get github.com/censync/go-hh` |
| Python | hh-python (this repository) | PyPI [`humanized-hash`](https://pypi.org/project/humanized-hash/) | `pip install humanized-hash` |

## A longer example: Sui

A Sui address has 64 hex digits, and nobody reads 64 digits. The second address below differs from
the first in one digit, the third in two; the changed digits are marked. In the text they are easy
to miss. The pictures and the tags are unrelated, because every cell depends on every bit of the
input.

| Picture | Address | Tag |
|---|---|---|
| ![picture of the first Sui address](https://raw.githubusercontent.com/censync/hh-python/v1.0.0/docs/images/sui-a.png) | <code>0xeab3150efcb34ff74930d8f3d491be109070a39e4d380de7737aff5c72a0b6b2</code> | `B6P-65H` |
| ![picture of the second Sui address](https://raw.githubusercontent.com/censync/hh-python/v1.0.0/docs/images/sui-b.png) | <code>0xeab3150efcb34ff74930d8f<ins><b>8</b></ins>d491be109070a39e4d380de7737aff5c72a0b6b2</code> | `Q60-QKR` |
| ![picture of the third Sui address](https://raw.githubusercontent.com/censync/hh-python/v1.0.0/docs/images/sui-c.png) | <code>0xeab3150efcb34ff74930d8f3d491be1090<ins><b>1</b></ins>0a39e4d380d<ins><b>c</b></ins>7737aff5c72a0b6b2</code> | `ZSJ-7BK` |

What a forger pays, by calculation. One current GPU tries about 1.4 billion addresses per second;
a try against hh also has to compute the stretched base digest, which leaves about 680 000 tries
per second. The figures are the expected search times on one such GPU for a typical picture
([SECURITY.md](https://github.com/censync/hh-cpp/blob/v1.0.0/docs/SECURITY.md) of hh-cpp has the
reasoning).

| The forged address has to match | Tries | One GPU |
|---|---|---|
| the first 4 and the last 4 hex digits | 2^32 | 3 seconds |
| the first 6 and the last 6 hex digits | 2^48 | 2.3 days |
| the first 8 and the last 8 hex digits | 2^64 | 420 years |
| the universal picture, with two cells allowed to differ | 2^52, stretched | 210 years |
| the universal picture, in every cell | 2^68, stretched | 14 million years |
| the ends of the text and the picture | the product of the two | |
| the keyed picture | cannot be searched: without the key the picture cannot be computed | |

A lookalike of the text is cheap, which is why address poisoning works. A lookalike of the
picture is not, and the two costs multiply. A picture that looks the same is still strong
evidence rather than proof; the tag or the full address is the check that is certain.

## Properties

- **Two modes.** A *universal* picture is the same for everyone and is what two people compare. A
  *keyed* picture is computed with a 32-byte secret of the wallet: an attacker who does not hold
  the key cannot compute, and therefore cannot grind, a lookalike. Inside an application keyed
  pictures are the default.
- **Deterministic to the byte.** Integer arithmetic only. The same input gives the same pixels
  and the same PNG, BMP and JPEG bytes as hh-cpp, on every platform and every interpreter.
- **Frozen.** The algorithm has no version and never changes; a picture that a user has learned
  stays the same for ever. Library releases follow SemVer and never alter the output.
- **No dependencies.** `dependencies = []`: no Pillow, no NumPy, not even `zlib`. SHA-256, HMAC
  and PBKDF2 come from `hashlib` and `hmac`; deflate, PNG, BMP, the baseline JPEG encoder and the
  rasteriser are part of the library.
- **Fast enough for an interpreter.** The rasteriser works on whole rows of samples with integer
  bit sets instead of looping over samples: on a desktop core a 128-pixel picture takes one to
  two milliseconds, its PNG three to four, the base digest two to four.
- **Made for colour vision deficiency.** About one man in twelve does not see colours the way the
  rest do. The four colours were chosen for them: the palette was searched so that every pair stays
  apart under simulated protanopia, deuteranopia and tritanopia, and every colour keeps a contrast
  of 3:1 on white and on dark surfaces. Shape carries most of the information, so a picture still
  works in greyscale (the measurements are in
  [docs/design](https://github.com/censync/hh-cpp/tree/v1.0.0/docs/design) of hh-cpp).
- **Pixels, not pictures.** The library returns RGBA bytes and encoded files; making a Tkinter,
  Qt or Pillow image of them is one line in the host.
- **Typed.** Type hints throughout and a `py.typed` marker.

## Quick start

```sh
pip install humanized-hash
```

```python
from humanized_hash import BaseDigest, Fingerprint

digest = BaseDigest.of_hex("0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed")    # slow: cache it
fingerprint = Fingerprint.universal(digest)      # or Fingerprint.keyed(digest, key)
image = fingerprint.render(128)                  # 128 x 128 RGBA pixels, image.rgba

png: bytes = image.encode_png()                  # or image.save("address.png")
tag: str = fingerprint.tag                       # "TKSPVH", shown as TKS-PVH
```

A keyed picture needs the 32-byte secret of the wallet:

```python
from humanized_hash import SecretKey

with SecretKey(key_bytes) as key:                # wiped when the block ends
    private = Fingerprint.keyed(digest, key)
```

`BaseDigest.of` takes the bytes of an address, `of_hex` their hexadecimal spelling and `of_text` an
address that exists only as text. `BaseDigest.from_bytes` computes nothing: it restores a digest
that was cached as `bytes(digest)`.

Invalid values raise `HhError`, a `ValueError` whose `code` is the error of the specification;
arguments of the wrong type raise `TypeError`.

A decision (confirming a payment, verifying a pasted address) should be backed by a picture of at
least 64 device-independent pixels, better 96, next to the picture it is compared with. Smaller
pictures are for recognition in lists. See
[docs/INTEGRATION.md](https://github.com/censync/hh-python/blob/v1.0.0/docs/INTEGRATION.md) for
web backends, Tkinter, Pillow and Qt, caching and key handling, and
[SECURITY.md](https://github.com/censync/hh-cpp/blob/v1.0.0/docs/SECURITY.md) of hh-cpp for what
a picture proves and what it does not.

## A complete program

A command line program that writes the picture of an address to a PNG file and prints its tag.

```sh
mkdir hh-example && cd hh-example
python3 -m venv .venv && . .venv/bin/activate
pip install humanized-hash
```

`main.py`:

```python
from humanized_hash import BaseDigest, Fingerprint

digest = BaseDigest.of_hex("0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed")
fingerprint = Fingerprint.universal(digest)
fingerprint.render(128).save("address.png")
tag = fingerprint.tag
print(f"{tag[:3]}-{tag[3:]}")
```

`python main.py` prints `TKS-PVH` and writes `address.png`, byte for byte the file
`testdata/golden/evm-1-universal-128.png` that every implementation reproduces.

## Command line

The package installs the command `humanized-hash`; `python -m humanized_hash` is the same tool.

```sh
humanized-hash 0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed --out address.png
humanized-hash --text bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4 --size 256 --out address.png
humanized-hash <hex> --key <64 hex digits> --shape round --frame double --out private.png
```

It takes the options of `hh_cli` of hh-cpp and prints the same values. It is a demonstration and
a test tool: a real host never takes a key from the command line.

## Testing

Python 3.9 or newer; nothing to install.

```sh
python -m unittest discover -s tests -t .        # every test, against the source tree
tools/crosscheck.sh <path to hh_cli of hh-cpp>   # differential test against hh-cpp
python tools/bench.py                            # what each step costs on this machine
python -m build                                  # sdist and wheel (needs the build package)
```

The tests reproduce every record of the golden vectors, compare the rasteriser with a
per-sample transcription of the specification and decode every encoder's output. The rules for
patches are in
[CONTRIBUTING.md](https://github.com/censync/hh-python/blob/v1.0.0/CONTRIBUTING.md), the releases
in [CHANGELOG.md](https://github.com/censync/hh-python/blob/v1.0.0/CHANGELOG.md).

## License

MIT, see [LICENSE](https://github.com/censync/hh-python/blob/v1.0.0/LICENSE).
Copyright (c) 2026 Dmitry Mandrika. [CenSync](https://censync.com)
