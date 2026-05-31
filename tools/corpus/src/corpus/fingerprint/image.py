"""Image fingerprint strategy: 64-bit pHash (spec §7.7).

Computed via the `imagehash` library (the `[fingerprint]` extra). Degrades to None
when the extra isn't installed — perceptual production is suspended-by-default, so a
base install simply emits no image fingerprint rather than failing.

Encoded `phash:<16-hex>` (64-bit) per the §7.6 convention.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

ALGO = "phash"
STRATEGY = "phash-64"


def _imagehash() -> Any | None:
    try:
        import imagehash
    except ImportError:
        return None
    return imagehash


def fingerprint_image(im: Any) -> str | None:
    """Return `phash:<16-hex>` for a PIL Image, or None if `imagehash` is absent."""
    ih = _imagehash()
    if ih is None:
        return None
    return f"{ALGO}:{ih.phash(im)}"


def fingerprint_file(path: Path) -> str | None:
    """Return `phash:<16-hex>` for the image at `path`, or None if unavailable."""
    ih = _imagehash()
    if ih is None:
        return None
    from PIL import Image

    with Image.open(path) as im:
        im.load()
        return f"{ALGO}:{ih.phash(im)}"
