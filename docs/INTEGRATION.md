# Integration

How to put hh-python into an application. What to hash, which mode to show where and how large a
picture must be are the same for every implementation and are described once, in
[INTEGRATION.md of hh-cpp](https://github.com/censync/hh-cpp/blob/v1.1.0/docs/INTEGRATION.md)
(sections 1 to 4). This document adds the Python side.

## 1. The three steps and what to cache

```python
from humanized_hash import BaseDigest, Fingerprint

digest = BaseDigest.of_hex(address)                # slow, public: cache bytes(digest)
fingerprint = Fingerprint.keyed(digest, key)       # one HMAC; or Fingerprint.universal(digest)
image = fingerprint.render(size, options)          # fast
```

- The **base digest** is 16 384 iterations of PBKDF2-HMAC-SHA-256, which `hashlib` runs in
  OpenSSL: 2 to 4 ms on a desktop core. An interpreter built without OpenSSL falls back to a
  loop over `hashlib.sha256` and needs several times as long: 10 to 15 ms on CPython, much more
  on PyPy. It is public and needs no protection, so cache it: in memory with
  `functools.lru_cache`, or as 32 bytes per address in the application's database
  (`bytes(digest)`, `BaseDigest.from_bytes`).
- `BaseDigest.from_bytes` is for those cached bytes only. It computes nothing, so the 32 bytes of
  an address passed to it give a picture that nobody else sees for that address, without an
  error; an address goes to `BaseDigest.of`, `of_hex` or `of_text`.
- Changing the key or the mode never needs the slow step again.
- **Rendering** a 128-pixel picture takes one to two milliseconds and its PNG three to four; a
  1024-pixel picture about 20 ms and its PNG about 120 ms. JPEG costs several times as much as
  PNG and rings on flat colour edges; prefer PNG.

```python
from functools import lru_cache

@lru_cache(maxsize=4096)
def digest_of(address: str) -> BaseDigest:
    return BaseDigest.of_hex(address)

@lru_cache(maxsize=1024)
def public_png(address: str, size: int) -> bytes:
    return Fingerprint.universal(digest_of(address)).render(size).encode_png()
```

`BaseDigest`, `Fingerprint`, `RenderOptions` and `Image` are immutable and hashable, so they are
safe cache keys and cache values. Cache by the address in one spelling (`address.lower()`), or
every spelling takes its own slot. In an `asyncio` application compute the digest with
`loop.run_in_executor`; the call releases the GIL while OpenSSL works.

Which bytes to hash per chain (EVM, Sui, Solana, Tron, TON, Bitcoin) is listed in section 1 of
hh-cpp's INTEGRATION.md: `BaseDigest.of_hex` or `BaseDigest.of` for binary inputs,
`BaseDigest.of_text` for formats that exist only as text.

## 2. Web backends

The encoders return `bytes`; every framework has a way to send bytes with a content type. With
the standard library alone:

```python
from wsgiref.simple_server import make_server
from humanized_hash import HhError

def application(environ, start_response):
    # GET /0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed
    try:
        body = public_png(environ["PATH_INFO"].lstrip("/").lower(), 128)
    except HhError as error:
        start_response("400 Bad Request", [("Content-Type", "text/plain; charset=utf-8")])
        return [error.code.spec_name.encode("ascii")]
    start_response("200 OK", [
        ("Content-Type", "image/png"),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "public, max-age=31536000, immutable"),
    ])
    return [body]

make_server("127.0.0.1", 8000, application).serve_forever()
```

The same bytes are returned from the usual frameworks:

| Framework | Response |
|---|---|
| Flask | `Response(body, mimetype="image/png")` |
| Django | `HttpResponse(body, content_type="image/png")` |
| FastAPI, Starlette | `Response(content=body, media_type="image/png")` |
| aiohttp | `web.Response(body=body, content_type="image/png")` |

A universal picture never changes, so it may be cached for ever (`immutable`). A keyed picture is
private to one user: serve it with `Cache-Control: private, no-store`, never from a shared cache,
and only over an authenticated connection. Bound the size parameter yourself (16 to 1024 is what
the library accepts; a public endpoint should offer a few fixed sizes) and keep the input limit
of your server below the 1 MiB that the library accepts.

## 3. Desktop toolkits

Tkinter reads PNG from memory (Tk 8.6):

```python
import tkinter

root = tkinter.Tk()
photo = tkinter.PhotoImage(data=fingerprint.render(128).encode_png())
tkinter.Label(root, image=photo).pack()      # keep a reference to photo while it is shown
root.mainloop()
```

With Pillow, for hosts that already have it, the pixels are one line:
`PIL.Image.frombytes("RGBA", image.size, image.rgba)`. With Qt for Python:

```python
view = QImage(image.rgba, image.width, image.height, 4 * image.width, QImage.Format_RGBA8888)
owned = view.copy()                          # detach from the bytes before they go away
```

Both take straight (non-premultiplied) alpha, which is what `Image.rgba` holds.

Render at the exact device-pixel size instead of scaling: the rasteriser is anti-aliased for the
size it is asked for. `image.save("address.png")` writes a file; the extension (`.png`, `.bmp`,
`.jpg` or `.jpeg`, in upper or lower case) chooses the format.

## 4. Keyed mode and key handling

```python
from humanized_hash import SecretKey

with SecretKey(key_bytes) as key:            # exactly 32 bytes, not all zero
    stored_check_value = key.check_value     # 4 bytes; compare with the stored ones
    fingerprint = Fingerprint.keyed(digest, key)
```

- The key is 32 uniformly random bytes or the output of a key derivation function, for example a
  SLIP-0021 node of the wallet seed (SECURITY.md of hh-cpp, "The key"). There is no passphrase
  form. The all-zero key is refused: a zero-filled buffer is what a failed key load looks like.
- `SecretKey` copies the bytes into a `bytearray` of its own and lets go of the object it was
  given; `close()`, the end of the `with` block and garbage collection overwrite that copy with
  zeros, and every use of a closed key raises `HhError` with `INVALID_KEY`. `key.closed` tells
  whether that happened. Pass the key as a `bytearray` and wipe it yourself afterwards.
- `check_value` is public. It is computed when the key is created and stays readable after
  `close()`, so a host can compare it with the stored one at any time.
- **What Python cannot wipe.** An immutable `bytes` object cannot be overwritten: if the key ever
  existed as `bytes` (read from a file, decoded from hexadecimal, returned by a KDF), that copy
  stays in memory until the allocator reuses it. `hmac` and OpenSSL make short-lived copies of
  the key while they compute. The interpreter may be swapped out or dumped. Treat `close()` as
  hygiene, not as a guarantee.
- A host that must keep the key out of the Python process computes the keyed fingerprint where
  the key lives (hh-cpp: `hh_keyed_fingerprint`; a secure element; an HSM: it is one
  HMAC-SHA-256, section 4 of the specification) and imports the result:

```python
fingerprint = Fingerprint.from_bytes(hmac_from_elsewhere, Mode.KEYED)
```

- A key cannot be pickled or copied, its `repr` is `SecretKey(***)`, and the buffer it holds
  prints as `<key bytes>`, so a traceback that shows local variables shows no key from inside the
  library. Your own variables are yours to guard: keep the key out of logs, exception messages
  and `multiprocessing` arguments; send worker processes the fingerprint, not the key.
- When `check_value` differs from the stored one, every private picture is about to change: stop
  and explain, do not re-key silently.

## 5. Looks and contrast

```python
from humanized_hash import FrameStyle, RenderOptions, Shape

options = RenderOptions(
    shape=Shape.ROUND,
    frame=FrameStyle.DOUBLE,           # any style of the shape, in either mode
    background=0x121212,
    background_alpha=255,
    frame_alpha=255,
)
report = options.measure_contrast(page=0x121212)
if report.figures_x100 < 300:
    ...                                # warn the user: figures may be hard to see
```

`frame` takes every style in both modes. `NONE`, `PLAIN`, `DOUBLE` and `THICK` fit either shape,
`ROUNDED`, `CHAMFERED` and `BRACKETS` the square, `TICKS` and `GAPS` the round shape; a style that
does not fit the shape is `INVALID_FRAME`. The default, `AUTOMATIC`, gives universal pictures no
frame and keyed square pictures rounded corners. A host that marks its keyed pictures with a
frame uses one style everywhere in the application and on every device of a user: a marker is
only useful if it is familiar. The library does not enforce the marker, so the caption, not the
frame, is what tells the user the mode.

Rendering refuses an opaque background with less than 2:1 against any palette colour
(`LOW_CONTRAST`). For a translucent background pass the colour of the surface underneath as
`page`. On a dark theme use `RenderOptions(background_alpha=0)` over a dark surface or an opaque
dark background; avoid mid greys and saturated surfaces. Colours are integers `0xRRGGBB`.

`fingerprint.layout` gives the cells, the palette and the mode to hosts that draw vectors
themselves (SVG, a canvas); the raster of `render` is the canonical form and the only one
covered by byte-exact vectors. `fingerprint.tag` is the six-character text form, shown as
`K7Q-M2X`: it is certain where a picture is not.

## 6. Errors

Invalid values raise `HhError`, a `ValueError`; `error.code` is an `ErrorCode` whose integer
value is the code of the C ABI and whose `spec_name` is the spelling of the specification.

| Call | `ErrorCode` |
|---|---|
| `BaseDigest.of`, `of_hex`, `of_text` | `EMPTY_INPUT`, `INPUT_TOO_LARGE`, `INVALID_HEX`, `INVALID_ARGUMENT` (a `str` with a lone surrogate) |
| `BaseDigest.from_bytes`, `Fingerprint.from_bytes` | `INVALID_DIGEST`, `INVALID_FINGERPRINT` |
| `SecretKey(...)`, use of a closed key | `INVALID_KEY` |
| `Fingerprint.render` | `INVALID_SIZE`, `INVALID_FRAME` (a style that does not fit the shape), `LOW_CONTRAST`, in this order of checks |
| `Image(...)`, `Image.encode_jpeg` | `INVALID_IMAGE`, `INVALID_QUALITY` |
| `RenderOptions(...)`, `measure_contrast`, `encode_bmp`, `encode_jpeg`, `save` | `INVALID_ARGUMENT` for a colour outside `0..0xFFFFFF`, an alpha outside `0..255`, an unknown file extension or a file name that cannot name a file (an embedded NUL; outside Windows also a lone surrogate) |

Arguments of the wrong type (a `str` where bytes are expected, a `float` size, a `bool` mode, a
`memoryview` that was released) raise `TypeError`. Nothing else is raised apart from
`MemoryError` and, in `Image.save`, `OSError` when the file cannot be written.

## 7. Threads and processes

The library keeps no mutable global state apart from small caches (translation tables of recent
backgrounds, the coverage of recent cell sizes, Huffman bit strings) that are safe to share: a
race at worst computes a value twice. Every function may be called from any thread, also on the
free-threaded build. The base digest releases the GIL inside OpenSSL; rendering and encoding are
pure Python and hold it, so a server that renders much uses processes rather than threads.
Values pickle (`BaseDigest`, `Fingerprint`, `RenderOptions`, `Image`, `HhError`); `SecretKey`
deliberately does not. A `SecretKey` must not be closed while another thread uses it; if that
happens the operation raises `INVALID_KEY` instead of returning a result computed from zeros.

## 8. Conformance

`python -m unittest discover -s tests -t .` reproduces every record of `testdata/vectors.tsv`
and every file of `testdata/golden/`; `tools/crosscheck.sh` compares thousands of pseudo-random
cases, valid and invalid, with `hh_cli` of hh-cpp byte for byte. A mismatch is a bug in this
implementation, never a reason to change the vectors.
