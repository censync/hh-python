"""The base digest, the secret key and the fingerprint."""

from __future__ import annotations

import operator
from types import TracebackType
from typing import Any, Callable, NoReturn, Optional, Tuple, Type, TypeVar, Union

from . import _contrast, _derive, _raster
from ._errors import ErrorCode, HhError
from ._image import Image
from ._model import DEFAULT_OPTIONS, Layout, Mode, RenderOptions, as_bytes

_Bytes = Union[bytes, bytearray, memoryview]
_T = TypeVar("_T")


class BaseDigest:
    """The base digest of an input: its stretched, public 32-byte value (SPEC.md section 4).

    It is the only slow step, 16 384 iterations of PBKDF2-HMAC-SHA-256, so hosts compute it off
    the event loop and cache ``bytes(digest)`` per address; both modes and any key derive their
    fingerprint from it cheaply. It is public and needs no protection.

    Compute one with :meth:`of`, :meth:`of_hex` or :meth:`of_text`; :meth:`from_bytes` computes
    nothing and only restores a digest that was stored. A digest is immutable, hashable and
    compares by value.
    """

    SIZE = 32
    """The size of a base digest in bytes."""

    __slots__ = ("_bytes",)
    _bytes: bytes

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(
            "use BaseDigest.of(), of_hex() or of_text(), or from_bytes() for a stored digest"
        )

    @classmethod
    def _wrap(cls, raw: bytes) -> BaseDigest:
        self = object.__new__(cls)
        object.__setattr__(self, "_bytes", raw)
        return self

    @classmethod
    def of(cls, data: _Bytes) -> BaseDigest:
        """Binary input: the bytes of an address, a public key or a hash, 1 to 1 048 576.

        Raises :class:`HhError` with ``EMPTY_INPUT`` or ``INPUT_TOO_LARGE``.
        """
        return cls._wrap(_derive.base_digest(_derive.KIND_BINARY, as_bytes(data, "data")))

    @classmethod
    def of_hex(cls, text: str) -> BaseDigest:
        """Binary input given as hexadecimal text.

        An optional ``0x`` or ``0X``, then an even, non-zero number of hexadecimal digits of
        either case. Every spelling of one address gives the same digest.

        Raises :class:`HhError` with ``INVALID_HEX`` or, for well-formed text that decodes to
        more than 1 048 576 bytes, ``INPUT_TOO_LARGE``.
        """
        if not isinstance(text, str):
            raise TypeError(f"text must be a str, not {type(text).__name__}")
        return cls._wrap(_derive.base_digest(_derive.KIND_BINARY, _derive.decode_hex(text)))

    @classmethod
    def of_text(cls, text: Union[str, _Bytes]) -> BaseDigest:
        """Text input: the UTF-8 encoding of ``text``, verbatim, without normalisation.

        A ``str`` is encoded here; bytes are taken as UTF-8 that is already encoded and are not
        validated. A text input and a binary input with the same bytes give different digests.

        Raises :class:`HhError` with ``EMPTY_INPUT``, ``INPUT_TOO_LARGE`` or, for a ``str`` that
        holds a lone surrogate, ``INVALID_ARGUMENT``.
        """
        if isinstance(text, str):
            data = _derive.encode_text(text)
        else:
            data = as_bytes(text, "text")
        return cls._wrap(_derive.base_digest(_derive.KIND_TEXT, data))

    @classmethod
    def from_bytes(cls, raw: _Bytes) -> BaseDigest:
        """Not for an address, a public key or a hash: those go to :meth:`of`.

        Restores a digest that was computed before and stored, for example ``bytes(digest)``
        from a cache. Nothing is computed here: the 32 bytes of an address would be accepted
        and give a picture that is not the picture of that address.

        Raises :class:`HhError` with ``INVALID_DIGEST`` unless ``raw`` has 32 bytes.
        """
        data = as_bytes(raw, "raw")
        if len(data) != cls.SIZE:
            raise HhError(ErrorCode.INVALID_DIGEST, f"a base digest has {cls.SIZE} bytes")
        return cls._wrap(data)

    def hex(self) -> str:
        """The 32 bytes in lowercase hexadecimal."""
        return self._bytes.hex()

    def __bytes__(self) -> bytes:
        return self._bytes

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BaseDigest):
            return NotImplemented
        return self._bytes == other._bytes

    def __hash__(self) -> int:
        return hash(self._bytes)

    def __setattr__(self, name: str, value: Any) -> NoReturn:
        raise AttributeError("a BaseDigest is immutable")

    def __delattr__(self, name: str) -> NoReturn:
        raise AttributeError("a BaseDigest is immutable")

    def __reduce__(self) -> Tuple[Any, ...]:
        return (BaseDigest.from_bytes, (self._bytes,))

    def __repr__(self) -> str:
        return f"BaseDigest.from_bytes(bytes.fromhex('{self._bytes.hex()}'))"


class _KeyBuffer(bytearray):
    """The key bytes of a :class:`SecretKey`.

    A ``bytearray`` that ``hmac`` takes as it is and that never prints its content, so that a
    traceback or a debugger that shows local variables shows no key.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "<key bytes>"

    __str__ = __repr__

    def __reduce_ex__(self, protocol: Any) -> NoReturn:
        raise TypeError("key bytes cannot be pickled or copied")


class SecretKey:
    """The 32-byte secret of keyed mode.

    The key must be uniformly random or the output of a key derivation function: there is no
    passphrase form. Exactly 32 bytes that are not all zero are accepted, from any bytes-like
    object; the bytes are copied and no reference to the object is kept, so wipe your own buffer.

    :meth:`close` overwrites the copy held here with zeros; use the key as a context manager or
    close it when the application locks. A closed key refuses every use with ``INVALID_KEY``;
    only :attr:`check_value`, which is public, stays readable.

    That is as far as Python allows: the bytes you passed in, if they are an immutable ``bytes``
    object, and the copies that ``hmac`` and the interpreter make while computing stay in memory
    until the allocator reuses it. Hosts that cannot accept that compute the keyed fingerprint
    in native code or a secure element and hand the result to :meth:`Fingerprint.from_bytes`.

    A key cannot be pickled or copied, and its ``repr`` never shows key material.

    Raises :class:`HhError` with ``INVALID_KEY``.
    """

    SIZE = 32
    """The size of a key in bytes."""

    __slots__ = ("_bytes", "_check_value", "_closed")
    _bytes: _KeyBuffer
    _check_value: bytes
    _closed: bool

    def __init__(self, data: _Bytes) -> None:
        self._closed = True
        self._bytes = _KeyBuffer(self.SIZE)
        self._check_value = b""
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError(f"data must be bytes-like, not {type(data).__name__}")
        try:
            view = memoryview(data)
        except ValueError:
            raise TypeError("data is a released memoryview") from None
        # Whatever is raised below, this frame holds no name for the caller's bytes, and the view
        # is released first: the caller can wipe and resize its buffer.
        del data
        with view:
            fits = view.nbytes == self.SIZE
            if fits and view.contiguous:
                # Straight into the buffer that close() wipes, without a copy in between.
                with view.cast("B") as flat:
                    self._bytes[:] = flat
            elif fits:
                self._bytes[:] = view.tobytes()
        if not fits:
            raise HhError(ErrorCode.INVALID_KEY, f"a key has {self.SIZE} bytes")
        if not any(self._bytes):
            raise HhError(ErrorCode.INVALID_KEY, "the all-zero key is not a key")
        self._check_value = _derive.key_check_value(self._bytes)
        self._closed = False

    @property
    def closed(self) -> bool:
        """Whether :meth:`close` was called."""
        return self._closed

    @property
    def check_value(self) -> bytes:
        """The key check value: 4 bytes a host stores beside its cached data.

        A different value means that the key, and with it every keyed picture, changed. The
        value is public and is computed when the key is created, so it stays readable after
        :meth:`close`.
        """
        return self._check_value

    def _use(self, function: Callable[..., _T], *args: Any) -> _T:
        """Calls ``function(key bytes, *args)``.

        A key that is closed meanwhile is wiped to zeros, and a result computed under zeros must
        never be handed out, so the key is checked again afterwards.
        """
        self._ensure_open()
        result = function(self._bytes, *args)
        self._ensure_open()
        return result

    def _ensure_open(self) -> None:
        if self._closed:
            raise HhError(ErrorCode.INVALID_KEY, "the key was closed")

    def close(self) -> None:
        """Wipes the key. Closing twice is harmless; using a closed key raises ``INVALID_KEY``."""
        self._closed = True
        for i in range(len(self._bytes)):
            self._bytes[i] = 0

    def __enter__(self) -> SecretKey:
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except AttributeError:
            # The constructor failed before the buffer existed.
            pass

    def __reduce__(self) -> NoReturn:
        raise TypeError("a SecretKey cannot be pickled or copied")

    def __repr__(self) -> str:
        return "SecretKey(***)"


class Fingerprint:
    """32 bytes and the mode they were derived in: everything a picture depends on.

    Create one with :meth:`universal` or :meth:`keyed`, or import bytes computed elsewhere with
    :meth:`from_bytes`. A fingerprint is immutable, hashable and compares by bytes and mode.
    """

    SIZE = 32
    """The size of a fingerprint in bytes."""

    __slots__ = ("_bytes", "_mode")
    _bytes: bytes
    _mode: Mode

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("use Fingerprint.universal(), keyed() or from_bytes()")

    @classmethod
    def _wrap(cls, raw: bytes, mode: Mode) -> Fingerprint:
        self = object.__new__(cls)
        object.__setattr__(self, "_bytes", raw)
        object.__setattr__(self, "_mode", mode)
        return self

    @classmethod
    def universal(cls, digest: BaseDigest) -> Fingerprint:
        """The universal fingerprint is the base digest itself."""
        if not isinstance(digest, BaseDigest):
            raise TypeError(f"digest must be a BaseDigest, not {type(digest).__name__}")
        return cls._wrap(bytes(digest), Mode.UNIVERSAL)

    @classmethod
    def keyed(cls, digest: BaseDigest, key: SecretKey) -> Fingerprint:
        """The keyed fingerprint: one HMAC of the base digest under the key.

        Raises :class:`HhError` with ``INVALID_KEY`` if ``key`` was closed.
        """
        if not isinstance(digest, BaseDigest):
            raise TypeError(f"digest must be a BaseDigest, not {type(digest).__name__}")
        if not isinstance(key, SecretKey):
            raise TypeError(f"key must be a SecretKey, not {type(key).__name__}")
        return cls._wrap(key._use(_derive.keyed_fingerprint, bytes(digest)), Mode.KEYED)

    @classmethod
    def from_bytes(cls, raw: _Bytes, mode: Union[Mode, int]) -> Fingerprint:
        """Takes the 32 fingerprint bytes and the mode they belong to.

        For hosts that compute the keyed HMAC elsewhere, for example in native code or inside a
        secure element. ``mode`` is a :class:`Mode` or its value, the ``int`` 1 or 2; a ``bool``
        or a ``float`` is a ``TypeError``.

        Raises :class:`HhError` with ``INVALID_FINGERPRINT`` unless ``raw`` has 32 bytes and the
        mode is known.
        """
        data = as_bytes(raw, "raw")
        if not isinstance(mode, int) or isinstance(mode, bool):
            raise TypeError(f"mode must be a Mode or an int, not {type(mode).__name__}")
        try:
            known = Mode(mode)
        except ValueError:
            raise HhError(ErrorCode.INVALID_FINGERPRINT, "the mode is 1 or 2") from None
        if len(data) != cls.SIZE:
            raise HhError(ErrorCode.INVALID_FINGERPRINT, f"a fingerprint has {cls.SIZE} bytes")
        return cls._wrap(data, known)

    @property
    def mode(self) -> Mode:
        """The mode the bytes were derived in."""
        return self._mode

    @property
    def tag(self) -> str:
        """The six-character Crockford Base32 tag, for example ``K7QM2X``.

        Hosts display it as ``K7Q-M2X``. Text allows a certain check where a picture does not.
        """
        return _raster.tag(self._bytes)

    @property
    def layout(self) -> Layout:
        """The cells, the palette and the mode, for hosts that draw vectors themselves."""
        return Layout(
            self._mode, _raster.cells(self._bytes), _contrast.PALETTE, _contrast.FRAME_COLOUR
        )

    def render(self, size: int, options: Optional[RenderOptions] = None) -> Image:
        """Renders ``size`` x ``size`` pixels, 16..1024.

        Raises :class:`HhError` with ``INVALID_SIZE``, ``INVALID_FRAME`` or ``LOW_CONTRAST``, as
        section 6 of the specification defines, in that order of checks.
        """
        size = operator.index(size)
        if options is None:
            options = DEFAULT_OPTIONS
        elif not isinstance(options, RenderOptions):
            raise TypeError(f"options must be RenderOptions, not {type(options).__name__}")
        return Image(size, size, _raster.render(self._bytes, self._mode, size, options))

    def hex(self) -> str:
        """The 32 bytes in lowercase hexadecimal."""
        return self._bytes.hex()

    def __bytes__(self) -> bytes:
        return self._bytes

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Fingerprint):
            return NotImplemented
        return self._mode is other._mode and self._bytes == other._bytes

    def __hash__(self) -> int:
        return hash((self._mode, self._bytes))

    def __setattr__(self, name: str, value: Any) -> NoReturn:
        raise AttributeError("a Fingerprint is immutable")

    def __delattr__(self, name: str) -> NoReturn:
        raise AttributeError("a Fingerprint is immutable")

    def __reduce__(self) -> Tuple[Any, ...]:
        return (Fingerprint.from_bytes, (self._bytes, int(self._mode)))

    def __repr__(self) -> str:
        return f"<Fingerprint {self._mode.name.lower()} {self.tag}>"
