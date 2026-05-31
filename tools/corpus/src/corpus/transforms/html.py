"""HTML transforms.

- `el=<N>` (HTML → image) — Nth addressable element in document order. Expects
  the resolved element to be `<img>` whose `src` is a base64-encoded `data:` URI;
  returns the decoded PIL image.
- `selector=<css>` (HTML → image) — CSS selector identifying a single `<img>`;
  decodes its data URI. Back-compat with earlier records.

AVIF support depends on `pillow-avif-plugin` (declared as a base dependency).
"""

from __future__ import annotations

import base64
import io
import re
from typing import Any

# Side-effect: registers AVIF codec with PIL.
import pillow_avif  # noqa: F401
from bs4 import BeautifulSoup, Tag
from PIL import Image

from . import RenderContext, register

_DATA_URI_RE = re.compile(
    r"^data:image/([a-z0-9+.\-]+);base64,(.+)$", re.DOTALL | re.IGNORECASE
)

# Addressable elements for `el=N` — must match the drafter's tag set.
_ADDRESSABLE_TAGS = (
    "section", "article", "p", "ul", "ol", "table",
    "pre", "blockquote", "figure",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "img",
)


@register("html", "el", "image")
def extract_el(soup: BeautifulSoup, value: str | None, ctx: RenderContext) -> Image.Image:
    """`?el=N` — Nth addressable element in document order. Expects an `<img>`;
    decodes its src data URI and returns the PIL image."""
    if value is None or not value.strip():
        raise ValueError("el= requires an integer index")
    raw = value.strip()
    if "-" in raw:
        raise ValueError(
            f"el={raw}: range form not supported by the image-output transform; "
            f"single index expected"
        )
    try:
        n = int(raw)
    except ValueError as exc:
        raise ValueError(f"el={raw}: not an integer") from exc
    elements = soup.find_all(_ADDRESSABLE_TAGS)
    if n < 1 or n > len(elements):
        raise ValueError(
            f"el={n} out of range (artifact has {len(elements)} addressable elements)"
        )
    tag = elements[n - 1]
    if tag.name != "img":
        raise ValueError(
            f"el={n} resolved to <{tag.name}>, expected <img>; "
            f"non-img element resolution via el= is not supported"
        )
    return _img_tag_to_pil(tag, f"el={n}")


@register("html", "selector", "image")
def extract_via_selector(
    soup: BeautifulSoup, value: str | None, ctx: RenderContext
) -> Image.Image:
    """Resolve a CSS selector to a single `<img>` and decode its data URI."""
    if value is None or not value.strip():
        raise ValueError("selector= requires a CSS selector")
    selector = value.strip()
    try:
        matches = soup.select(selector)
    except Exception as exc:
        raise ValueError(f"selector failed to parse: {selector!r}: {exc}") from exc
    if not matches:
        raise ValueError(f"selector matched no elements: {selector!r}")
    if len(matches) > 1:
        raise ValueError(
            f"selector matched {len(matches)} elements (expected exactly 1): {selector!r}"
        )
    tag = matches[0]
    return _img_tag_to_pil(tag, selector)


def _img_tag_to_pil(tag: Tag, selector_for_error: str) -> Image.Image:
    if tag.name != "img":
        raise ValueError(
            f"selector {selector_for_error!r} resolved to <{tag.name}>, expected <img>"
        )
    src_raw = tag.get("src") or ""
    src = str(src_raw).strip()
    if not src.startswith("data:"):
        raise ValueError(
            f"<img src=> is not a data URI ({src[:60]!r}…) for {selector_for_error!r}; "
            "the html resolver only handles inline base64 data URIs"
        )
    match = _DATA_URI_RE.match(src)
    if not match:
        raise ValueError(
            f"<img src=> has an unrecognized data URI shape ({src[:80]!r}…); "
            "expected `data:image/<format>;base64,<bytes>`"
        )
    raw = base64.b64decode(match.group(2))
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:
        raise ValueError(
            f"failed to decode image bytes from data URI for {selector_for_error!r}: {exc}"
        ) from exc
    return img.convert("RGBA") if img.mode == "P" else img
