"""Canonicalisation and derivation: SPEC.md sections 3 and 4.

SHA-256 (FIPS 180-4), HMAC (RFC 2104) and PBKDF2 (RFC 8018) come from the standard library.
"""

from __future__ import annotations

import hashlib
import hmac
import re

from ._errors import ErrorCode, HhError

DST = b"HumanizedHash"
STRETCH_SALT = b"HumanizedHash/stretch"
STRETCH_ITERATIONS = 16384
MAX_INPUT_SIZE = 1048576

KIND_BINARY = 0x00
KIND_TEXT = 0x01

_STAGE_DIGEST = 0x01
_STAGE_KEYED = 0x02
_STAGE_KCV = 0x03

_NOT_HEX = re.compile(r"[^0-9a-fA-F]")
_IPAD = bytes(b ^ 0x36 for b in range(256))
_OPAD = bytes(b ^ 0x5C for b in range(256))


def m1_header(kind: int, length: int) -> bytes:
    """``M1`` without the data: ``DST || 00 || 01 || kind || u32be(length)``."""
    return DST + bytes((0x00, _STAGE_DIGEST, kind)) + length.to_bytes(4, "big")


def d0(kind: int, data: bytes) -> bytes:
    """``d0 = SHA-256(M1)``."""
    hasher = hashlib.sha256(m1_header(kind, len(data)))
    hasher.update(data)
    return hasher.digest()


def pbkdf2_hmac_sha256(password: bytes, salt: bytes, iterations: int, length: int) -> bytes:
    """PBKDF2-HMAC-SHA-256 (RFC 8018 section 5.2) on top of ``hashlib.sha256``.

    ``hashlib.pbkdf2_hmac`` needs an interpreter built with OpenSSL; this is what runs without it.
    """
    if len(password) > 64:
        password = hashlib.sha256(password).digest()
    padded = password.ljust(64, b"\x00")
    inner = hashlib.sha256(padded.translate(_IPAD))
    outer = hashlib.sha256(padded.translate(_OPAD))

    def prf(message: bytes) -> bytes:
        first = inner.copy()
        first.update(message)
        second = outer.copy()
        second.update(first.digest())
        return second.digest()

    out = bytearray()
    block = 0
    while len(out) < length:
        block += 1
        u = prf(salt + block.to_bytes(4, "big"))
        total = int.from_bytes(u, "big")
        for _ in range(iterations - 1):
            u = prf(u)
            total ^= int.from_bytes(u, "big")
        out += total.to_bytes(32, "big")
    return bytes(out[:length])


def stretch(digest0: bytes) -> bytes:
    """``s = PBKDF2-HMAC-SHA-256(d0, "HumanizedHash/stretch", 16384, 32)``."""
    native = getattr(hashlib, "pbkdf2_hmac", None)
    if native is not None:
        return bytes(native("sha256", digest0, STRETCH_SALT, STRETCH_ITERATIONS, 32))
    return pbkdf2_hmac_sha256(digest0, STRETCH_SALT, STRETCH_ITERATIONS, 32)


def base_digest(kind: int, data: bytes) -> bytes:
    """The base digest ``s`` of an input; checks the length limits of section 3."""
    if len(data) == 0:
        raise HhError(ErrorCode.EMPTY_INPUT, "the input has no bytes")
    if len(data) > MAX_INPUT_SIZE:
        raise HhError(
            ErrorCode.INPUT_TOO_LARGE, f"the input is longer than {MAX_INPUT_SIZE} bytes"
        )
    return stretch(d0(kind, data))


def m2(s: bytes) -> bytes:
    """``M2 = DST || 00 || 02 || s``."""
    return DST + bytes((0x00, _STAGE_KEYED)) + s


def keyed_fingerprint(key: bytearray, s: bytes) -> bytes:
    """``HMAC-SHA-256(K, M2)``."""
    return hmac.digest(key, m2(s), "sha256")


def key_check_value(key: bytearray) -> bytes:
    """The first 4 bytes of ``HMAC-SHA-256(K, DST || 00 || 03)``."""
    return hmac.digest(key, DST + bytes((0x00, _STAGE_KCV)), "sha256")[:4]


def decode_hex(text: str) -> bytes:
    """Decodes hexadecimal text as section 3 defines it: the syntax first, then the length."""
    digits = text[2:] if text[:2] in ("0x", "0X") else text
    if not digits or len(digits) % 2 != 0 or _NOT_HEX.search(digits):
        raise HhError(
            ErrorCode.INVALID_HEX,
            "not an even, non-zero number of hexadecimal digits with an optional 0x",
        )
    if len(digits) // 2 > MAX_INPUT_SIZE:
        raise HhError(
            ErrorCode.INPUT_TOO_LARGE, f"the input is longer than {MAX_INPUT_SIZE} bytes"
        )
    return bytes.fromhex(digits)


def encode_text(text: str) -> bytes:
    """The UTF-8 bytes of a text input.

    Lone surrogates have no UTF-8 encoding and are refused instead of being replaced, after the
    length check; for that check a lone surrogate counts as three bytes (section 3).
    """
    # Every code point gives at least one byte, so an overlong text is refused unencoded.
    if len(text) > MAX_INPUT_SIZE:
        raise HhError(
            ErrorCode.INPUT_TOO_LARGE, f"the input is longer than {MAX_INPUT_SIZE} bytes"
        )
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError as error:
        # "surrogatepass" writes a lone surrogate as the three bytes of its code point.
        if len(text.encode("utf-8", "surrogatepass")) > MAX_INPUT_SIZE:
            raise HhError(
                ErrorCode.INPUT_TOO_LARGE, f"the input is longer than {MAX_INPUT_SIZE} bytes"
            ) from None
        raise HhError(
            ErrorCode.INVALID_ARGUMENT,
            f"the text holds a lone surrogate at position {error.start}",
        ) from None
