#!/usr/bin/env python3
"""Times the steps of hh-python on this machine, from the source tree.

usage: python tools/bench.py [size ...]        (default sizes: 64 128 256 1024)

The best of several runs is printed, in milliseconds. "cold" renders start with empty caches;
"warm" renders reuse the translation tables and the figure coverage of the render before.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Callable

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from humanized_hash import (
    BaseDigest,
    Fingerprint,
    FrameStyle,
    RenderOptions,
    SecretKey,
    Shape,
    _raster,
)

ADDRESS = bytes.fromhex("5aaeb6053f3e94c9b9a09f33669435e7ef1beaed")


def best(function: Callable[[], object], runs: int) -> float:
    """The shortest of ``runs`` calls, in milliseconds."""
    shortest = None
    for _ in range(runs):
        start = time.perf_counter()
        function()
        elapsed = time.perf_counter() - start
        shortest = elapsed if shortest is None else min(shortest, elapsed)
    return 1000 * (shortest or 0)


def main() -> None:
    sizes = [int(argument) for argument in sys.argv[1:]] or [64, 128, 256, 1024]
    print(f"{sys.implementation.name} {sys.version.split()[0]}")
    print(f"base digest  {best(lambda: BaseDigest.of(ADDRESS), 10):8.2f} ms")
    digest = BaseDigest.of(ADDRESS)
    with SecretKey(bytes(range(32))) as key:
        print(f"keyed HMAC   {best(lambda: Fingerprint.keyed(digest, key), 100):8.3f} ms")
        keyed = Fingerprint.keyed(digest, key)
    looks = [
        ("universal", Fingerprint.universal(digest), RenderOptions()),
        ("keyed", keyed, RenderOptions()),
        ("round ticks", keyed, RenderOptions(Shape.ROUND, FrameStyle.TICKS, 0x121212, 0, 100)),
    ]
    print(f"{'size':>4} {'look':<12}{'cold':>9}{'warm':>9}{'PNG':>9}{'BMP':>9}{'JPEG':>9}")
    for size in sizes:
        runs = 3 if size > 512 else 20
        for name, fingerprint, options in looks:

            def cold() -> None:
                _raster._figure_counts.cache_clear()
                _raster._pixel_tables.cache_clear()
                fingerprint.render(size, options)

            image = fingerprint.render(size, options)
            times = (
                best(cold, runs),
                best(lambda: fingerprint.render(size, options), runs),
                best(image.encode_png, runs),
                best(image.encode_bmp, runs),
                best(image.encode_jpeg, max(2, runs // 4)),
            )
            print(f"{size:>4} {name:<12}" + "".join(f"{value:9.2f}" for value in times))


if __name__ == "__main__":
    main()
