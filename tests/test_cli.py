"""The command line tool: single renders, --batch and --generate."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from typing import List, Tuple

import humanized_hash
from humanized_hash import FrameStyle
from humanized_hash._cli import main

from .support import read_bytes

ADDRESS = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
DIGEST = "e212927148fcf76f6669c244a0db08bdd4f36dc50a378f6a1a3fe472807e7852"
KEY = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
KEYED = "26ea8171aab23c8e1bf7c23417d33d6dba81d881af70edd2b0675348e080b478"


def run(*arguments: str) -> Tuple[int, str, str]:
    """The exit status, standard output and standard error of one run."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            status = main(list(arguments))
        except SystemExit as stop:  # argparse reports wrong usage this way
            status = stop.code if isinstance(stop.code, int) else 1
    return status, out.getvalue(), err.getvalue()


class SingleRenderTest(unittest.TestCase):
    def test_the_values_are_printed_as_hh_cli_prints_them(self) -> None:
        status, out, err = run(ADDRESS)
        self.assertEqual((0, ""), (status, err))
        self.assertEqual(
            [
                "mode         universal",
                "base digest  " + DIGEST,
                "fingerprint  " + DIGEST,
                "tag          TKS-PVH",
            ],
            out.split("\n")[:4],
        )
        cells = out.split("\n")[4:8]
        self.assertTrue(cells[0].startswith("cells        "))
        self.assertTrue(all(len(line) == 13 + 12 for line in cells), cells)
        self.assertEqual("", out.split("\n")[8])

    def test_a_keyed_picture_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "private.png")
            status, out, _ = run(ADDRESS, "--key", KEY, "--out", path)
            self.assertEqual(0, status)
            self.assertIn("mode         keyed\n", out)
            self.assertIn("fingerprint  " + KEYED + "\n", out)
            self.assertIn("key check    6a5955cf\n", out)
            with open(path, "rb") as file:
                written = file.read()
            self.assertEqual(read_bytes("golden", "evm-1-keyed-128.png"), written)
            self.assertIn(f"wrote        {path} ({len(written)} bytes)\n", out)

    def test_options_reach_the_renderer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "look.png")
            arguments = [
                "fb6916095ca1df60bb79ce92ce3ea74c37c5d359", "--key", KEY, "--size", "128",
                "--shape", "round", "--frame", "gaps", "--out", path,
            ]
            self.assertEqual(0, run(*arguments)[0])
            with open(path, "rb") as file:
                written = file.read()
            self.assertEqual(read_bytes("golden", "evm-2-keyed-128-round-gaps.png"), written)

    def test_the_format_follows_the_extension_unless_it_is_given(self) -> None:
        magic = {"a.png": b"\x89PNG", "a.bmp": b"BM", "a.jpg": b"\xff\xd8", "a.jpeg": b"\xff\xd8"}
        with tempfile.TemporaryDirectory() as directory:
            for name, start in magic.items():
                path = os.path.join(directory, name)
                self.assertEqual(0, run(ADDRESS, "--size", "32", "--out", path)[0])
                with open(path, "rb") as file:
                    self.assertTrue(file.read().startswith(start), name)
            path = os.path.join(directory, "a.rgba")
            self.assertEqual(0, run(ADDRESS, "--size", "32", "--out", path)[0])
            self.assertEqual(32 * 32 * 4, os.path.getsize(path))
            path = os.path.join(directory, "b.png")
            self.assertEqual(0, run(ADDRESS, "--format", "bmp", "--out", path)[0])
            with open(path, "rb") as file:
                self.assertEqual(b"BM", file.read(2))

    def test_only_the_lower_case_extensions_of_hh_cli_choose_a_format(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for name in ("a.BMP", "a.Jpg", "a.JPEG", "a.RGBA", "a.gif", "a.bmp.txt", "abmp", "a"):
                path = os.path.join(directory, name)
                self.assertEqual(0, run(ADDRESS, "--size", "32", "--out", path)[0])
                with open(path, "rb") as file:
                    self.assertEqual(b"\x89PNG", file.read(4), name)
            # hh_cli looks at names of more than four characters only.
            before = os.getcwd()
            os.chdir(directory)
            try:
                self.assertEqual(0, run(ADDRESS, "--size", "32", "--out", ".bmp")[0])
                self.assertEqual(0, run(ADDRESS, "--size", "32", "--out", "b.bmp")[0])
            finally:
                os.chdir(before)
            self.assertEqual(b"\x89PNG", open_bytes(os.path.join(directory, ".bmp"))[:4])
            self.assertEqual(b"BM", open_bytes(os.path.join(directory, "b.bmp"))[:2])

    def test_text_input(self) -> None:
        status, out, _ = run("--text", "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4")
        self.assertEqual(0, status)
        self.assertIn("dc705192e4a205d8c403ae7693290df45f09cec04116ad38f6140f349392548f", out)

    def test_errors_are_named_and_exit_with_1(self) -> None:
        for arguments, name in (
            (["0xzz"], "invalid_hex"),
            ([ADDRESS, "--size", "15"], "invalid_size"),
            ([ADDRESS, "--frame", "ticks"], "invalid_frame"),
            ([ADDRESS, "--key", "00" * 32], "invalid_key"),
            ([ADDRESS, "--key", "xyz"], "invalid_key"),
            ([ADDRESS, "--background", "7a96c5ff"], "low_contrast"),
            ([ADDRESS, "--format", "jpeg", "--quality", "49"], "invalid_quality"),
            (["--text", ""], "empty_input"),
        ):
            status, out, err = run(*arguments)
            self.assertEqual((1, ""), (status, out), arguments)
            self.assertTrue(err.startswith(f"error: {name}: "), err)

    def test_wrong_usage_exits_with_2(self) -> None:
        for arguments in (
            [],
            ["--size", "64"],
            [ADDRESS, "--shape", "oval"],
            [ADDRESS, "--frame-alpha", "256"],
            [ADDRESS, "--frame-alpha", "-1"],
            [ADDRESS, "--frame-alpha", "+5"],
            [ADDRESS, "--frame-alpha", "2_5"],
            [ADDRESS, "--size", "3_2"],
            [ADDRESS, "--size", "+64"],
            [ADDRESS, "--size", "-64"],
            [ADDRESS, "--size", " 64"],
            [ADDRESS, "--size", "64 "],
            [ADDRESS, "--size", ""],
            [ADDRESS, "--size", "\u0666\u0664"],
            [ADDRESS, "--size", "\uff16\uff14"],
            [ADDRESS, "--size", "12345678901"],
            [ADDRESS, "--quality", "9_2"],
            [ADDRESS, "--quality", "+92"],
            [ADDRESS, "--quality", "92.0"],
            [ADDRESS, "--background", "ffffff"],
            [ADDRESS, "--matte", "12345"],
            [ADDRESS, "--format", "gif"],
            [ADDRESS, "extra"],
            ["--batch", "only-one"],
        ):
            self.assertEqual(2, run(*arguments)[0], arguments)

    def test_numbers_are_digits_of_any_magnitude(self) -> None:
        self.assertEqual(0, run(ADDRESS, "--size", "0000000064", "--frame-alpha", "0255")[0])
        for size in ("2147483648", "4294967312", "9999999999"):
            status, _, err = run(ADDRESS, "--size", size)
            self.assertEqual(1, status)
            self.assertTrue(err.startswith("error: invalid_size: "), err)
        status, _, err = run(ADDRESS, "--format", "jpeg", "--quality", "4294967388")
        self.assertEqual(1, status)
        self.assertTrue(err.startswith("error: invalid_quality: "), err)
        status, _, err = run(ADDRESS, "--size", "3_2")
        self.assertIn("humanized-hash: error: argument --size: '3_2' is not", err)

    def test_the_module_runs_as_a_program(self) -> None:
        environment = dict(os.environ)
        package_parent = os.path.dirname(os.path.dirname(os.path.abspath(humanized_hash.__file__)))
        environment["PYTHONPATH"] = package_parent
        done = subprocess.run(
            [sys.executable, "-m", "humanized_hash", ADDRESS],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual((0, b""), (done.returncode, done.stderr))
        self.assertIn(b"tag          TKS-PVH", done.stdout)


class BatchTest(unittest.TestCase):
    def batch(self, lines: List[str]) -> Tuple[List[str], str]:
        return self.batch_of_bytes(("\n".join(lines) + "\n").encode("utf-8"))

    def batch_of_bytes(self, content: bytes) -> Tuple[List[str], str]:
        with tempfile.TemporaryDirectory() as directory:
            cases = os.path.join(directory, "cases.txt")
            with open(cases, "wb") as file:
                file.write(content)
            self.directory = os.path.join(directory, "deeper", "out")
            status, out, err = run("--batch", cases, self.directory)
            self.assertEqual((0, ""), (status, err))
            self.written = {
                name: open_bytes(os.path.join(self.directory, name))
                for name in sorted(os.listdir(self.directory))
            }
            return out.split("\n")[:-1], err

    def test_cases_print_their_values_and_write_their_files(self) -> None:
        tail = "128 square automatic ffffffff 255 png 92 ffffff"
        lines, _ = self.batch(
            [
                "# a comment",
                "",
                f"hex {ADDRESS} - {tail}",
                f"hex {ADDRESS} {KEY} {tail}",
                "text 626331717735303864367165 - 64 round plain 00000000 100 rgba 92 ffffff",
                f"hex {ADDRESS} - 32 square none ffffffff 255 jpeg 80 000000",
                f"hex {ADDRESS} - 32 square none ffffffff 255 bmp 80 000000",
            ]
        )
        self.assertEqual(f"1\tok\t{DIGEST}\t{DIGEST}\tTKSPVH\t-", lines[0])
        self.assertEqual(f"2\tok\t{DIGEST}\t{KEYED}\tQA0XH0\t6a5955cf", lines[1])
        self.assertTrue(lines[2].startswith("3\tok\t"))
        self.assertEqual(
            ["case-1.png", "case-2.png", "case-3.rgba", "case-4.jpeg", "case-5.bmp"],
            list(self.written),
        )
        for name, golden in (("case-1.png", "evm-1-universal"), ("case-2.png", "evm-1-keyed")):
            self.assertEqual(read_bytes("golden", golden + "-128.png"), self.written[name])
        self.assertEqual(64 * 64 * 4, len(self.written["case-3.rgba"]))

    def test_errors_and_bad_cases_are_named_in_the_order_of_hh_cli(self) -> None:
        good = f"hex {ADDRESS} - 128 square automatic ffffffff 255 png 92 ffffff"
        lines, _ = self.batch(
            [
                good.replace(ADDRESS, "0xzz"),
                good.replace(" - ", " 00ff "),
                good.replace(" - ", " nothex "),
                good.replace(" 128 ", " 15 "),
                good.replace("automatic", "ticks"),
                good.replace("ffffffff", "7a96c5ff"),
                good.replace("png 92", "jpeg 49"),
                good.replace("png", "gif"),
                # The input is looked at before the key, the key before the size, and so on.
                "hex 0xzz 00ff 15 square ticks 7a96c5ff 255 gif 49 ffffff",
                "hex 0x12 00ff 15 square ticks 7a96c5ff 255 gif 49 ffffff",
                f"hex 0x12 {KEY} 15 round rounded 7a96c5ff 255 gif 49 ffffff",
                f"hex 0x12 {KEY} 16 round rounded 7a96c5ff 255 gif 49 ffffff",
                f"hex 0x12 {KEY} 16 round thick 7a96c5ff 255 gif 49 ffffff",
                f"hex 0x12 {KEY} 16 round thick ffffffff 255 gif 49 ffffff",
                f"hex 0x12 {KEY} 18 round thick ffffffff 255 gif 49 ffffff",
                f"hex 0x12 {KEY} 18 round thick ffffffff 255 jpeg 49 ffffff",
                "binary 00 - 128 square automatic ffffffff 255 png 92 ffffff",
                "text zz - 128 square automatic ffffffff 255 png 92 ffffff",
                good.replace("square", "oval"),
                good.replace("automatic", "fancy"),
                good.replace("ffffffff", "ffffff"),
                good.replace(" 255 ", " 256 "),
                good.replace(" 255 ", " x "),
                good.replace("92 ffffff", "92 fffff"),
                good.replace(" 128 ", " big "),
                "hex 00",
                "?",
            ]
        )
        names = [line.split("\t")[1] for line in lines]
        numbers = [line.split("\t")[0] for line in lines]
        self.assertEqual([str(n + 1) for n in range(len(lines))], numbers)
        self.assertEqual(
            [
                "invalid_hex", "invalid_key", "invalid_key", "invalid_size", "invalid_frame",
                "low_contrast", "invalid_quality", "invalid_argument",
                "invalid_hex", "invalid_key", "invalid_size", "invalid_frame", "low_contrast",
                "invalid_size", "invalid_argument", "invalid_quality",
                "bad_case", "bad_case", "bad_case", "bad_case", "bad_case", "bad_case", "bad_case",
                "bad_case", "bad_case", "bad_case", "bad_case",
            ],
            names,
        )
        self.assertEqual({}, self.written)

    def test_the_format_of_a_case_is_strict(self) -> None:
        good = f"hex {ADDRESS} - 128 square automatic ffffffff 255 png 92 ffffff"
        ok = f"ok\t{DIGEST}\t{DIGEST}\tTKSPVH\t-"
        cases = [
            (good, ok),
            (good + " extra", "bad_case"),
            (good + " # comment", "bad_case"),
            ("\t  " + good.replace(" ", " \t ") + "\t ", ok),
            (" # not a comment", "bad_case"),
            ("  ", "bad_case"),
            # Only the ASCII space and the tab separate fields.
            (good.replace(" - ", " -\u00a0"), "bad_case"),
            (good.replace(" - ", "\u00a0-\u00a0"), "bad_case"),
            (good.replace(" 128 ", " 128\x1f"), "bad_case"),
            (good.replace(" 128 ", " 128\x0b"), "bad_case"),
            (good.replace(" 128 ", " 128\x0c"), "bad_case"),
            (good.replace(" 128 ", " 128\u2003"), "bad_case"),
            (good.replace(" 128 ", " 128\x85"), "bad_case"),
            # Numbers are 1 to 10 ASCII digits without a sign.
            (good.replace(" 128 ", " 0000000128 "), ok),
            (good.replace(" 128 ", " 00000000128 "), "bad_case"),
            (good.replace(" 128 ", " +128 "), "bad_case"),
            (good.replace(" 128 ", " -128 "), "bad_case"),
            (good.replace(" 128 ", " 1_28 "), "bad_case"),
            (good.replace(" 128 ", " 128.0 "), "bad_case"),
            (good.replace(" 128 ", " 0x80 "), "bad_case"),
            (good.replace(" 128 ", " \u0661\u0662\u0668 "), "bad_case"),
            (good.replace(" 128 ", " \uff11\uff12\uff18 "), "bad_case"),
            (good.replace(" 128 ", " 2147483648 "), "invalid_size"),
            (good.replace(" 128 ", " 4294967424 "), "invalid_size"),
            (good.replace(" 128 ", " 9999999999 "), "invalid_size"),
            (good.replace(" 128 ", " 10000000000 "), "bad_case"),
            (good.replace(" 255 ", " 0255 "), ok),
            (good.replace(" 255 ", " 256 "), "bad_case"),
            (good.replace(" 255 ", " 4294967551 "), "bad_case"),
            (good.replace(" 255 ", " +255 "), "bad_case"),
            (good.replace(" 255 ", " 2_5 "), "bad_case"),
            (good.replace("png 92", "jpeg 4294967388"), "invalid_quality"),
            (good.replace("png 92", "jpeg 9_2"), "bad_case"),
            (good.replace("png 92", "png 9999999999"), ok),
            (good.replace("png 92", "png 0"), ok),
            (good.replace("png 92", "png -1"), "bad_case"),
            # Names are written as the specification writes them.
            (good.replace("hex", "HEX"), "bad_case"),
            (good.replace("square", "Square"), "bad_case"),
            (good.replace("png", "PNG"), "invalid_argument"),
            (good.replace("png", "jpg"), "invalid_argument"),
            (good.replace("ffffffff", "FFFFFFFF"), ok),
            (good.replace("ffffffff", "0xffffff"), "bad_case"),
            (good.replace(ADDRESS, "0x\u0661\u0662"), "invalid_hex"),
            (good.replace(ADDRESS, "0x12\u00a0"), "invalid_hex"),
        ]
        lines, _ = self.batch([line for line, _ in cases])
        expected = [f"{n + 1}\t{answer}" for n, (_, answer) in enumerate(cases)]
        self.assertEqual(expected, lines)

    def test_the_file_is_bytes(self) -> None:
        good = f"hex {ADDRESS} - 16 square automatic ffffffff 255 rgba 92 ffffff".encode("ascii")
        text = b"text ff00fe - 16 square automatic ffffffff 255 rgba 92 ffffff"
        content = b"\n".join(
            [
                b"# \xff\xfe is not UTF-8, and a comment",
                b"\xff\xfe",
                good + b"\r",
                b"\r",
                b"#\r",
                good + b"\r\r",
                good.replace(b"hex", b"hex\xa0"),
                good.replace(b" - ", b" \xc2\xa0 "),
                good.replace(b"0x5a", b"0x\xff"),
                text,
                good + b" \r",
                good,
            ]
        )
        lines, _ = self.batch_of_bytes(content)
        ok = f"ok\t{DIGEST}\t{DIGEST}\tTKSPVH\t-"
        self.assertEqual(
            [
                "1\tbad_case",
                f"2\t{ok}",
                "3\tbad_case",
                "4\tbad_case",
                "5\tinvalid_key",
                "6\tinvalid_hex",
                "7\tok\t" + lines[6][5:],
                f"8\t{ok}",
                f"9\t{ok}",
            ],
            lines,
        )
        # The bytes of a text case reach the library as they are, valid UTF-8 or not.
        digest = humanized_hash.BaseDigest.of_text(b"\xff\x00\xfe")
        self.assertEqual(f"7\tok\t{digest.hex()}\t{digest.hex()}", lines[6][: 5 + 64 + 1 + 64])
        self.assertEqual(
            ["case-2.rgba", "case-7.rgba", "case-8.rgba", "case-9.rgba"], list(self.written)
        )

    def test_a_directory_that_cannot_be_made_is_reported_at_the_first_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cases = os.path.join(directory, "cases.txt")
            with open(cases, "w", encoding="ascii", newline="\n") as file:
                file.write("hex 0xzz - 16 square automatic ffffffff 255 png 92 ffffff\n")
                file.write(f"hex {ADDRESS} - 16 square automatic ffffffff 255 png 92 ffffff\n")
            status, out, err = run("--batch", cases, os.path.join(cases, "out"))
            self.assertEqual(1, status)
            self.assertTrue(out.startswith("1\tinvalid_hex\n2\tok\t"), out)
            self.assertFalse(out.endswith("\n"), "hh_cli stops before it ends the line")
            self.assertIn("cannot write into", err)

    def test_a_missing_file_is_reported(self) -> None:
        status, out, err = run("--batch", os.path.join(os.sep, "no", "such", "file"), "unused")
        self.assertEqual((1, ""), (status, out))
        self.assertIn("cannot read", err)


class GenerateTest(unittest.TestCase):
    def test_the_cases_of_a_seed_never_change(self) -> None:
        # The same lines come from the tool of hh-kotlin, whose generator this one follows.
        status, out, _ = run("--generate", "5", "1")
        self.assertEqual(0, status)
        self.assertEqual(
            [
                "# 5 cases, seed 1",
                "hex 0x5a4abadf7f242c4473b70ef6223d6d87a8f6d012aa45d3395ab33e4f7b4c2ed0b4"
                "1499cd65394c"
                " 3befbeddf028ff1c344cb6a5520851766a8a35884edbfade6060552b69f1d125"
                " 119 square brackets 2147feb6 150 png 78 256c93",
                "hex 0x6c24c74ecb661fdaa7e07b7ccf24fca2597642f9"
                " bc14b9f3c279c77ee8a82ae75b4088093b03ff7c5648b38ca9b71590fb9dcd35"
                " 225 round gaps 000000ff 102 jpeg 86 4901e0",
                "hex 0x6d9c2bea7654422f54ca064bedae"
                " - 115 square automatic e6dae765 102 bmp 93 821bf4",
                "hex 0x - 129 square brackets ffffffff 211 bmp 97 988255",
                "hex 0xa483cab641e5e98c405045d21ab6c61fdf727c73e9ddba383fb02988eb3285c5a7bdad03749c"
                " - 41 square plain 00000000 48 bmp 86 6cc14a",
                "",
            ],
            out.split("\n"),
        )

    def test_generated_cases_are_cases(self) -> None:
        _, out, _ = run("--generate", "300", "-12345")
        lines = out.split("\n")[1:-1]
        self.assertEqual(300, len(lines))
        kinds = set()
        universal_frames = set()
        for line in lines:
            fields = line.split(" ")
            self.assertEqual(11, len(fields), line)
            kinds.add(fields[0])
            if fields[2] == "-":
                universal_frames.add(fields[5])
        self.assertEqual({"hex", "text"}, kinds)
        # The frame of a case depends on the shape alone: cases without a key get every style.
        self.assertEqual({style.value for style in FrameStyle}, universal_frames)
        self.assertNotEqual(out, run("--generate", "300", "12345")[1])

    def test_a_generated_batch_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cases = os.path.join(directory, "cases.txt")
            with open(cases, "w", encoding="utf-8", newline="\n") as file:
                file.write(run("--generate", "60", "3")[1])
            status, out, err = run("--batch", cases, os.path.join(directory, "out"))
            self.assertEqual((0, ""), (status, err))
            lines = out.split("\n")[:-1]
            self.assertEqual(60, len(lines))
            rendered = [line for line in lines if "\tok\t" in line]
            self.assertEqual(len(rendered), len(os.listdir(os.path.join(directory, "out"))))
            self.assertGreater(len(rendered), 20)
            self.assertNotIn("bad_case", out)


def open_bytes(path: str) -> bytes:
    with open(path, "rb") as file:
        return file.read()


if __name__ == "__main__":
    unittest.main()
