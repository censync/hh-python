"""Reproduces every record of ``testdata/vectors.tsv``, the golden vectors of hh-cpp.

The file is a byte-identical copy (SPEC.md section 15); a mismatch is a bug in this
implementation, never in the vectors.
"""

from __future__ import annotations

import hashlib
import re
import unittest

from humanized_hash import BaseDigest, Fingerprint, HhError, Image, Mode, SecretKey
from humanized_hash import _derive

from .support import options_of, pattern, read_bytes, records, render_case, vector_input


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cells_text(fp: Fingerprint) -> str:
    return "".join(f"{int(cell.figure)}{cell.colour}" for cell in fp.layout.cells)


class VectorsTest(unittest.TestCase):
    def test_the_file_is_present_and_complete(self) -> None:
        minimum = "D 20, H 20, K 8, C 20, R 80, E 25, G 20, W 15, I 14, F 16"
        for kind, count in (pair.split() for pair in minimum.split(", ")):
            self.assertGreaterEqual(len(records(kind)), int(count), kind)

    def test_the_copy_is_what_source_records(self) -> None:
        # testdata/SOURCE names the hh-cpp release the files came from and their SHA-256.
        lines = read_bytes("SOURCE").decode("utf-8").split("\n")
        self.assertTrue(
            any(re.fullmatch(r"tag: v\d+\.\d+\.\d+", line) for line in lines),
            "testdata/SOURCE names no release tag",
        )
        self.assertTrue(any(re.fullmatch(r"commit: [0-9a-f]{40}", line) for line in lines))
        hashes = [line.split("  ") for line in lines if re.fullmatch(r"[0-9a-f]{64}  \S+", line)]
        self.assertEqual(1 + len(records("G")), len(hashes))
        for digest, name in hashes:
            self.assertEqual(digest, sha256(read_bytes(*name.split("/"))), name)

    def test_derivation_records(self) -> None:
        for r in records("D"):
            with self.subTest(r[1]):
                self.assertEqual(16, len(r))
                data = vector_input(r[3])
                text = r[2] == "text"
                digest = BaseDigest.of_text(data.decode("utf-8")) if text else BaseDigest.of(data)
                if text:
                    self.assertEqual(digest, BaseDigest.of_text(data))
                kind = _derive.KIND_TEXT if text else _derive.KIND_BINARY
                if r[5] != "-":
                    self.assertEqual(r[5], (_derive.m1_header(kind, len(data)) + data).hex())
                self.assertEqual(r[6], _derive.d0(kind, data).hex())
                self.assertEqual(r[7], digest.hex())
                self.assertEqual(r[8], _derive.m2(bytes(digest)).hex())
                universal = Fingerprint.universal(digest)
                self.assertEqual(Mode.UNIVERSAL, universal.mode)
                self.assertEqual(r[9], universal.hex())
                self.assertEqual(r[12], cells_text(universal))
                self.assertEqual(r[14], universal.tag)
                if r[4] == "-":
                    self.assertEqual(["-", "-", "-", "-"], [r[10], r[11], r[13], r[15]])
                    continue
                with SecretKey(bytes.fromhex(r[4])) as key:
                    self.assertEqual(r[11], key.check_value.hex())
                    keyed = Fingerprint.keyed(digest, key)
                self.assertEqual(Mode.KEYED, keyed.mode)
                self.assertEqual(r[10], keyed.hex())
                self.assertEqual(r[13], cells_text(keyed))
                self.assertEqual(r[15], keyed.tag)

    def test_hexadecimal_input_records(self) -> None:
        for r in records("H"):
            with self.subTest(r[1]):
                text = bytes.fromhex(r[2]).decode("utf-8")
                if re.fullmatch(r"[0-9a-f]+", r[3]):
                    self.assertEqual(BaseDigest.of(bytes.fromhex(r[3])), BaseDigest.of_hex(text))
                else:
                    with self.assertRaises(HhError) as raised:
                        BaseDigest.of_hex(text)
                    self.assertEqual(r[3], raised.exception.code.spec_name)

    def test_key_records(self) -> None:
        for r in records("K"):
            with self.subTest(r[1]):
                raw = b"" if r[2] == "-" else bytes.fromhex(r[2])
                if re.fullmatch(r"[0-9a-f]{8}", r[3]):
                    with SecretKey(raw) as key:
                        self.assertEqual(r[3], key.check_value.hex())
                else:
                    with self.assertRaises(HhError) as raised:
                        SecretKey(raw)
                    self.assertEqual(r[3], raised.exception.code.spec_name)

    def test_contrast_records(self) -> None:
        for r in records("C"):
            with self.subTest(r[1]):
                options = options_of("square", "automatic", r[2], r[3])
                report = options.measure_contrast(int(r[4], 16))
                self.assertEqual(int(r[5]), report.figures_x100)
                self.assertEqual(int(r[6]), report.frame_x100)

    def test_render_records(self) -> None:
        for r in records("R"):
            with self.subTest(r[1]):
                self.assertEqual(15, len(r))
                fp, size, options = render_case(r[2:9])
                image = fp.render(size, options)
                matte = int(r[10], 16)
                self.assertEqual((size, size), image.size)
                self.assertEqual(r[11], sha256(image.rgba), "rgba")
                self.assertEqual(r[12], sha256(image.encode_png()), "png")
                self.assertEqual(r[13], sha256(image.encode_bmp(matte)), "bmp")
                self.assertEqual(r[14], sha256(image.encode_jpeg(int(r[9]), matte)), "jpeg")

    def test_render_error_records(self) -> None:
        for r in records("E"):
            with self.subTest(r[1]):
                fp, size, options = render_case(r[2:9])
                with self.assertRaises(HhError) as raised:
                    fp.render(size, options)
                self.assertEqual(r[9], raised.exception.code.spec_name)

    def test_golden_files(self) -> None:
        for r in records("G"):
            with self.subTest(r[1]):
                fp, size, options = render_case(r[3:10])
                self.assertEqual(read_bytes("golden", r[2]), fp.render(size, options).encode_png())

    def test_size_sweep_records(self) -> None:
        for r in records("W"):
            with self.subTest(r[1]):
                self.assertEqual(11, len(r))
                fp, first, options = render_case([r[2], r[3], r[8], r[4], r[5], r[6], r[7]])
                hasher = hashlib.sha256()
                for size in range(first, int(r[9]) + 1):
                    hasher.update(fp.render(size, options).rgba)
                self.assertEqual(r[10], hasher.hexdigest())

    def test_image_records(self) -> None:
        for r in records("I"):
            with self.subTest(r[1]):
                self.assertEqual(11, len(r))
                width, height = int(r[2]), int(r[3])
                image = Image(width, height, pattern(r[4], width, height))
                matte = int(r[6], 16)
                self.assertEqual(r[7], sha256(image.rgba), "rgba")
                self.assertEqual(r[8], sha256(image.encode_png()), "png")
                self.assertEqual(r[9], sha256(image.encode_bmp(matte)), "bmp")
                self.assertEqual(r[10], sha256(image.encode_jpeg(int(r[5]), matte)), "jpeg")

    def test_failure_records(self) -> None:
        for r in records("F"):
            with self.subTest(r[1]):
                with self.assertRaises(HhError) as raised:
                    if r[2] == "digest":
                        data = vector_input(r[4])
                        if r[3] == "text":
                            BaseDigest.of_text(data.decode("utf-8"))
                        else:
                            BaseDigest.of(data)
                    elif r[2] == "jpeg":
                        Image(8, 8, pattern("flat:ffffffff", 8, 8)).encode_jpeg(int(r[3]))
                    elif r[2] == "image":
                        Image(int(r[3]), int(r[4]), b"\x7f" * int(r[5]))
                    else:
                        self.fail(f"unknown operation {r[2]}")
                self.assertEqual(r[-1], raised.exception.code.spec_name)


if __name__ == "__main__":
    unittest.main()
