"""The public API: values, errors and the order in which errors are detected."""

from __future__ import annotations

import array
import copy
import dataclasses
import os
import pathlib
import pickle
import tempfile
import traceback
import unittest
from typing import Any, Callable
from unittest import mock

import humanized_hash as hh
from humanized_hash import (
    BaseDigest,
    Cell,
    ContrastReport,
    ErrorCode,
    Figure,
    Fingerprint,
    FrameStyle,
    HhError,
    Image,
    Layout,
    Mode,
    RenderOptions,
    SecretKey,
    Shape,
)

ADDRESS = "5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
ADDRESS_DIGEST = "e212927148fcf76f6669c244a0db08bdd4f36dc50a378f6a1a3fe472807e7852"
KEYED = "26ea8171aab23c8e1bf7c23417d33d6dba81d881af70edd2b0675348e080b478"
TEST_KEY = bytes(range(32))
LIMIT = 1048576


def released_view() -> memoryview:
    view = memoryview(bytes(32))
    view.release()
    return view


class ApiTestCase(unittest.TestCase):
    def assert_error(
        self, code: ErrorCode, function: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> HhError:
        with self.assertRaises(HhError) as raised:
            function(*args, **kwargs)
        self.assertIs(code, raised.exception.code)
        self.assertTrue(str(raised.exception))
        return raised.exception


class BaseDigestTest(ApiTestCase):
    def test_every_spelling_of_an_address_gives_one_digest(self) -> None:
        expected = BaseDigest.of(bytes.fromhex(ADDRESS))
        self.assertEqual(ADDRESS_DIGEST, expected.hex())
        for form in (ADDRESS, "0x" + ADDRESS, "0X" + ADDRESS.upper(), ADDRESS.lower()):
            self.assertEqual(expected, BaseDigest.of_hex(form), form)
            self.assertEqual(hash(expected), hash(BaseDigest.of_hex(form)))

    def test_bytes_like_inputs_are_one_input(self) -> None:
        raw = bytes.fromhex(ADDRESS)
        expected = BaseDigest.of(raw)
        self.assertEqual(expected, BaseDigest.of(bytearray(raw)))
        self.assertEqual(expected, BaseDigest.of(memoryview(raw)))

    def test_text_and_binary_inputs_are_separated(self) -> None:
        text = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
        digest = BaseDigest.of_text(text)
        self.assertNotEqual(digest, BaseDigest.of(text.encode("ascii")))
        self.assertEqual(
            "dc705192e4a205d8c403ae7693290df45f09cec04116ad38f6140f349392548f", digest.hex()
        )
        self.assertEqual(digest, BaseDigest.of_text(text.encode("ascii")))

    def test_text_is_utf_8_without_normalisation(self) -> None:
        # U+10348 is four bytes; a precomposed and a decomposed e-acute are different inputs.
        self.assertEqual(
            BaseDigest.of_text("\U00010348"), BaseDigest.of_text(b"\xf0\x90\x8d\x88")
        )
        self.assertNotEqual(BaseDigest.of_text("\u00e9"), BaseDigest.of_text("e\u0301"))
        # Bytes are taken verbatim, even if they are not UTF-8.
        self.assertEqual(32, len(bytes(BaseDigest.of_text(b"\xff\xfe"))))

    def test_invalid_inputs(self) -> None:
        self.assert_error(ErrorCode.EMPTY_INPUT, BaseDigest.of, b"")
        self.assert_error(ErrorCode.EMPTY_INPUT, BaseDigest.of_text, "")
        self.assert_error(ErrorCode.EMPTY_INPUT, BaseDigest.of_text, b"")
        self.assert_error(ErrorCode.INPUT_TOO_LARGE, BaseDigest.of, bytes(LIMIT + 1))
        self.assert_error(ErrorCode.INPUT_TOO_LARGE, BaseDigest.of_text, bytes(LIMIT + 1))
        # Among them Arabic-Indic and full-width digits, which are digits but not hexadecimal.
        bad_strings = ["", "0x", "0xzz", "abc", " ab", "ab ", "ab\n", "a b", "0x0x12"]
        bad_strings += ["\u0661\u0662", "\uff11\uff12"]
        for bad in bad_strings:
            self.assert_error(ErrorCode.INVALID_HEX, BaseDigest.of_hex, bad)
        self.assert_error(ErrorCode.INVALID_DIGEST, BaseDigest.from_bytes, bytes(31))
        self.assert_error(ErrorCode.INVALID_DIGEST, BaseDigest.from_bytes, bytes(33))
        self.assert_error(ErrorCode.INVALID_ARGUMENT, BaseDigest.of_text, "a\ud800b")
        error = self.assert_error(ErrorCode.INVALID_HEX, BaseDigest.of_hex, "x")
        self.assertIsInstance(error, ValueError)

    def test_the_largest_input_is_accepted(self) -> None:
        self.assertEqual(
            "1f4bcfa790e7d10ff543d082d4eb7f7cfe5981102f3f181cb83b486a3d16c7cb",
            BaseDigest.of(b"\xab" * LIMIT).hex(),
        )

    def test_wrong_types_are_type_errors(self) -> None:
        for call in (
            lambda: BaseDigest.of("abcd"),
            lambda: BaseDigest.of(None),
            lambda: BaseDigest.of_hex(b"abcd"),
            lambda: BaseDigest.of_text(12),
            lambda: BaseDigest.from_bytes("00" * 32),
            lambda: BaseDigest(bytes(32)),
            lambda: Fingerprint(bytes(32), Mode.KEYED),
            lambda: Fingerprint.universal(bytes(32)),
            lambda: Fingerprint.keyed(BaseDigest.from_bytes(bytes(32)), TEST_KEY),
            lambda: Fingerprint.from_bytes("00" * 32, Mode.KEYED),
            lambda: Fingerprint.from_bytes(bytes(32), True),
            lambda: Fingerprint.from_bytes(bytes(32), 1.0),
            lambda: Fingerprint.from_bytes(bytes(32), "keyed"),
            lambda: Fingerprint.from_bytes(bytes(32), None),
            lambda: SecretKey("k" * 32),
            lambda: SecretKey(list(TEST_KEY)),
            lambda: Image(1, 1, 4),
            lambda: Image(1, 1, [0, 0, 0, 0]),
            lambda: Image(1, 1, "abcd"),
            lambda: Image(1, 1, None),
            # A released view is no bytes-like object any more.
            lambda: BaseDigest.of(released_view()),
            lambda: BaseDigest.of_text(released_view()),
            lambda: BaseDigest.from_bytes(released_view()),
            lambda: Fingerprint.from_bytes(released_view(), Mode.KEYED),
            lambda: SecretKey(released_view()),
            lambda: Image(2, 4, released_view()),
            lambda: RenderOptions(shape="round"),
            lambda: RenderOptions(frame="plain"),
            lambda: RenderOptions(background="ffffff"),
            lambda: RenderOptions(background_alpha=1.0),
            lambda: RenderOptions(frame_alpha=True),
        ):
            self.assertRaises(TypeError, call)

    def test_text_is_checked_for_length_then_for_surrogates(self) -> None:
        # Every code point is at least one byte, so an overlong text is refused unencoded.
        self.assert_error(ErrorCode.INPUT_TOO_LARGE, BaseDigest.of_text, "a" * (LIMIT + 1))
        self.assert_error(ErrorCode.INPUT_TOO_LARGE, BaseDigest.of_text, "a" * LIMIT + "\ud800")
        # 1 048 576 code points of two bytes each are too many bytes, though not too many points.
        self.assert_error(ErrorCode.INPUT_TOO_LARGE, BaseDigest.of_text, "\u00e9" * LIMIT)
        # For the length check a lone surrogate counts as three bytes.
        self.assert_error(
            ErrorCode.INPUT_TOO_LARGE, BaseDigest.of_text, "a" * (LIMIT - 2) + chr(0xD800)
        )
        self.assert_error(
            ErrorCode.INVALID_ARGUMENT, BaseDigest.of_text, "a" * (LIMIT - 3) + chr(0xD800)
        )
        long_and_bad = "\u00e9" * (LIMIT - 1) + "\udc00"
        self.assert_error(ErrorCode.INPUT_TOO_LARGE, BaseDigest.of_text, long_and_bad)
        # A str is a sequence of code points: two surrogate code points are not a pair.
        pair = chr(0xD800) + chr(0xDC00)
        self.assertEqual(2, len(pair))
        for bad in ("\ud800", "\udc00", "a\ud800", "\udc00\ud800", pair, "x\udbffy"):
            self.assert_error(ErrorCode.INVALID_ARGUMENT, BaseDigest.of_text, bad)
        BaseDigest.of_text("\U0010ffff")

    def test_hexadecimal_syntax_is_checked_before_its_length(self) -> None:
        too_long = "a" * (2 * (LIMIT + 1))
        self.assert_error(ErrorCode.INPUT_TOO_LARGE, BaseDigest.of_hex, too_long)
        self.assert_error(ErrorCode.INPUT_TOO_LARGE, BaseDigest.of_hex, "0x" + too_long)
        self.assert_error(ErrorCode.INVALID_HEX, BaseDigest.of_hex, too_long[:-1] + "g")
        self.assert_error(ErrorCode.INVALID_HEX, BaseDigest.of_hex, too_long[:-1])

    def test_a_stored_digest_is_restored_not_computed(self) -> None:
        # from_bytes takes its 32 bytes as the digest; of() hashes and stretches them.
        raw = bytes.fromhex("eab3150efcb34ff74930d8f3d491be109070a39e4d380de7737aff5c72a0b6b2")
        self.assertEqual("B6P65H", Fingerprint.universal(BaseDigest.of(raw)).tag)
        self.assertEqual("B6P65H", Fingerprint.universal(BaseDigest.of_hex(raw.hex())).tag)
        self.assertEqual(raw, bytes(BaseDigest.from_bytes(raw)))
        self.assertNotEqual(BaseDigest.of(raw), BaseDigest.from_bytes(raw))
        computing = [name for name in vars(BaseDigest) if name.startswith(("of", "from_"))]
        self.assertEqual(["of", "of_hex", "of_text", "from_bytes"], computing)
        self.assertTrue((BaseDigest.from_bytes.__doc__ or "").startswith("Not for an address"))

    def test_a_digest_is_an_immutable_value(self) -> None:
        digest = BaseDigest.from_bytes(bytes.fromhex(ADDRESS_DIGEST))
        self.assertEqual(bytes.fromhex(ADDRESS_DIGEST), bytes(digest))
        self.assertEqual(digest, eval(repr(digest), {"BaseDigest": BaseDigest}))
        self.assertNotEqual(digest, bytes(digest))
        self.assertEqual(digest, pickle.loads(pickle.dumps(digest)))
        self.assertEqual(digest, copy.deepcopy(digest))
        self.assertEqual(1, len({digest, BaseDigest.from_bytes(bytearray(bytes(digest)))}))
        with self.assertRaises(AttributeError):
            digest._bytes = bytes(32)
        with self.assertRaises(AttributeError):
            digest.other = 1
        with self.assertRaises(AttributeError):
            del digest._bytes
        self.assertEqual(ADDRESS_DIGEST, digest.hex())
        source = bytearray(bytes(digest))
        restored = BaseDigest.from_bytes(source)
        source[0] ^= 0xFF  # the digest holds a copy
        self.assertEqual(digest, restored)


class SecretKeyTest(ApiTestCase):
    def test_keys_are_checked(self) -> None:
        self.assert_error(ErrorCode.INVALID_KEY, SecretKey, b"\x01" * 31)
        self.assert_error(ErrorCode.INVALID_KEY, SecretKey, b"\x01" * 33)
        self.assert_error(ErrorCode.INVALID_KEY, SecretKey, bytes(32))
        self.assert_error(ErrorCode.INVALID_KEY, SecretKey, b"")
        with SecretKey(TEST_KEY) as key:
            self.assertEqual("6a5955cf", key.check_value.hex())
        with SecretKey(bytearray(TEST_KEY)) as key:
            self.assertEqual("6a5955cf", key.check_value.hex())
        with SecretKey(memoryview(TEST_KEY)) as key:
            self.assertEqual("6a5955cf", key.check_value.hex())

    def test_any_view_of_32_bytes_is_a_key(self) -> None:
        digest = BaseDigest.from_bytes(bytes.fromhex(ADDRESS_DIGEST))
        spread = bytearray(64)
        spread[::2] = TEST_KEY
        words = array.array("I", TEST_KEY)  # eight items of four bytes
        self.assertEqual(4, words.itemsize)
        for view in (memoryview(spread)[::2], memoryview(TEST_KEY + b"xx")[:32], memoryview(words)):
            with SecretKey(view) as key:
                self.assertEqual("6a5955cf", key.check_value.hex())
                self.assertEqual(KEYED, Fingerprint.keyed(digest, key).hex())
        self.assert_error(ErrorCode.INVALID_KEY, SecretKey, memoryview(spread)[::4])
        self.assert_error(ErrorCode.INVALID_KEY, SecretKey, memoryview(bytes(64))[::2])

    def test_a_key_lets_go_of_the_buffer_it_was_given(self) -> None:
        # A bytearray with a live view cannot be resized; clear() fails with BufferError.
        for content in (bytes(TEST_KEY), bytes(32), bytes(31), bytes(33)):
            source = bytearray(content)
            try:
                key = SecretKey(source)
            except HhError as error:
                self.assertIs(ErrorCode.INVALID_KEY, error.code)
            else:
                key.close()
            source.clear()
            self.assertEqual(bytearray(), source)
        source = bytearray(64)
        self.assert_error(ErrorCode.INVALID_KEY, SecretKey, memoryview(source)[::2])
        source.clear()

    def test_a_key_copies_its_bytes_and_is_unusable_once_closed(self) -> None:
        source = bytearray(TEST_KEY)
        key = SecretKey(source)
        source[:] = bytes(32)  # the caller wipes its own buffer; the key is not affected
        self.assertEqual("6a5955cf", key.check_value.hex())
        digest = BaseDigest.from_bytes(bytes.fromhex(ADDRESS_DIGEST))
        self.assertEqual(KEYED, Fingerprint.keyed(digest, key).hex())
        self.assertFalse(key.closed)
        buffer = key._bytes
        key.close()
        key.close()
        self.assertTrue(key.closed)
        self.assertEqual(bytearray(32), buffer)
        self.assert_error(ErrorCode.INVALID_KEY, Fingerprint.keyed, digest, key)
        self.assert_error(ErrorCode.INVALID_KEY, key.__enter__)
        self.assert_error(ErrorCode.INVALID_KEY, key._use, lambda raw: bytes(raw))

    def test_the_check_value_is_public_and_outlives_the_key(self) -> None:
        key = SecretKey(TEST_KEY)
        before = key.check_value
        self.assertEqual("6a5955cf", before.hex())
        key.close()
        self.assertTrue(key.closed)
        self.assertEqual(before, key.check_value)
        self.assertIsInstance(key.check_value, bytes)
        with self.assertRaises(AttributeError):
            key.check_value = b"1234"
        with self.assertRaises(AttributeError):
            key.closed = False

    def test_the_context_manager_wipes_even_after_an_error(self) -> None:
        with self.assertRaises(RuntimeError):
            with SecretKey(TEST_KEY) as key:
                raise RuntimeError("the host failed")
        self.assertTrue(key.closed)
        self.assertEqual(bytearray(32), key._bytes)

    def test_key_material_never_shows_and_never_travels(self) -> None:
        key = SecretKey(TEST_KEY)
        self.assertEqual("SecretKey(***)", repr(key))
        self.assertEqual("SecretKey(***)", str(key))
        self.assertRaises(TypeError, pickle.dumps, key)
        self.assertRaises(TypeError, copy.copy, key)
        self.assertRaises(TypeError, copy.deepcopy, key)
        self.assertFalse(hasattr(key, "__dict__"))
        key.close()
        self.assertEqual("SecretKey(***)", repr(key))

    def test_the_buffer_of_a_key_never_prints_its_bytes(self) -> None:
        key = SecretKey(TEST_KEY)
        buffer = key._bytes
        self.assertEqual(TEST_KEY, bytes(buffer))
        for shown in (repr(buffer), str(buffer), f"{buffer}", "%s %r" % (buffer, buffer)):
            self.assertNotIn("x01", shown)
            self.assertIn("<key bytes>", shown)
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
            self.assertRaises(TypeError, pickle.dumps, buffer, protocol)
        self.assertRaises(TypeError, copy.copy, buffer)
        self.assertRaises(TypeError, copy.deepcopy, buffer)

    def test_a_traceback_with_local_variables_shows_no_key(self) -> None:
        secret = bytes(range(0xA0, 0xC0))
        digest = BaseDigest.from_bytes(bytes.fromhex(ADDRESS_DIGEST))

        def failing(raw: Any) -> bytes:
            raise RuntimeError("the host failed")

        def failing_function() -> None:
            with SecretKey(bytearray(secret)) as key:
                key._use(failing)

        def failing_hmac() -> None:
            with SecretKey(bytearray(secret)) as key:
                with mock.patch("hmac.digest", side_effect=RuntimeError("no HMAC")):
                    Fingerprint.keyed(digest, key)

        def failing_constructor() -> None:
            SecretKey(bytearray(secret + b"\xc0"))

        package = os.path.dirname(os.path.abspath(hh.__file__))
        for call, frames in (
            (failing_function, ["_use"]),
            (failing_hmac, ["keyed", "_use", "keyed_fingerprint"]),
            (failing_constructor, ["__init__"]),
        ):
            try:
                call()
            except (RuntimeError, HhError) as error:
                report = traceback.TracebackException.from_exception(error, capture_locals=True)
            # The frames of the library; the variables of the host are its own to guard.
            report.stack[:] = [
                frame for frame in report.stack if os.path.dirname(frame.filename) == package
            ]
            self.assertEqual(frames, [frame.name for frame in report.stack])
            text = "".join(report.format())
            self.assertIn("SecretKey(***)", text)
            self.assertNotIn("xa1", text, call.__name__)
            if call is failing_hmac:
                self.assertIn("key = <key bytes>", text)

    def test_a_key_that_failed_to_build_is_closed(self) -> None:
        try:
            SecretKey(bytes(32))
        except HhError as error:
            self.assertIs(ErrorCode.INVALID_KEY, error.code)
        key = object.__new__(SecretKey)
        self.assertRaises(HhError, key.__init__, bytes(33))
        self.assertTrue(key.closed)
        self.assertEqual(bytearray(32), key._bytes)
        self.assert_error(ErrorCode.INVALID_KEY, Fingerprint.keyed, BaseDigest.of(b"a"), key)


class FingerprintTest(ApiTestCase):
    def test_fingerprints_compare_by_bytes_and_mode(self) -> None:
        raw = bytes.fromhex(ADDRESS_DIGEST)
        universal = Fingerprint.universal(BaseDigest.from_bytes(raw))
        self.assertIs(Mode.UNIVERSAL, universal.mode)
        self.assertEqual("TKSPVH", universal.tag)
        self.assertEqual(raw, bytes(universal))
        self.assertEqual(universal, Fingerprint.from_bytes(raw, Mode.UNIVERSAL))
        self.assertEqual(universal, Fingerprint.from_bytes(raw, 1))
        self.assertEqual(hash(universal), hash(Fingerprint.from_bytes(raw, Mode.UNIVERSAL)))
        self.assertNotEqual(universal, Fingerprint.from_bytes(raw, Mode.KEYED))
        self.assertNotEqual(universal, raw)
        self.assertEqual(universal, pickle.loads(pickle.dumps(universal)))
        self.assertEqual("<Fingerprint universal TKSPVH>", repr(universal))
        with self.assertRaises(AttributeError):
            universal._mode = Mode.KEYED
        with self.assertRaises(AttributeError):
            del universal._bytes
        with self.assertRaises(AttributeError):
            universal.other = 1
        self.assertIs(Mode.UNIVERSAL, universal.mode)

    def test_the_mode_is_a_mode_or_its_integer(self) -> None:
        raw = bytes.fromhex(ADDRESS_DIGEST)
        for mode in (Mode.KEYED, 2, int(Mode.KEYED)):
            self.assertIs(Mode.KEYED, Fingerprint.from_bytes(raw, mode).mode)
        for mode in (True, False, 1.0, 2.0, "2", b"\x02", None, (2,)):
            self.assertRaises(TypeError, Fingerprint.from_bytes, raw, mode)
        for mode in (0, 3, -1, 2**70):
            self.assert_error(ErrorCode.INVALID_FINGERPRINT, Fingerprint.from_bytes, raw, mode)

    def test_imports_are_checked(self) -> None:
        bad = ((bytes(16), Mode.KEYED), (bytes(64), Mode.KEYED), (bytes(32), 0), (bytes(32), 3))
        for raw, mode in bad:
            self.assert_error(ErrorCode.INVALID_FINGERPRINT, Fingerprint.from_bytes, raw, mode)

    def test_layout_describes_the_cells(self) -> None:
        raw = bytearray(32)
        for i in range(16):
            raw[i] = ((i // 2) << 5) | ((i % 4) << 3) | 7
        layout = Fingerprint.from_bytes(raw, Mode.KEYED).layout
        figures = [
            Figure.NONE, Figure.NONE, Figure.SQUARE, Figure.CIRCLE,
            Figure.TRIANGLE_UP, Figure.TRIANGLE_RIGHT, Figure.TRIANGLE_DOWN, Figure.TRIANGLE_LEFT,
        ]
        self.assertIs(Mode.KEYED, layout.mode)
        self.assertEqual(16, len(layout.cells))
        for i, cell in enumerate(layout.cells):
            self.assertIs(figures[i // 2], cell.figure, i)
            self.assertEqual(0 if figures[i // 2] is Figure.NONE else i % 4, cell.colour, i)
        self.assertEqual((0x7A96C5, 0x890AF0, 0xC10445, 0xD48200), layout.palette)
        self.assertEqual(0x808080, layout.frame_colour)
        self.assertEqual(layout, Fingerprint.from_bytes(raw, Mode.KEYED).layout)
        self.assertEqual(hash(layout), hash(Fingerprint.from_bytes(raw, 2).layout))
        self.assertEqual(Cell(Figure.SQUARE, 0), layout.cells[4])
        self.assertIsInstance(layout, Layout)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            layout.cells[0].colour = 1

    def test_the_tag_reads_bytes_16_to_19(self) -> None:
        for word, expected in ((0, "000000"), (0xFFFFFFFF, "ZZZZZZ"), (4, "000001"), (3, "000000")):
            raw = bytes(16) + word.to_bytes(4, "big") + bytes(12)
            self.assertEqual(expected, Fingerprint.from_bytes(raw, Mode.UNIVERSAL).tag)
        # Bytes 20..31 and the low bits of bytes 0..15 are not used.
        a = Fingerprint.from_bytes(bytes(32), Mode.UNIVERSAL)
        unused = bytes([7] * 16) + bytes(3) + b"\x03" + bytes([255] * 12)
        b = Fingerprint.from_bytes(unused, Mode.UNIVERSAL)
        self.assertEqual(a.tag, b.tag)
        self.assertEqual(a.layout, b.layout)
        self.assertEqual(a.render(32), b.render(32))


class RenderTest(ApiTestCase):
    universal = Fingerprint.from_bytes(bytes.fromhex(ADDRESS_DIGEST), Mode.UNIVERSAL)
    keyed = Fingerprint.from_bytes(bytes.fromhex(KEYED), Mode.KEYED)

    def test_render_options_are_validated(self) -> None:
        for bad in (
            {"background": 0x1000000},
            {"background": -1},
            {"background_alpha": 256},
            {"background_alpha": -1},
            {"frame_alpha": 256},
            {"frame_alpha": -1},
        ):
            self.assert_error(ErrorCode.INVALID_ARGUMENT, RenderOptions, **bad)
        self.assert_error(ErrorCode.INVALID_ARGUMENT, RenderOptions().measure_contrast, -5)
        self.assert_error(ErrorCode.INVALID_ARGUMENT, RenderOptions().measure_contrast, 0x1000000)
        self.assertEqual(ContrastReport(300, 394), RenderOptions().measure_contrast())
        transparent = RenderOptions(background_alpha=0)
        self.assertEqual(300, transparent.measure_contrast(0x121212).figures_x100)
        self.assertEqual(112, transparent.measure_contrast(0x9E9E9E).figures_x100)

    def test_options_are_a_frozen_value(self) -> None:
        options = RenderOptions(Shape.ROUND, FrameStyle.GAPS, 0x121212, 200, 100)
        self.assertEqual(options, RenderOptions(Shape.ROUND, FrameStyle.GAPS, 0x121212, 200, 100))
        changed = dataclasses.replace(RenderOptions(Shape.ROUND), frame=FrameStyle.GAPS)
        self.assertEqual(RenderOptions(Shape.ROUND, FrameStyle.GAPS), changed)
        self.assertNotEqual(options, changed)
        self.assertEqual(1, len({options, pickle.loads(pickle.dumps(options))}))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            options.frame_alpha = 3
        self.assertIn("GAPS", repr(options))

    def test_pixels_are_rgba_with_straight_alpha(self) -> None:
        image = self.keyed.render(64)
        self.assertEqual((64, 64), image.size)
        self.assertEqual((64, 64), (image.width, image.height))
        self.assertEqual(64 * 64 * 4, len(image.rgba))
        self.assertIsInstance(image.rgba, bytes)
        # Outside the rounded corner of a keyed picture: transparent, and then black.
        self.assertEqual(b"\x00\x00\x00\x00", image.rgba[:4])
        middle = 4 * (32 * 64 + 5)
        self.assertEqual(b"\xff\xff\xff\xff", image.rgba[middle : middle + 4])
        self.assertEqual(image, self.keyed.render(64, RenderOptions()))
        self.assertEqual(hash(image), hash(self.keyed.render(64)))
        self.assertNotEqual(image, self.universal.render(64))
        self.assertEqual("<Image 64x64 RGBA>", repr(image))

    def test_sizes_are_integers(self) -> None:
        self.assertRaises(TypeError, self.universal.render, 64.0)
        self.assertRaises(TypeError, self.universal.render, "64")
        self.assertRaises(TypeError, self.universal.render, 64, "round")
        self.assert_error(ErrorCode.INVALID_SIZE, self.universal.render, -1)
        self.assert_error(ErrorCode.INVALID_SIZE, self.universal.render, 2**64)
        self.assertEqual(hh.MIN_SIZE, self.universal.render(hh.MIN_SIZE).width)
        self.assertEqual(hh.MAX_SIZE, self.universal.render(hh.MAX_SIZE).width)

    def test_errors_are_detected_in_the_order_of_the_specification(self) -> None:
        low_contrast = 0x7A96C5  # a palette colour
        marker = RenderOptions(frame=FrameStyle.ROUNDED, background=low_contrast)
        # 1. the size, 2. the frame, 3. the contrast, 4. room for the cells.
        self.assert_error(ErrorCode.INVALID_SIZE, self.universal.render, 15, marker)
        self.assert_error(ErrorCode.INVALID_SIZE, self.universal.render, 1025, marker)
        self.assert_error(ErrorCode.INVALID_FRAME, self.universal.render, 16, marker)
        self.assert_error(ErrorCode.LOW_CONTRAST, self.keyed.render, 16, marker)
        tight = RenderOptions(Shape.ROUND, FrameStyle.THICK, low_contrast)
        self.assert_error(ErrorCode.INVALID_FRAME, self.universal.render, 17, tight)
        self.assert_error(ErrorCode.LOW_CONTRAST, self.keyed.render, 17, tight)
        tight = RenderOptions(Shape.ROUND, FrameStyle.THICK)
        self.assert_error(ErrorCode.INVALID_SIZE, self.keyed.render, 17, tight)
        self.assertEqual(18, self.keyed.render(18, tight).width)
        # A translucent background is not measured: the page underneath is unknown.
        self.keyed.render(16, RenderOptions(background=low_contrast, background_alpha=254))

    def test_frames_follow_the_table_of_the_specification(self) -> None:
        allowed = {
            (Shape.SQUARE, Mode.UNIVERSAL): {"automatic", "none", "plain"},
            (Shape.ROUND, Mode.UNIVERSAL): {"automatic", "none", "plain"},
            (Shape.SQUARE, Mode.KEYED): {
                "automatic", "none", "plain", "rounded", "chamfered", "double", "thick", "brackets",
            },
            (Shape.ROUND, Mode.KEYED): {
                "automatic", "none", "plain", "double", "thick", "ticks", "gaps",
            },
        }
        for (shape, mode), names in allowed.items():
            fp = self.keyed if mode is Mode.KEYED else self.universal
            for style in FrameStyle:
                options = RenderOptions(shape, style)
                if style.value in names:
                    self.assertEqual(40, fp.render(40, options).width)
                else:
                    self.assert_error(ErrorCode.INVALID_FRAME, fp.render, 40, options)

    def test_automatic_is_rounded_for_keyed_squares_and_none_otherwise(self) -> None:
        for fp, shape, style in (
            (self.keyed, Shape.SQUARE, FrameStyle.ROUNDED),
            (self.keyed, Shape.ROUND, FrameStyle.NONE),
            (self.universal, Shape.SQUARE, FrameStyle.NONE),
            (self.universal, Shape.ROUND, FrameStyle.NONE),
        ):
            self.assertEqual(
                fp.render(48, RenderOptions(shape, style)), fp.render(48, RenderOptions(shape))
            )


class ImageTest(ApiTestCase):
    def test_encoders_check_their_arguments(self) -> None:
        image = RenderTest.universal.render(32)
        for quality in (49, 101, -1, 0, 1000):
            self.assert_error(ErrorCode.INVALID_QUALITY, image.encode_jpeg, quality)
        self.assert_error(ErrorCode.INVALID_ARGUMENT, image.encode_bmp, 0x1000000)
        self.assert_error(ErrorCode.INVALID_ARGUMENT, image.encode_jpeg, 92, -1)
        # The quality is looked at before the matte.
        self.assert_error(ErrorCode.INVALID_QUALITY, image.encode_jpeg, 49, -1)
        self.assertRaises(TypeError, image.encode_jpeg, 92.0)
        self.assertRaises(TypeError, image.encode_bmp, (255, 255, 255))
        self.assert_error(ErrorCode.INVALID_IMAGE, Image, 0, 1, b"")
        self.assert_error(ErrorCode.INVALID_IMAGE, Image, 1, 0, b"")
        self.assert_error(ErrorCode.INVALID_IMAGE, Image, -1, -1, bytes(4))
        self.assert_error(ErrorCode.INVALID_IMAGE, Image, 2, 2, bytes(15))
        self.assert_error(ErrorCode.INVALID_IMAGE, Image, 2, 2, bytes(17))
        self.assert_error(ErrorCode.INVALID_IMAGE, Image, 4097, 1, bytes(4097 * 4))
        self.assert_error(ErrorCode.INVALID_IMAGE, Image, 1, 4097, bytes(4097 * 4))
        self.assertRaises(TypeError, Image, 2.0, 2, bytes(16))
        self.assertEqual(image.encode_png(), Image(32, 32, bytearray(image.rgba)).encode_png())
        widest = Image(hh.MAX_DIMENSION, 1, bytes(4 * hh.MAX_DIMENSION))
        self.assertEqual(hh.MAX_DIMENSION, widest.width)

    def test_defaults(self) -> None:
        image = RenderTest.keyed.render(24)
        self.assertEqual(92, hh.DEFAULT_JPEG_QUALITY)
        self.assertEqual(image.encode_jpeg(92, 0xFFFFFF), image.encode_jpeg())
        self.assertEqual(image.encode_bmp(0xFFFFFF), image.encode_bmp())
        self.assertNotEqual(image.encode_bmp(0), image.encode_bmp())

    def test_an_image_holds_a_copy_of_its_pixels(self) -> None:
        source = bytearray(b"\x01\x02\x03\x04" * 4)
        image = Image(2, 2, source)
        source[0] = 99
        self.assertEqual(b"\x01\x02\x03\x04" * 4, image.rgba)
        self.assertEqual(image, pickle.loads(pickle.dumps(image)))
        self.assertEqual(image, Image(2, 2, memoryview(image.rgba)))
        for change in (
            lambda: setattr(image, "rgba", b""),
            lambda: setattr(image, "_width", 5),
            lambda: setattr(image, "_rgba", b""),
            lambda: setattr(image, "other", 1),
            lambda: delattr(image, "_rgba"),
            lambda: delattr(image, "_height"),
        ):
            self.assertRaises(AttributeError, change)
        self.assertEqual((2, 2, b"\x01\x02\x03\x04" * 4), (image.width, image.height, image.rgba))

    def test_values_travel_with_every_pickle_protocol(self) -> None:
        digest = BaseDigest.from_bytes(bytes.fromhex(ADDRESS_DIGEST))
        keyed = Fingerprint.from_bytes(bytes.fromhex(KEYED), Mode.KEYED)
        values = [
            digest,
            keyed,
            keyed.layout,
            keyed.layout.cells[0],
            keyed.render(16),
            Image(1, 2, bytes(range(8))),
            RenderOptions(Shape.ROUND, FrameStyle.GAPS, 0x121212, 200, 100),
            RenderOptions().measure_contrast(),
        ]
        for value in values:
            for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
                restored = pickle.loads(pickle.dumps(value, protocol))
                self.assertEqual(value, restored, (value, protocol))
                self.assertEqual(hash(value), hash(restored))
                self.assertIs(type(value), type(restored))
            self.assertEqual(value, copy.copy(value))
            self.assertEqual(value, copy.deepcopy(value))
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
            error = pickle.loads(pickle.dumps(HhError(ErrorCode.INVALID_KEY, "closed"), protocol))
            self.assertIs(ErrorCode.INVALID_KEY, error.code)

    def test_save_chooses_the_format_by_the_extension(self) -> None:
        image = RenderTest.keyed.render(24)
        with tempfile.TemporaryDirectory() as directory:
            for name, expected in (
                ("a.png", image.encode_png()),
                ("a.PNG", image.encode_png()),
                ("a.bmp", image.encode_bmp(0x102030)),
                ("a.jpg", image.encode_jpeg(60, 0x102030)),
                ("a.jpeg", image.encode_jpeg(60, 0x102030)),
            ):
                path = os.path.join(directory, name)
                image.save(path, quality=60, matte=0x102030)
                with open(path, "rb") as file:
                    self.assertEqual(expected, file.read(), name)
            target = pathlib.Path(directory) / "b.png"
            image.save(target)
            self.assertEqual(image.encode_png(), target.read_bytes())
            for name in ("a.gif", "a", "png", "a.png.txt"):
                path = os.path.join(directory, name)
                self.assert_error(ErrorCode.INVALID_ARGUMENT, image.save, path)
                self.assertFalse(os.path.exists(path))
            path = os.path.join(directory, "q.jpg")
            self.assert_error(ErrorCode.INVALID_QUALITY, image.save, path, quality=5)
            self.assertFalse(os.path.exists(path))

    def test_save_takes_what_open_takes_as_a_name(self) -> None:
        image = RenderTest.keyed.render(24)
        with tempfile.TemporaryDirectory() as directory:
            for name, expected in ((b"c.png", image.encode_png()), (b"c.BMP", image.encode_bmp())):
                path = os.path.join(os.fsencode(directory), name)
                image.save(path)
                with open(path, "rb") as file:
                    self.assertEqual(expected, file.read(), name)
            self.assert_error(
                ErrorCode.INVALID_ARGUMENT, image.save, os.path.join(os.fsencode(directory), b"c")
            )
            # A name that cannot name a file is an invalid value, not a ValueError of open().
            for name in ("a\0.png", "\0.png", "a\ud800.png"):
                path = os.path.join(directory, name)
                error = self.assert_error(ErrorCode.INVALID_ARGUMENT, image.save, path)
                self.assertIsNone(error.__cause__)
            bad = os.path.join(os.fsencode(directory), b"a\0.png")
            self.assert_error(ErrorCode.INVALID_ARGUMENT, image.save, bad)
            bad_path = pathlib.Path(directory, "a\0.jpg")
            self.assert_error(ErrorCode.INVALID_ARGUMENT, image.save, bad_path)
            self.assertEqual(["c.BMP", "c.png"], sorted(os.listdir(directory)))
            self.assertRaises(OSError, image.save, os.path.join(directory, "missing", "a.png"))
            for wrong in (None, 5, 1.5, ["a.png"]):
                self.assertRaises(TypeError, image.save, wrong)


class ErrorTest(ApiTestCase):
    def test_error_codes_match_the_specification(self) -> None:
        expected = {
            "empty_input": 1, "input_too_large": 2, "invalid_hex": 3, "invalid_key": 4,
            "invalid_digest": 5, "invalid_fingerprint": 6, "invalid_size": 7, "invalid_frame": 8,
            "low_contrast": 9, "invalid_quality": 10, "invalid_image": 11, "invalid_argument": 14,
        }
        self.assertEqual(expected, {code.spec_name: int(code) for code in ErrorCode})

    def test_an_error_keeps_its_code_across_processes(self) -> None:
        error = HhError(ErrorCode.INVALID_HEX, "not hexadecimal")
        restored = pickle.loads(pickle.dumps(error))
        self.assertIs(ErrorCode.INVALID_HEX, restored.code)
        self.assertEqual("not hexadecimal", str(restored))

    def test_enumerations_carry_the_values_of_the_specification(self) -> None:
        self.assertEqual([1, 2], [int(mode) for mode in Mode])
        self.assertEqual(list(range(7)), [int(figure) for figure in Figure])
        self.assertEqual(["square", "round"], [shape.value for shape in Shape])
        self.assertEqual(
            "automatic none plain rounded chamfered double thick brackets ticks gaps".split(),
            [style.value for style in FrameStyle],
        )


if __name__ == "__main__":
    unittest.main()
