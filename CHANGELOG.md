# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Each release names the hh-cpp release
its golden vectors were copied from. The algorithm itself is frozen and has no version: no
release changes a fingerprint, a pixel or an encoded byte.

## [1.1.0] - 2026-09-25

Golden vectors: hh-cpp v1.1.0.

### Changed

- The mode no longer restricts the look: universal fingerprints take every frame style that fits
  the shape (`ROUNDED`, `CHAMFERED`, `DOUBLE`, `THICK`, `BRACKETS`, `TICKS`, `GAPS`), which 1.0.0
  refused with `INVALID_FRAME`. A style that does not fit the shape is still `INVALID_FRAME`, and
  its message names the shape alone. `AUTOMATIC` is unchanged: universal pictures stay frameless
  and keyed square pictures keep their rounded corners, so every picture 1.0.0 rendered is the
  same to the byte.
- The golden vectors are those of hh-cpp v1.1.0: they gain renders and size sweeps of universal
  fingerprints with every style, and the error records now test the shape alone.
- `humanized-hash --generate` picks the frame of a case by the shape alone, so cases without a
  key get every style too. The cases of a seed differ from those of 1.0.0 in the frame of such
  cases only, and they are the cases that the tool of hh-kotlin 1.1.0 prints for the seed.
- The docstrings of `FrameStyle`, `RenderOptions.frame` and `ErrorCode.INVALID_FRAME`, the README
  and `docs/INTEGRATION.md` describe the rule; links to the documents of hh-cpp point at v1.1.0.

## [1.0.0] - 2026-09-21

The first release. Golden vectors: hh-cpp v1.0.0.

### Added

- Public API in `humanized_hash` (type hints, `py.typed`, docstrings): `BaseDigest.of`, `of_hex`
  and `of_text` compute the base digest of bytes, hexadecimal or text, and `from_bytes` restores
  a stored one; `SecretKey`, a context manager that wipes its copy of the key, with `closed` and
  a key check value that stays readable after the key is closed; universal and keyed
  `Fingerprint` with layout and six-character tag, and `from_bytes` for a fingerprint computed
  elsewhere; `RenderOptions` with square and round shapes, keyed-mode frame markers, any
  background colour and transparency, frame transparency and a WCAG contrast measure; `Image`
  with RGBA pixels, PNG, BMP and JPEG encoders and `save`. `HhError`, a `ValueError`, carries the
  `ErrorCode` of the specification; arguments of the wrong type raise `TypeError`. Values are
  immutable, hashable and picklable with every protocol; a key is neither picklable nor
  printable, and neither is the buffer that holds it.
- A rasteriser that evaluates whole rows of samples as integer bit sets, exact to the per-sample
  definition of the specification; fixed-Huffman deflate, PNG, BMP and a baseline JPEG encoder
  written in the library; Adler-32; PBKDF2 over `hashlib.sha256` for interpreters without
  OpenSSL. SHA-256, HMAC, PBKDF2 and CRC-32 come from the standard library. No dependencies;
  integer arithmetic only.
- The command `humanized-hash` (`python -m humanized_hash`) with the options of `hh_cli` of
  hh-cpp, and with `--batch`, which follows the batch format of `hh_cli` to the letter, and
  `--generate` for differential tests.
- Tests with `unittest`: known-answer tests (FIPS 180-4, RFC 4231, RFC 7914, CRC-32 and Adler-32
  check values); the golden vectors and golden files of hh-cpp; the rasteriser against a
  per-sample transcription of the specification for every size from 16 to 96 and samples up to
  1024; the deflate stream against a literal transcription of its matching rule; decoders for
  PNG (`zlib`), BMP and baseline JPEG; error order, API and robustness tests; source rules
  (no floating point, standard library only, documented API).
- `tools/crosscheck.sh`: differential test against `hh_cli` of hh-cpp with pseudo-random cases
  and the hand-made cases of `tools/edge-cases.txt`. `tools/update-vectors.sh` copies the vectors
  and writes `testdata/SOURCE`. `tools/bench.py` times every step.
- Packaging with setuptools: `humanized-hash` on PyPI, CPython 3.9 to 3.14 and PyPy 3.10; the
  source distribution carries the tests and the vectors, the wheel the package only.

[1.1.0]: https://github.com/censync/hh-python/releases/tag/v1.1.0
[1.0.0]: https://github.com/censync/hh-python/releases/tag/v1.0.0
