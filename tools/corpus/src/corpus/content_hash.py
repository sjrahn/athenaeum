"""Canonical-content hashing strategies per spec §7.1 (`canonical_strategy`).

Each media-type schema MAY declare:

    canonical_strategy:
      algo: blake3-canonical-<media-type-id>
      canonicalization:
        - <step-1>
        - <step-2>
        - ...

The drafter computes the strategy at draft time and writes the result into the
record's `canonical:` frontmatter field as `<algo>:<hex>`. The strategy lets two
records be compared for "same content?" even when timestamps, producer strings, or
other ever-changing metadata cause the byte hash to drift.

This module registers each algo name against an implementation function; the drafter
dispatches via `compute(algo, path)`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import blake3 as _blake3
from bs4 import BeautifulSoup
from PIL import Image
from pypdf import PdfReader


def _canonicalize_pdf(path: Path) -> str:
    """blake3-canonical-pdf — concatenate per-page extracted text, blake3 the result.
    Drops /Info dates and producer strings by construction (they're not in the
    extracted text)."""
    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        chunks.append(text)
    # pypdf occasionally produces unpaired UTF-16 surrogates that fail plain UTF-8
    # encoding. Use `errors="replace"` so the canonical hash is always computable.
    canonical = "\n\n".join(chunks).encode("utf-8", errors="replace")
    return _blake3.blake3(canonical).hexdigest()


_HTML_DROP_TAGS = ("script", "style", "svg")
_WS_RUN = re.compile(r"\s+")


def _canonicalize_html(path: Path) -> str:
    """blake3-canonical-html — drop <script>/<style>/<svg>, collapse whitespace,
    blake3."""
    raw = path.read_bytes()
    soup = BeautifulSoup(raw, "html.parser")
    for tag_name in _HTML_DROP_TAGS:
        for tag in soup(tag_name):
            tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    canonical = _WS_RUN.sub(" ", text).strip().encode("utf-8")
    return _blake3.blake3(canonical).hexdigest()


def _canonicalize_image(path: Path) -> str:
    """blake3-canonical-image — rasterize to canonical resolution (longest side
    1024px) and color mode (RGB), then blake3 the raw pixel bytes."""
    with Image.open(path) as im:
        canonical_im = im.convert("RGB")
        w, h = canonical_im.size
        longest = max(w, h)
        if longest > 1024:
            scale = 1024 / longest
            new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
            canonical_im = canonical_im.resize(new_size, Image.LANCZOS)
        pixel_bytes = canonical_im.tobytes()
    return _blake3.blake3(pixel_bytes).hexdigest()


_STRATEGIES: dict[str, Callable[[Path], str]] = {
    "blake3-canonical-pdf": _canonicalize_pdf,
    "blake3-canonical-html": _canonicalize_html,
    "blake3-canonical-image": _canonicalize_image,
}


def compute(algo: str, path: Path) -> str:
    """Run the named strategy against `path`; return the resulting hex hash.

    Raises `ValueError` if the algo isn't registered.
    """
    fn = _STRATEGIES.get(algo)
    if fn is None:
        raise ValueError(f"unknown canonical_strategy algo: {algo!r}")
    return fn(path)


def available_algos() -> list[str]:
    return sorted(_STRATEGIES.keys())
