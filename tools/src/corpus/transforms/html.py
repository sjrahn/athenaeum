"""HTML transforms.

- `el=<N>` (HTML → htmlel) — Nth addressable element in document order, selected as
  an `HtmlElRef`. A *terminal* `el=N` materializes the element's inline bytes:
  an `<img>` decodes + renders to a PIL image (cache: PNG); a `<video>`/`<audio>`
  or `<a href="data:…">` attachment decodes to raw bytes (cache: the media's native
  extension). An image-output op after `el=N` (`bbox`/`mark`/`fit`/…) auto-promotes the
  `<img>` to an image first (non-image carriers cannot promote).
- `selector=<css>` (HTML → image) — CSS selector identifying a single `<img>`;
  decodes its data URI. Back-compat with earlier records.

Inline media (every carrier) lives in the HTML as a base64 `data:` URI — `<img src>` /
`srcset`, a `<video>`/`<audio>`'s `<source src>` (or own `src`), or an attachment
`<a href>`. The drafter (`corpus.draft.html`) addresses each carrier by `el=N` and the
resolver re-materializes its bytes here; the two MUST agree on which elements `el=N`
names, so the membership predicate (`is_addressable`) and the carrier→data-URI map
(`carrier_data_uri`) are defined here and imported by the drafter.

AVIF support depends on `pillow-avif-plugin` (declared as a base dependency).
"""

from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass

# Side-effect: registers AVIF codec with PIL.
import pillow_avif  # noqa: F401
from bs4 import BeautifulSoup, Tag
from PIL import Image

from . import NotMaterializable, RenderContext, register

#: Versioned op id (spec §6.4 / `ledger.md` §13.2's op-version pin) for the LIVE `el=` element-
#: scoping op materialized here (the htmlel working-kind path — `extract_el` below) — folded
#: into the resolver's cache key exactly like `transforms.csv.ENGINE_VERSION`. Scope: this pin
#: covers only the resolver's live re-materialization of `corpus://<hash>?el=N` from the
#: artifact bytes; a PERSISTED-SEGMENT `address: el=N` read (matching a citation's quote
#: against the record's already-STORED body text) is a distinct, unversioned surface and never
#: folds this in. A later change to element addressing (`is_addressable`) or carrier
#: materialization (`carrier_data_uri`) is a NEW id, never a silent reinterpretation of an
#: already-resolved (and potentially already-cited) result.
ENGINE_VERSION = "html-el@1"

# Image-only data URI (the `<img>` / `selector=` path keeps its strict shape).
_DATA_URI_RE = re.compile(
    r"^data:image/([a-z0-9+.\-]+);base64,(.+)$", re.DOTALL | re.IGNORECASE
)
# Any base64 data URI — `data:<media-type>;base64,<bytes>`. Used to materialize
# non-image carriers (video/audio/attachment) to raw bytes.
_ANY_DATA_URI_RE = re.compile(
    r"^data:([a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+)(?:;[^,]*)?;base64,(.+)$",
    re.DOTALL | re.IGNORECASE,
)

# Structural / image elements that get an `el=N` index for spec §4.3 addressing.
# Single shared index axis across structural containers (`section`, `article`),
# prose blocks (`p`, `ul`, `ol`, `dl`, `blockquote`), structured content (`table`,
# `pre`, `figure`), headings (`h1`-`h6`), and inline images (`img`). `dl` is the
# definition list — a content-bearing block, the peer of `ul`/`ol`; its `dt`/`dd`
# items stay non-addressable, exactly as `li` does. Layout-only wrappers
# (`div`, `span`) are NOT addressable — they're chrome the drafter unwraps anyway.
#
# This tuple is the structural axis shared with the EPUB `spine=N&el=K` resolver
# (`corpus.transforms.epub`); `test_drafters.py` asserts that lockstep. The HTML
# `el=N` axis is a SUPERSET — `is_addressable` additionally admits the inline media
# carriers below (EPUB has no inline-media carriers, so its axis stays structural).
_ADDRESSABLE_TAGS = (
    "section", "article", "p", "ul", "ol", "dl", "table",
    "pre", "blockquote", "figure",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "img",
)

# Inline media carriers beyond `<img>`. `<video>`/`<audio>` are containers whose bytes
# live in a child `<source data:…>` (or their own `src`); an `<a href="data:…">` is an
# attachment link (vCard, file, …). A bare `<a>`/`<source>` is NOT addressable — only a
# `data:`-bearing one is — so the per-message `<a href="sms://…">` timestamp links the
# imessage exporter emits stay off the index. `<source>` is never addressed independently;
# it is reached through its parent `<video>`/`<audio>`.
_MEDIA_CARRIER_TAGS = ("video", "audio")


def is_addressable(tag: object) -> bool:
    """`el=N` membership predicate, shared by the drafter and the resolver so the two
    stay in lockstep. True for the structural/image axis (`_ADDRESSABLE_TAGS`) plus the
    inline media carriers: `<video>`/`<audio>`, and `<a href="data:…">` attachment links."""
    if not isinstance(tag, Tag):
        return False
    name = tag.name
    if name in _ADDRESSABLE_TAGS:
        return True
    if name in _MEDIA_CARRIER_TAGS:
        return True
    if name == "a":
        href = tag.get("href")
        return isinstance(href, str) and href.startswith("data:")
    return False


_SRCSET_CANDIDATE_RE = re.compile(r"(\S+)\s+(\d+(?:\.\d+)?)[wx]", re.IGNORECASE)


def largest_img_src(tag: Tag) -> str | None:
    """Return an `<img>`'s highest-resolution **inlined** source for materialisation.

    In a self-contained snapshot SingleFile inlines both `src` and every `srcset`
    candidate as `data:` URIs; the displayed `src` is the thumbnail, `srcset` carries
    higher-resolution variants. Prefer the largest `srcset` candidate that is a `data:`
    URI (by its `w`/`x` descriptor), falling back to `src`. Remote (non-`data:`)
    candidates are skipped — only inlined bytes resolve offline. The drafter's embed
    metadata and the `el=` resolver MUST both use this selection so they agree on which
    image `el=N` names.

    `srcset` is comma-separated but a `data:` URI itself contains a comma (`;base64,`),
    so we don't split on commas. A `data:` URI has no whitespace, so each candidate's
    URL is one `\\S+` token immediately followed by its descriptor — match those pairs
    directly. Descriptor-less candidates (implicit `1x`) are ignored: never the largest.
    """
    best: str | None = None
    best_score = -1.0
    srcset = tag.get("srcset")
    if isinstance(srcset, str) and srcset.strip():
        for m in _SRCSET_CANDIDATE_RE.finditer(srcset):
            url = m.group(1)
            if not url.startswith("data:"):
                continue
            score = float(m.group(2))
            if score > best_score:
                best, best_score = url, score
    if best is not None:
        return best
    src = tag.get("src")
    return str(src).strip() if src else None


def carrier_data_uri(tag: Tag) -> str | None:
    """The inline base64 `data:` URI a carrier element materializes from, or None if the
    element carries no inlined bytes (a remote-only `<img>`, a `<video>` whose source was
    evicted, an `<a>` to a non-`data:` href). Shared by drafter + resolver."""
    if not isinstance(tag, Tag):
        return None
    name = tag.name
    if name == "img":
        src = (largest_img_src(tag) or "").strip()
        return src if src.startswith("data:") and src != "data:," else None
    if name in _MEDIA_CARRIER_TAGS:
        own = tag.get("src")
        if isinstance(own, str) and own.startswith("data:") and own != "data:,":
            return own.strip()
        for source in tag.find_all("source"):
            ssrc = source.get("src") if isinstance(source, Tag) else None
            if isinstance(ssrc, str) and ssrc.startswith("data:") and ssrc != "data:,":
                return ssrc.strip()
        return None
    if name == "a":
        href = tag.get("href")
        if isinstance(href, str) and href.startswith("data:") and href != "data:,":
            return href.strip()
        return None
    return None


_DOWNLOAD_LABEL_RE = re.compile(r"download\s+(?P<name>.+?)(?:\s*\([^)]*\))?\s*$", re.IGNORECASE)


def attachment_filename(tag: Tag) -> str | None:
    """Best-effort filename for an `<a href="data:…">` attachment, parsed from its link
    text. The imessage exporter renders attachments as `Click to download <name> (<size>)`;
    pull `<name>`. Returns None when no name is recoverable."""
    if not isinstance(tag, Tag) or tag.name != "a":
        return None
    text = tag.get_text(" ", strip=True)
    if not text:
        return None
    m = _DOWNLOAD_LABEL_RE.search(text)
    if m:
        name = m.group("name").strip()
        if name:
            return name
    return None


def parse_data_uri(uri: str) -> tuple[str, bytes] | None:
    """Decode a base64 `data:<media-type>;base64,<bytes>` URI to `(media_type, bytes)`,
    or None if the shape is unrecognized / the payload won't decode."""
    m = _ANY_DATA_URI_RE.match(uri.strip())
    if not m:
        return None
    media_type = m.group(1).lower()
    try:
        raw = base64.b64decode(m.group(2))
    except Exception:
        return None
    if not raw:
        return None
    return media_type, raw


@dataclass(frozen=True)
class HtmlElRef:
    """A selected `el=N` element (intermediate `htmlel` working kind). The resolver
    materializes it terminally — an `<img>` to a PIL image, a media/attachment carrier
    to raw bytes — or promotes an `<img>` to an image for a following image-output op."""

    tag: Tag
    index: int


@register("html", "el", "htmlel")
def extract_el(soup: BeautifulSoup, value: str | None, ctx: RenderContext) -> HtmlElRef:
    """`?el=N` — select the Nth addressable element in document order as an `HtmlElRef`.
    The concrete materialization (image vs raw bytes) is decided terminally by the
    resolver, since it depends on which element `N` names."""
    if value is None or not value.strip():
        raise ValueError("el= requires an integer index")
    raw = value.strip()
    if "-" in raw:
        # A span address (`el=1-8`) names a real envelope of elements; it just has no
        # single byte surface. Not a defect — see `NotMaterializable`.
        raise NotMaterializable(
            f"el={raw}: range form not supported by the materialization transform; "
            f"single index expected"
        )
    try:
        n = int(raw)
    except ValueError as exc:
        raise ValueError(f"el={raw}: not an integer") from exc
    elements = soup.find_all(is_addressable)
    if n < 1 or n > len(elements):
        raise ValueError(
            f"el={n} out of range (artifact has {len(elements)} addressable elements)"
        )
    tag = elements[n - 1]
    return HtmlElRef(tag=tag, index=n)


def render_htmlel_image(ref: HtmlElRef, ctx: RenderContext) -> Image.Image:
    """Render an `HtmlElRef` to a PIL image — valid only for an `<img>` carrier. Used for
    the terminal `el=N`-on-`<img>` case and for promotion before an image-output op."""
    tag = ref.tag
    if tag.name != "img":
        # Deliberately NOT NotMaterializable: an image-output op was CHAINED onto this
        # element, so the address claims a crop of an image that isn't there. That is a
        # real authoring defect, and lint should say so.
        raise ValueError(
            f"el={ref.index} resolved to <{tag.name}>, which has no image rendering; "
            f"image-output ops (bbox/mark/fit/…) apply only to <img> carriers"
        )
    return _img_tag_to_pil(tag, f"el={ref.index}")


def htmlel_bytes(ref: HtmlElRef) -> tuple[str, bytes]:
    """Materialize a non-image carrier (`<video>`/`<audio>`/`<a href="data:…">`) to
    `(media_type, raw_bytes)`. Raises for an `<img>` (use `render_htmlel_image`) or a
    structural element with no inline bytes."""
    tag = ref.tag
    uri = carrier_data_uri(tag)
    if uri is None:
        # The element IS there and is exactly what the address said — a heading, a
        # table, a list. Its content is text, so there are no bytes to materialize; a
        # text segment citing it is complete as it stands.
        raise NotMaterializable(
            f"el={ref.index} resolved to <{tag.name}>, which carries no inline data: URI "
            f"to materialize"
        )
    parsed = parse_data_uri(uri)
    if parsed is None:
        raise ValueError(
            f"el={ref.index} (<{tag.name}>): unrecognized or undecodable data URI"
        )
    return parsed


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
    src_raw = largest_img_src(tag) or ""
    src = str(src_raw).strip()
    if not src.startswith("data:"):
        raise ValueError(
            f"<img src=> is not a data URI ({src[:60]!r}…) for {selector_for_error!r}; "
            "the html resolver only handles inline base64 data URIs"
        )
    match = _DATA_URI_RE.match(src)
    if match:
        raw = base64.b64decode(match.group(2))
    else:
        # The source may inline an image under a generic / non-image media type —
        # imessage-exporter labels some inline JPEGs `data:application/octet-stream`. Decode
        # any base64 data URI and let PIL sniff the real format from the bytes below; if
        # they are not a decodable image, `Image.open` raises and we report that.
        parsed = parse_data_uri(src)
        if parsed is None:
            raise ValueError(
                f"<img src=> has an unrecognized data URI shape ({src[:80]!r}…); "
                "expected `data:<media-type>;base64,<bytes>`"
            )
        raw = parsed[1]
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:
        raise ValueError(
            f"failed to decode image bytes from data URI for {selector_for_error!r}: {exc}"
        ) from exc
    return img.convert("RGBA") if img.mode == "P" else img
