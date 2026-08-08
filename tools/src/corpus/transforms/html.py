"""HTML transforms.

- `el=<path>` (HTML → htmlel) *(3.6, §6.1.1)* — the element named by a dotted
  child-index path walked from the artifact's body, selected as an `HtmlElRef`. A
  *terminal* `el=` materializes the element's inline bytes: an `<img>` decodes +
  renders to a PIL image (cache: PNG); a `<video>`/`<audio>` or `<a href="data:…">`
  attachment decodes to raw bytes (cache: the media's native extension). An
  image-output op after `el=` (`bbox`/`mark`/`fit`/…) auto-promotes the `<img>` to an
  image first (non-image carriers cannot promote). A record not yet stamped with
  `addressing:` (§7.1) resolves through the FROZEN pre-3.6 filtered index instead —
  `legacy_is_addressable`, below.
- `selector=<css>` (HTML → image) — CSS selector identifying a single `<img>`;
  decodes its data URI. Back-compat with earlier records.

Inline media (every carrier) lives in the HTML as a base64 `data:` URI — `<img src>` /
`srcset`, a `<video>`/`<audio>`'s `<source src>` (or own `src`), or an attachment
`<a href>`. The drafter (`corpus.draft.html`) addresses each carrier by its `el=` path
and the resolver re-materializes its bytes here. What the two share is the path walk
itself (`element_path` / `resolve_element_path`) and the carrier→data-URI map
(`carrier_data_uri`) — there is no membership predicate to drift, which is the 3.6
amendment's substance (§12.28).

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

from .. import functional_uri as furi
from . import NotMaterializable, RenderContext, register

#: Versioned op id (spec §6.4 / `ledger.md` §13.2's op-version pin) for the LIVE `el=` element-
#: scoping op materialized here (the htmlel working-kind path — `extract_el` below) — folded
#: into the resolver's cache key exactly like `transforms.csv.ENGINE_VERSION`. Scope: this pin
#: covers only the resolver's live re-materialization of `corpus://<hash>?el=…` from the
#: artifact bytes; a PERSISTED-SEGMENT `address: el=…` read (matching a citation's quote
#: against the record's already-STORED body text) is a distinct, unversioned surface and never
#: folds this in. A later change to element addressing or carrier materialization
#: (`carrier_data_uri`) is a NEW id, never a silent reinterpretation of an
#: already-resolved (and potentially already-cited) result — `@2` is the 3.6 path space
#: (§6.1.1) replacing the `@1` whitelist counter, exactly that rule applied to itself.
ENGINE_VERSION = "html-el@2"

#: The pinned parser identity (spec §6.1.1 / §7.1's `addressing` key): the stdlib-backed
#: `html.parser` tree BeautifulSoup builds. Error recovery and implied-tag insertion
#: differ BETWEEN parsers (lxml, html5lib), so the choice is part of the address
#: contract, not an implementation detail — the drafter stamps this identity beside the
#: attested element count, and the resolver refuses a record stamped under any other.
EL_PARSER_ID = "html.parser"

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

# ---------- the LEGACY (pre-3.6) filtered index ---------- #
#
# Until 3.6 the `el=N` axis was a 1-based counter over a WHITELIST of tags — a versioned
# contract in disguise (§12.28: adding `<dl>` on 2026-06-25 silently re-pointed stored
# addresses on 455 of 458 artifacts carrying one). The whitelist below is FROZEN as of
# ATH-CORPUS 3.5 and must never change again: its only remaining consumers are the
# resolver's legacy branch for records not yet stamped with `addressing:` (§7.1) and the
# §12.28 remap, both of which need the exact enumeration the stored addresses were
# written under. New addressing goes through the total path space (§6.1.1, below);
# which elements a drafter chooses to EMIT for is now a free heuristic owned by
# `corpus.draft.html`, deliberately unshared.
_LEGACY_ADDRESSABLE_TAGS = (
    "section", "article", "p", "ul", "ol", "dl", "table",
    "pre", "blockquote", "figure",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "img",
)

# Inline media carriers beyond `<img>`. `<video>`/`<audio>` are containers whose bytes
# live in a child `<source data:…>` (or their own `src`); an `<a href="data:…">` is an
# attachment link (vCard, file, …). A bare `<a>`/`<source>` is NOT a carrier — only a
# `data:`-bearing one is — so the per-message `<a href="sms://…">` timestamp links the
# imessage exporter emits stay off the legacy index. `<source>` is never addressed
# independently; it is reached through its parent `<video>`/`<audio>`.
_MEDIA_CARRIER_TAGS = ("video", "audio")


def legacy_is_addressable(tag: object) -> bool:
    """The FROZEN pre-3.6 `el=N` membership predicate (see `_LEGACY_ADDRESSABLE_TAGS`).
    True for the structural/image axis plus the inline media carriers:
    `<video>`/`<audio>`, and `<a href="data:…">` attachment links."""
    if not isinstance(tag, Tag):
        return False
    name = tag.name
    if name in _LEGACY_ADDRESSABLE_TAGS:
        return True
    if name in _MEDIA_CARRIER_TAGS:
        return True
    if name == "a":
        href = tag.get("href")
        return isinstance(href, str) and href.startswith("data:")
    return False


# ---------- the el= path walk (3.6, spec §6.1.1) ---------- #
#
# The one shared implementation of the total address space: the drafter computes paths
# with it, the resolver walks them back with it, and the §12.28 remap pairs old→new
# through it. It has no configuration to drift — that is the amendment's point.


def path_root(soup: BeautifulSoup) -> Tag:
    """The element the path walk is rooted at: the artifact's `<body>` (§6.1.1). A
    body-less fragment roots at the document itself — the parse has no narrower
    container, so the document root IS the effective body; the attested element count
    keeps both sides honest about which tree they walked."""
    body = soup.body
    return body if body is not None else soup  # type: ignore[return-value]


def iter_element_children(tag: Tag) -> list[Tag]:
    """`tag`'s ELEMENT children in document order — the siblings a path component
    indexes into. Text nodes and comments are invisible to the walk."""
    return [c for c in tag.children if isinstance(c, Tag)]


def element_path(tag: Tag, root: Tag) -> str | None:
    """The §6.1.1 child-index path of `tag` walked up to `root`, as the canonical
    dotted string (no `el=` key). None when `tag` is not under `root` (or IS `root`:
    the root itself has no path — a whole-transport claim is the ABSENT address
    (§4.3.2.2: address optional, absence naming the whole transport), never a path
    that names the root)."""
    parts: list[int] = []
    node = tag
    while node is not root:
        parent = node.parent
        if parent is None:
            return None
        index = 0
        for child in parent.children:
            if isinstance(child, Tag):
                index += 1
                if child is node:
                    break
        else:
            return None
        parts.append(index)
        node = parent
    if not parts:
        return None
    return ".".join(str(i) for i in reversed(parts))


def resolve_element_path(root: Tag, path: furi.ElPath) -> Tag:
    """Walk `path`'s components down from `root` to the element it names. Raises
    `ValueError` naming the first component that runs past its parent's element-child
    count — bounds are a property of the ADDRESS (the `parse_index_span` lesson), so a
    sibling-range address bounds-checks its endpoints here too, BEFORE the caller
    decides whether there is anything to materialize."""
    node = root
    for depth, want in enumerate(path.components, start=1):
        children = iter_element_children(node)
        if want > len(children):
            walked = ".".join(str(c) for c in path.components[:depth])
            raise ValueError(
                f"el={furi.format_el_path(path)}: component {depth} ({walked}) walks to "
                f"child {want}, but <{node.name}> has {len(children)} element children"
            )
        node = children[want - 1]
    if path.sibling_range is not None:
        _a, b = path.sibling_range
        children = iter_element_children(node)
        if b > len(children):
            raise ValueError(
                f"el={furi.format_el_path(path)}: sibling range runs to child {b}, but "
                f"<{node.name}> has {len(children)} element children"
            )
    return node


def total_element_count(soup: BeautifulSoup) -> int:
    """The artifact's total element count over the WHOLE document — the attested
    self-check (§6.1.1/§7.1): a consumer whose parse yields a different number knows its
    tree disagrees with the one the addresses were computed under, and says so."""
    return len(soup.find_all(True))


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
    """A selected `el=` element (intermediate `htmlel` working kind). The resolver
    materializes it terminally — an `<img>` to a PIL image, a media/attachment carrier
    to raw bytes — or promotes an `<img>` to an image for a following image-output op.
    `index` is the address's own spelling (a 3.6 path string, or a legacy integer on an
    unstamped record) — used only to name the element in error messages."""

    tag: Tag
    index: int | str


@register("html", "el", "htmlel")
def extract_el(soup: BeautifulSoup, value: str | None, ctx: RenderContext) -> HtmlElRef:
    """`?el=<path>` — walk the child-index path (§6.1.1) to its element as an
    `HtmlElRef`. The concrete materialization (image vs raw bytes) is decided terminally
    by the resolver, since it depends on which element the path names.

    Which grammar the value is read under is decided by the RECORD, not the value: a
    record stamped with `addressing:` (§7.1) carries path addresses; an unstamped record
    still carries the pre-3.6 filtered index and resolves through the frozen legacy
    enumeration, unchanged. The bare-integer spelling is valid under BOTH grammars with
    different meanings (`el=5` = 5th whitelisted element vs body's 5th element child),
    so sniffing the value would resolve silently to the wrong element — the exact
    failure this amendment exists to end.

    On the stamped branch the two attested facts are checked FIRST: a foreign parser
    identity or a diverging element count is a hard error, never a silent walk of the
    wrong tree. A sibling range (`el=1.3.[2-9]`) is bounds-checked exactly like a point
    and only THEN declared unmaterializable — an envelope that runs past the tree names
    nothing, and reporting it as declared coverage is how confabulated span addresses
    stayed invisible to the gate (the `parse_index_span` lesson, kept)."""
    addressing = ctx.get("el_addressing")
    if addressing:
        parser = str(addressing.get("parser") or "")
        if parser and parser != EL_PARSER_ID:
            raise ValueError(
                f"record's el= addresses were computed under parser {parser!r}; this "
                f"toolchain resolves with {EL_PARSER_ID!r} and their trees may disagree "
                f"(§6.1.1) — re-attest to re-stamp before resolving"
            )
        stamped = addressing.get("elements")
        if stamped is not None:
            actual = total_element_count(soup)
            if int(stamped) != actual:
                raise ValueError(
                    f"element-count mismatch: the record attests {stamped} elements, "
                    f"this parse yields {actual} — the trees disagree, so el= paths "
                    f"would resolve to the wrong elements (§6.1.1); re-attest to "
                    f"re-derive addresses against the current parse"
                )
        path = furi.parse_el_path(value)
        tag = resolve_element_path(path_root(soup), path)
        if not path.is_point:
            # An in-bounds sibling range names a real envelope of elements; it just has
            # no single byte surface. Not a defect — see `NotMaterializable`.
            raise NotMaterializable(
                f"el={furi.format_el_path(path)}: sibling-range envelope has no single "
                f"byte surface to materialize; a point path is required for that"
            )
        return HtmlElRef(tag=tag, index=furi.format_el_path(path))

    # Legacy branch — an unstamped (pre-3.6) record: the frozen filtered index.
    elements = soup.find_all(legacy_is_addressable)
    low, high = furi.parse_index_span(
        "el", value, count=len(elements), noun="artifact"
    )
    if low != high:
        raise NotMaterializable(
            f"el={low}-{high}: span envelope has no single byte surface to "
            f"materialize; a single index is required for that"
        )
    return HtmlElRef(tag=elements[low - 1], index=low)


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


def el_member_bytes(
    artifact_path: object, value: str, *, el_addressing: dict | None = None
) -> tuple[str, bytes]:
    """*(3.8)* The raw bytes of the member carried at `el=<value>` in the HTML artifact at
    `artifact_path` — `(media_type, bytes)`, exactly as the carrier's base64 `data:` payload
    decodes, which is what attestation hashed into the roster row (§4.3.1.4).

    This is the containment-layer entry point (`containment.open_member_stream`), NOT a
    resolver op, and the difference is the whole reason it exists: the resolver's terminal
    `el=`-on-`<img>` op *renders* to a PIL image, which re-encodes — fine for a view, fatal for
    a promotion, whose `id` must equal the member's declared blake3. So an `<img>` is decoded
    here rather than rendered, and every carrier family goes through one path.

    `el_addressing` dispatches the grammar exactly as `extract_el` does — its presence means
    3.6 paths, its absence the frozen legacy index — and its drift checks run first, because
    resolving to the wrong element would mint a record under the wrong id."""
    from pathlib import Path as _Path

    soup = BeautifulSoup(_Path(str(artifact_path)).read_bytes(), EL_PARSER_ID)
    ctx: RenderContext = {}
    if el_addressing:
        ctx["el_addressing"] = el_addressing
    ref = extract_el(soup, value, ctx)
    uri = carrier_data_uri(ref.tag)
    if uri is None:
        raise NotMaterializable(
            f"el={ref.index} resolved to <{ref.tag.name}>, which carries no inline data: URI "
            f"— it is not a member and has no bytes to promote"
        )
    parsed = parse_data_uri(uri)
    if parsed is None:
        raise ValueError(f"el={ref.index} (<{ref.tag.name}>): unrecognized or undecodable data URI")
    return parsed


def el_member_filename(
    artifact_path: object, value: str, *, el_addressing: dict | None = None
) -> str | None:
    """*(3.8)* The member's own declared name at `el=<value>`, or None. Only an attachment
    link carries one (`Click to download <name>`); an inlined `<img>`/`<video>` is anonymous
    in the source and gets no invented name. Tolerant by design — a name is provenance, not
    identity, so a walk that fails yields None rather than blocking a promotion whose hash
    verifies."""
    from pathlib import Path as _Path

    try:
        soup = BeautifulSoup(_Path(str(artifact_path)).read_bytes(), EL_PARSER_ID)
        ctx: RenderContext = {}
        if el_addressing:
            ctx["el_addressing"] = el_addressing
        return attachment_filename(extract_el(soup, value, ctx).tag)
    except Exception:
        return None


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
        # A VECTOR image is not a broken image. PIL has no SVG rasterizer, so a perfectly
        # valid inline SVG lands here — and calling that "failed to decode" made two
        # records read as corrupt provenance for a whole arc when the bytes were fine
        # and the gap was ours. Distinguish by looking: a valid `<svg>` root means the
        # address names exactly what it says and only rasterization is missing
        # (NotMaterializable — declared coverage, not a defect); anything else really is
        # undecodable bytes and stays an error.
        if _is_svg_payload(raw):
            raise NotMaterializable(
                f"{selector_for_error}: the element is an inline SVG, which has no raster "
                f"rendering in this toolchain (no SVG rasterizer) — the bytes are valid "
                f"and the address names them correctly"
            ) from exc
        raise ValueError(
            f"failed to decode image bytes from data URI for {selector_for_error!r}: {exc}"
        ) from exc
    return img.convert("RGBA") if img.mode == "P" else img


def _is_svg_payload(raw: bytes) -> bool:
    """True when `raw` is a valid-looking SVG document — an `<svg` root within the leading
    bytes, tolerating an XML declaration, a DOCTYPE, comments, and a BOM."""
    head = raw[:4096].lstrip(b"\xef\xbb\xbf").lstrip()
    if not head.startswith(b"<"):
        return False
    return b"<svg" in head[:4096].lower()
