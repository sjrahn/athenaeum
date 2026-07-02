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

# Supported image algorithms → the `imagehash` function that computes each. All default
# to an 8x8 (64-bit, 16-hex) digest, satisfying the §7.6 `<algo>:<hex>` encoding. The
# `fingerprint` schema knob may select among these (§7.7); `phash` is the default.
_ALGO_FUNCS: dict[str, str] = {
    "phash": "phash",         # perceptual hash (DCT)
    "dhash": "dhash",         # difference (gradient) hash
    "ahash": "average_hash",  # average hash
    "whash": "whash",         # wavelet hash
}


def _imagehash() -> Any | None:
    try:
        import imagehash
    except ImportError:
        return None
    return imagehash


def fingerprint_image(im: Any, *, algo: str = ALGO) -> str | None:
    """Return `<algo>:<16-hex>` for a PIL Image, or None if `imagehash` is absent.
    `algo` ∈ {phash, dhash, ahash, whash} (spec §7.7)."""
    fn_name = _ALGO_FUNCS.get(algo)
    if fn_name is None:
        raise ValueError(f"unknown image fingerprint algorithm {algo!r}")
    ih = _imagehash()
    if ih is None:
        return None
    return f"{algo}:{getattr(ih, fn_name)(im)}"


def fingerprint_file(path: Path, *, algo: str = ALGO) -> str | None:
    """Return `<algo>:<16-hex>` for the image at `path`, or None if unavailable."""
    if _imagehash() is None:
        return None
    from PIL import Image

    with Image.open(path) as im:
        im.load()
        return fingerprint_image(im, algo=algo)
