"""EPUB transforms — the materialization side of a `spine=<N>&el=<K>` embed address.

- `spine=<N>` (EPUB → epub_doc) — selects the Nth content document in the OPF spine
  (reading order) and binds an image resolver over the book's separately-stored zip
  members. The intermediate `epub_doc` kind carries the selected document's raw XHTML
  plus that resolver.
- `el=<K>` (epub_doc → image) — the Kth addressable element in that spine document
  (document order, same axis as the drafter). Expects an `<img>`; resolves its `<img src>`
  against the EPUB's zip members and returns the decoded PIL image.

This mirrors the HTML `el=` transform, but an EPUB image is a separately-stored zip member
(resolved relative to the spine document) rather than an inline base64 `data:` URI. The
drafter (`draft/epub.py` via `corpus.epub.clean_xhtml_body`) records each `<img>` as an
embed addressed `spine=<N>&el=<K>` against the immutable artifact; this re-resolves that
address back to the bytes. El-indexing is shared with the drafter through
`corpus.epub.addressable_image_bytes`, so the `K` written into the address selects the same
element on materialization.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .. import epub as epub_mod
from . import RenderContext, register


@dataclass
class EpubDoc:
    """A selected spine document, the `epub` → `epub_doc` working value: its raw XHTML plus
    a resolver from an `<img src>` (relative to the document) to the zip-member bytes."""

    data: bytes
    resolve_img: Callable[[str], bytes | None]
    spine_index: int  # for error messages


@register("epub", "spine", "epub_doc")
def select_spine(path: Path, value: str | None, ctx: RenderContext) -> EpubDoc:
    """`?spine=N` — select the Nth content document (1-indexed) in the OPF spine and bind a
    resolver over the book's image members. `path` is the artifact `.epub`."""
    if value is None or not value.strip():
        raise ValueError("spine= requires an integer index")
    raw = value.strip()
    if "-" in raw:
        raise ValueError(
            f"spine={raw}: range form (spines=<a>-<b>) is a section span, not addressable "
            f"to an element; a single spine index is expected before el="
        )
    try:
        n = int(raw)
    except ValueError as exc:
        raise ValueError(f"spine={raw}: not an integer") from exc
    pkg = epub_mod.read_package(path)
    if n < 1 or n > len(pkg.spine):
        raise ValueError(
            f"spine={n} out of range (EPUB has {len(pkg.spine)} spine documents)"
        )
    doc = pkg.spine[n - 1]
    resolver = epub_mod.make_image_resolver(epub_mod.read_resources(path), doc.href)
    return EpubDoc(data=doc.data, resolve_img=resolver, spine_index=n)


@register("epub_doc", "el", "image")
def extract_el(doc: EpubDoc, value: str | None, ctx: RenderContext) -> Image.Image:
    """`?el=K` — the Kth addressable element in the selected spine document; expects an
    `<img>`, resolves its zip member, and returns the decoded PIL image."""
    if value is None or not value.strip():
        raise ValueError("el= requires an integer index")
    raw = value.strip()
    if "-" in raw:
        raise ValueError(
            f"el={raw}: range form not supported by the image-output transform; "
            f"single index expected"
        )
    try:
        k = int(raw)
    except ValueError as exc:
        raise ValueError(f"el={raw}: not an integer") from exc
    data = epub_mod.addressable_image_bytes(doc.data, k, doc.resolve_img)
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        raise ValueError(
            f"spine={doc.spine_index}&el={k}: failed to decode image member bytes: {exc}"
        ) from exc
    return img.convert("RGBA") if img.mode == "P" else img
