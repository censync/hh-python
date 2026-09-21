# Contributing to hh-python

hh-python is the Python implementation of Humanized Hash (`hh`). The C++17 repository hh-cpp is
the reference: it owns `docs/SPEC.md`, `docs/SECURITY.md` and the canonical golden vectors. This
repository carries a byte-identical copy of the vectors in `testdata/` and records the hh-cpp
release and the file hashes in `testdata/SOURCE`. The port follows `SPEC.md`, not the C++ source.

Bug reports and patches are welcome: open an issue or a pull request. Security problems are
reported privately, as `docs/SECURITY.md` of hh-cpp describes.

## The algorithm is frozen

Output is byte-identical with hh-cpp. A mismatch against the vectors is a bug here, never a reason
to change the vectors. The algorithm has no version and never changes; what the specification
leaves open (API shape, error texts, performance) may evolve under SemVer.

hh is a standalone library. Nothing here names a particular host application.

## Dependencies and license

- `dependencies = []`. The package imports the standard library only, and of it only what every
  build has: `hashlib`, `hmac`, `binascii`, `struct`, `math.isqrt` and the like. It does not import
  `zlib`, which is optional in CPython builds: deflate, Adler-32, PNG, BMP, the JPEG encoder and
  the rasteriser are written here. SHA-256, HMAC, PBKDF2 and CRC-32 are the standard library's.
- No third-party packages anywhere, including the tests and the tools. Tests use `unittest` only;
  they may cross-check against `zlib` and may use floating point to measure error.
- The build backend is setuptools; `build` is the only package needed to make a release. No
  linter, formatter or type checker is required to work on the code, and none is configured.
- License: MIT (`LICENSE`); contributions are accepted under it.

## Style

- Everything is English: code, comments, docstrings, documentation, commit messages. No emoji.
- PEP 8 with 100 columns, double quotes, type hints on every function, a docstring on every
  public object. Public names live in `humanized_hash/__init__.py` and `__all__`; every other
  module starts with an underscore.
- Python 3.9 is the oldest supported version: `from __future__ import annotations` in every
  module, `typing.Optional` and `typing.Union` where an annotation is evaluated at run time, no
  `match`, no `int.bit_count`, no `zip(strict=...)`.
- Comments explain the code and cite the section of the specification or the standard
  (RFC 1951, ITU-T T.81).

## Library rules (src/humanized_hash)

- Integer arithmetic only: no `float`, no `/`, no `round`, nothing from `math` but `isqrt`.
  Python integers are unbounded; mask where the specification works modulo 2^32.
- Invalid values raise `HhError` (a `ValueError`) with the `ErrorCode` of the specification, in
  the order of checks the specification gives; arguments of the wrong type raise `TypeError`.
- Buffers that held key material are overwritten before release, as far as Python allows; the
  documentation says where it does not.
- A faster path must equal the per-sample definition exactly. `tests/reference.py` is that
  definition; `tests/test_raster.py` compares the two.
- `tests/test_package.py` enforces the rules that a program can check.

## Build and test

- `python -m unittest discover -s tests -t .` runs every test against the source tree; it must
  pass with `python -W error -X dev` on every supported version. `HH_TEST_INSTALLED=1` tests the
  installed package instead, `HH_TESTDATA_DIR` points at the vectors.
- `tools/crosscheck.sh <hh_cli>` runs the differential test against hh-cpp: generated cases and
  the hand-made cases of `tools/edge-cases.txt`, a file of bytes that every implementation
  carries in the same copy; `python tools/bench.py` times every step. The tools may use floating
  point, the library never.
- `tools/update-vectors.sh <hh-cpp checkout>` refreshes `testdata/` and `testdata/SOURCE`; never
  edit those files by hand.
- `python -m build` makes the source distribution and the wheel. The version lives in
  `src/humanized_hash/_version.py` and nowhere else.

## Commits

Atomic, imperative, lower case, for example "add the baseline jpeg encoder". Every commit passes
the tests.
