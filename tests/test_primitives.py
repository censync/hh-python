"""Known-answer tests of the primitives.

SHA-256, HMAC and PBKDF2 come from the standard library and CRC-32 from ``binascii``; their
vectors guard against an interpreter whose primitives are not what the specification names.
PBKDF2 for interpreters without OpenSSL and Adler-32 are written in the library.
"""

from __future__ import annotations

import binascii
import hashlib
import hmac
import random
import unittest

from humanized_hash import _derive, _png

try:
    import zlib
except ImportError:  # zlib is optional in CPython builds
    zlib = None


class Sha256Test(unittest.TestCase):
    # FIPS 180-4 and the NIST example values.
    VECTORS = [
        (b"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
        (b"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
        (
            b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
            "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
        ),
        (
            b"abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmn"
            b"hijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu",
            "cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1",
        ),
        (b"a" * 1000000, "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"),
    ]

    def test_fips_180_4(self) -> None:
        for message, expected in self.VECTORS:
            self.assertEqual(expected, hashlib.sha256(message).hexdigest())


class HmacTest(unittest.TestCase):
    # RFC 4231, test cases 1 to 7: key, data, HMAC-SHA-256 (case 5 is truncated to 128 bits).
    VECTORS = [
        (
            "0b" * 20,
            b"Hi There".hex(),
            "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7",
        ),
        (
            b"Jefe".hex(),
            b"what do ya want for nothing?".hex(),
            "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843",
        ),
        (
            "aa" * 20,
            "dd" * 50,
            "773ea91e36800e46854db8ebd09181a72959098b3ef8c122d9635514ced565fe",
        ),
        (
            "0102030405060708090a0b0c0d0e0f10111213141516171819",
            "cd" * 50,
            "82558a389a443c0ea4cc819899f2083a85f0faa3e578f8077a2e3ff46729665b",
        ),
        ("0c" * 20, b"Test With Truncation".hex(), "a3b6167473100ee06e0c796c2955552b"),
        (
            "aa" * 131,
            b"Test Using Larger Than Block-Size Key - Hash Key First".hex(),
            "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54",
        ),
        (
            "aa" * 131,
            (
                b"This is a test using a larger than block-size key and a larger than "
                b"block-size data. The key needs to be hashed before being used by the "
                b"HMAC algorithm."
            ).hex(),
            "9b09ffa71b942fcb27635fbcd5b0e944bfdc63644f0713938a7f51535c3a35e2",
        ),
    ]

    def test_rfc_4231(self) -> None:
        for key, data, expected in self.VECTORS:
            tag = hmac.digest(bytes.fromhex(key), bytes.fromhex(data), "sha256").hex()
            self.assertEqual(expected, tag[: len(expected)])

    def test_the_key_may_be_a_bytearray(self) -> None:
        # SecretKey keeps its bytes in a bytearray so that they can be wiped.
        key = bytes(range(32))
        expected = hmac.digest(key, b"message", "sha256")
        self.assertEqual(expected, hmac.digest(bytearray(key), b"message", "sha256"))


class Pbkdf2Test(unittest.TestCase):
    # RFC 7914 section 11: PBKDF2-HMAC-SHA-256 with dkLen 64.
    VECTORS = [
        (
            b"passwd",
            b"salt",
            1,
            "55ac046e56e3089fec1691c22544b605f94185216dde0465e68b9d57c20dacbc"
            "49ca9cccf179b645991664b39d77ef317c71b845b1e30bd509112041d3a19783",
        ),
        (
            b"Password",
            b"NaCl",
            80000,
            "4ddcd8f60b98be21830cee5ef22701f9641a4418d04c0414aeff08876b34ab56"
            "a1d425a1225833549adb841b51c9b3176a272bdebba1d078478f62b397f33c8d",
        ),
    ]

    def test_rfc_7914_with_the_implementation_of_the_library(self) -> None:
        for password, salt, iterations, expected in self.VECTORS:
            derived = _derive.pbkdf2_hmac_sha256(password, salt, iterations, 64)
            self.assertEqual(expected, derived.hex())

    @unittest.skipUnless(hasattr(hashlib, "pbkdf2_hmac"), "this interpreter has no OpenSSL")
    def test_rfc_7914_with_the_standard_library(self) -> None:
        for password, salt, iterations, expected in self.VECTORS:
            derived = hashlib.pbkdf2_hmac("sha256", password, salt, iterations, 64)
            self.assertEqual(expected, derived.hex())

    def test_both_implementations_stretch_alike(self) -> None:
        generator = random.Random(7)
        for _ in range(3):
            d0 = generator.randbytes(32)
            expected = _derive.pbkdf2_hmac_sha256(d0, _derive.STRETCH_SALT, 16384, 32)
            self.assertEqual(expected, _derive.stretch(d0))

    def test_lengths_and_long_passwords(self) -> None:
        # A password longer than a block is hashed first (RFC 2104); any length can be asked for.
        long_password = b"p" * 100
        for length in (1, 31, 32, 33, 65):
            derived = _derive.pbkdf2_hmac_sha256(long_password, b"s", 3, length)
            self.assertEqual(length, len(derived))
            if hasattr(hashlib, "pbkdf2_hmac"):
                native = hashlib.pbkdf2_hmac("sha256", long_password, b"s", 3, length)
                self.assertEqual(native, derived)


class ChecksumTest(unittest.TestCase):
    def test_crc_32_check_value(self) -> None:
        self.assertEqual(0xCBF43926, binascii.crc32(b"123456789"))
        self.assertEqual(0, binascii.crc32(b""))

    def test_adler_32_check_values(self) -> None:
        self.assertEqual(1, _png.adler32(b""))
        self.assertEqual(0x11E60398, _png.adler32(b"Wikipedia"))
        self.assertEqual(0x091E01DE, _png.adler32(b"123456789"))
        self.assertEqual(0x9F51D664, _png.adler32(b"\xff" * 20000))

    @unittest.skipIf(zlib is None, "this interpreter has no zlib")
    def test_adler_32_agrees_with_zlib(self) -> None:
        generator = random.Random(9)
        for length in (1, 2, 5551, 5552, 5553, 65535, 65536, 65537, 200001):
            data = generator.randbytes(length)
            self.assertEqual(zlib.adler32(data), _png.adler32(data), length)
        self.assertEqual(zlib.adler32(b"\xff" * 3000000), _png.adler32(b"\xff" * 3000000))


if __name__ == "__main__":
    unittest.main()
