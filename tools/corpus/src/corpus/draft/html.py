"""HTML draft extraction (deterministic, no LLM).

Mechanical drafter. The drafter's job is to deliver the page's body as
cleaned HTML to the normalizer + a dedup'd embed manifest of every
inline image; the normalizer does all structural work (section
grouping, segment splitting, markdown rendering, embed-segment linking
via address membership).

The drafter is deliberately **mechanical** — it removes only
intrinsically non-rendered infrastructure and never drops a content-
bearing element by semantic/positional guess. A universal tool cannot
own a correct global definition of "what is chrome" (nav vs. content,
a real `<form>` vs. an ASP.NET WebForms page-wrapper, a decorative vs.
a meaningful aside), and getting it wrong drops content *silently*.
So **chrome removal is a capture-time, per-host concern**: declare the
selectors to delete in the origin overlay's `capture.interactions[].remove`
(or an `eval` step) — it runs in the live DOM before the snapshot, where
the site's actual structure is known. With no overlay, page chrome simply
leaks into the single text segment; the normalizer trims it. Better to
over-include than to silently drop.

Pipeline:

1. Parse the source HTML with BeautifulSoup (`html.parser`).
2. Extract metadata fields (`<title>` / og:title / og:description /
   description / `<html lang>` / og:site_name / canonical / capture-
   injected `corpus-capture-url` + `corpus-fetched-at`).
3. Detect bot-block / WAF challenge pages on the pre-strip soup.
4. Pre-walk the pre-strip work copy: assign 1-indexed `el=N` positions
   to every addressable element (`section`, `article`, `p`, `ul`, `ol`,
   `table`, `pre`, `blockquote`, `figure`, `h1`-`h6`, `img`) in
   document order. For each `<img>` decode its base64 `data:` URI to
   compute embed metadata (blake3 byte_hash, format, width, height,
   alt) and dedup by byte_hash into the embed manifest.
5. Strip non-rendered infrastructure ONLY: decompose `<script>` /
   `<style>` / `<noscript>` / `<template>` / `<link>` and HTML comments.
   No chrome/role/class heuristics — that is the capture layer's job.
6. Rewrite label/value div pairs as `<p><strong>Label:</strong> Value</p>`.
7. Collapse KaTeX (`<span class="katex">` and bare `<math>`) to LaTeX.
8. Annotate surviving addressable elements with `data-el="N"` and drop
   `<img src>`/`srcset` (the base64 URI is dead weight in the cleaned
   body; `data-el="N"` is the address — a consumer builds
   `corpus://<hash>?el=N` to fetch the bytes from the artifact).
9. Strip attributes (keep whitelist + global `id` + `data-el`).
10. Unwrap empty `<div>` / `<span>`.
11. Root is always `<body>`. Serialize.
12. Emit the embed manifest. Nothing content-bearing is stripped, so
    every inline image survives and is embedded.

Return: a `DrafterResult` — `fields` (record-level metadata), `embeds`
(dedup'd image-asset descriptor dicts), one `<!--segment text-->` whose
body is the cleaned HTML, `title`, drafter `issues`, and the
`blake3-canonical-html` `canonical` hash.

The normalizer reads that segment's body, parses it, decides section
structure, emits markdown segments with `address: el=N` (or `el=N-M`).
Image segments link to embeds by address membership — no explicit
embed-reference field.

The `el=N` index axis (assigned on the pre-strip artifact, parsed with
`html.parser`) MUST stay identical to the resolver's
`corpus.transforms.html` addressable-tag set / parser, or
`corpus://<hash>?el=N` resolution silently breaks (`test_drafters.py`
guards this).

Per spec §4.3 the body is faithful — no interpretation, no editorial.
"""

from __future__ import annotations

import base64
import io
import re
from pathlib import Path
from typing import Any

import blake3 as _blake3
from bs4 import BeautifulSoup, Comment, Tag
from PIL import Image

from corpus import content_hash, recordbuild, records, touches
from corpus.draft import DrafterResult, register
from corpus.fingerprint import algos_for_atom, text_fingerprints
from corpus.segments import Segment
from corpus.transforms.html import largest_img_src

# Tags whose entire subtree is removed before serialization — non-rendered
# infrastructure ONLY. These produce no rendered content in a saved snapshot,
# so removing them never drops anything a reader would see. The drafter does
# NOT remove page chrome (nav/header/footer/aside), interactive controls
# (form/button/input), or anything by ARIA role or class/id pattern: a
# universal tool cannot reliably tell chrome from content, and a wrong guess
# drops content silently (e.g. ASP.NET WebForms wraps the whole page in one
# `<form>`). Chrome removal is a capture-time, per-host concern — see the
# origin overlay's `capture.interactions[].remove`.
_STRIP_TAGS = {"script", "style", "noscript", "template", "link"}

# Block-level tags relevant to `_convert_field_pairs` heuristic.
_BLOCK_TAGS_FOR_FIELD_PAIRS = {
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "ul", "ol", "table", "pre", "blockquote", "figure",
}

# Attributes kept on surviving elements. Everything else (class, style,
# data-*, aria-*, role, tabindex, on*, etc.) is stripped — the cleaned
# HTML is meant to carry structure and content, not presentation.
# Note: `<img>` does NOT keep `src` — image bytes are addressed by
# `data-el="N"` against the artifact (the addressing scheme). The
# original base64 src would be huge dead weight in the cleaned body.
_KEEP_ATTRS: dict[str, set[str]] = {
    "a": {"href"},
    "img": {"alt"},
    "annotation": {"encoding"},  # KaTeX LaTeX annotation marker
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
    "ol": {"start", "type"},
    "li": {"value"},
    "html": {"lang"},
    "time": {"datetime"},
    "code": {"class"},  # syntax-highlight language class (e.g. language-python)
}
# `id` is kept globally — cross-reference anchors target ids on headings
# and definition-list items, and those links would otherwise dangle.
# `data-el` is the drafter's artifact-position annotation — the normalizer
# reads it as the address of each emitted segment.
_GLOBAL_KEEP_ATTRS = {"id", "data-el"}

# Tags that get an `el=N` index for spec §4.3 addressing. Single shared
# index axis across structural containers (`section`, `article`), prose
# blocks (`p`, `ul`, `ol`, `blockquote`), structured content (`table`,
# `pre`, `figure`), headings (`h1`-`h6`), and inline images (`img`).
# Layout-only wrappers (`div`, `span`) are NOT addressable — they're
# chrome the drafter unwraps anyway.
#
# MUST equal `corpus.transforms.html._ADDRESSABLE_TAGS` (the resolver's
# source of truth) — `test_drafters.py` asserts the two stay in lockstep.
_ADDRESSABLE_TAGS = (
    "section", "article", "p", "ul", "ol", "table",
    "pre", "blockquote", "figure",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "img",
)

# data URI parser for `<img src="data:image/png;base64,XXX">` shapes.
_DATA_URI_RE = re.compile(
    r"^data:([a-z0-9+./\-]+);base64,(.+)$", re.DOTALL | re.IGNORECASE
)
# SVG intrinsic-size parsing (PIL can't open SVG natively). Read the ROOT
# `<svg>` tag ONLY — scanning the whole document for `width=`/`height=` grabs
# the first inner element's size, a real bug seen on ALLDATA's ~600KB wiring
# SVGs, which declare no root size and yielded a bogus 100x100 from an inner
# element. Prefer integer root width/height, else the viewBox extent, else fall
# back (in the caller) to the <img>'s own width/height attributes.
_SVG_ROOT_RE = re.compile(rb"<svg\b[^>]*>", re.IGNORECASE | re.DOTALL)
_SVG_VIEWBOX_RE = re.compile(
    r'\bviewBox\s*=\s*["\']?\s*[-+0-9.eE]+[\s,]+[-+0-9.eE]+[\s,]+'
    r"([0-9.eE]+)[\s,]+([0-9.eE]+)",
    re.IGNORECASE,
)


def _len_attr(tag: str, name: str) -> int:
    """Integer pixel value of a length attribute (`width`/`height`) on a single
    tag string, or 0. Percentage values (`width="100%"`) return 0 — they're not
    intrinsic pixel sizes."""
    m = re.search(
        rf'\b{re.escape(name)}\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s/>]+))',
        tag,
        re.IGNORECASE,
    )
    if not m:
        return 0
    val = (m.group(1) or m.group(2) or m.group(3) or "").strip()
    if val.endswith("%"):
        return 0
    num = re.match(r"([0-9]+(?:\.[0-9]+)?)", val)
    return round(float(num.group(1))) if num else 0


def _svg_dimensions(raw: bytes) -> tuple[int, int]:
    """Best-effort intrinsic size of an SVG from its ROOT element only: prefer
    integer `width`/`height` (ignoring percentages), else the `viewBox` extent.
    Returns (0, 0) when the root declares no usable size — an honest 'unknown'
    beats a number scraped from a random inner element."""
    m = _SVG_ROOT_RE.search(raw)
    if not m:
        return 0, 0
    root = m.group(0).decode("utf-8", errors="ignore")
    w, h = _len_attr(root, "width"), _len_attr(root, "height")
    if w and h:
        return w, h
    vb = _SVG_VIEWBOX_RE.search(root)
    if vb:
        return round(float(vb.group(1))), round(float(vb.group(2)))
    return w, h


def _attr_px(tag: Tag, name: str) -> int:
    """Integer pixel value of a `width`/`height` attribute on a BeautifulSoup
    element, or 0 (percentages and non-numerics return 0). Reads the attribute
    directly rather than serializing the tag — `<img>` srcs can be 600KB+ data
    URIs."""
    val = str(tag.get(name) or "").strip()
    if not val or val.endswith("%"):
        return 0
    num = re.match(r"([0-9]+(?:\.[0-9]+)?)", val)
    return round(float(num.group(1))) if num else 0

# Wrapper tags whose semantic content is just markup grouping. After
# stripping their attributes they're indistinguishable from the parent
# flow; unwrap them so the resulting HTML doesn't carry hollow nesting.
# `<div>` and `<span>` are the big offenders in modern Tailwind / utility-
# CSS sites where every layout decision is a wrapping div. `<section>`
# is kept (semantic HTML5 sectioning) so the normalizer sees the page's
# author-asserted section structure.
_UNWRAP_TAGS = {"div", "span"}

# Bot-block / WAF challenge signatures. Each entry is (source_name, title_re,
# body_re). A match requires title_re to match the <title> text AND body_re to
# match somewhere in the rendered text. Both regexes are pre-compiled,
# case-insensitive. Keep signatures NARROW — we'd rather miss a block-page
# than misflag a legitimate page whose title happens to contain "Access
# Denied" or whose body mentions "Cloudflare" in passing.
_BLOCK_PAGE_SIGNATURES: tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...] = (
    (
        "Akamai",
        re.compile(r"^\s*access denied\s*$", re.IGNORECASE),
        re.compile(r"errors\.edgesuite\.net", re.IGNORECASE),
    ),
    (
        "Cloudflare",
        re.compile(r"attention required|cloudflare", re.IGNORECASE),
        re.compile(r"cf-error-details|Ray ID:\s*[0-9a-f]{12,}", re.IGNORECASE),
    ),
    (
        "Imperva",
        re.compile(r".", re.DOTALL),
        re.compile(r"Incapsula incident ID:\s*\d", re.IGNORECASE),
    ),
)

# Touch identifier for drafter-emitted issues (spec §4.3.3.1 `detector`).
# `corpus.draft.text/text_html@<version>` — matches the draft touch the CLI
# records, so issue provenance and the touch chain agree.
_DRAFTER_DETECTOR_ID = touches.script_identifier("draft.text/text_html")


@register("text/text_html")
def draft(
    html_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,
) -> DrafterResult:
    raw = html_path.read_bytes()
    text_algos = algos_for_atom("text", fingerprint)
    soup = BeautifulSoup(raw, "html.parser")

    fields: dict[str, Any] = {}
    title: str | None = None
    if v := _title(soup):
        fields["html_title"] = v
        title = v
    if v := _meta_description(soup):
        fields["html_description"] = v
    if v := _html_lang(soup):
        fields["html_lang"] = v
    if v := _og_site_name(soup):
        fields["og_site_name"] = v
    # URLs that ALIAS the captured origin — the page's self-declared canonical
    # (`<link rel=canonical>`) and the post-redirect final URL (the capture-injected
    # `corpus-capture-url` meta). These belong on the ORIGIN block's uri: list, not the
    # artifact block (spec §7.2 — canonical / shortlink / final URLs collapse into one
    # origin). `_apply_drafter_result` folds them in. `fetched_at` is already the origin
    # block's snapshot: (set at ingest), so the drafter doesn't re-emit it.
    origin_uri_aliases: list[str] = []
    if v := _canonical_url(soup):
        origin_uri_aliases.append(v)
    if v := _meta_content(soup, "corpus-capture-url"):
        origin_uri_aliases.append(v)

    issues: list[dict[str, Any]] = []
    if source := _detect_block_page(soup, title):
        issues.append(
            {
                "id": "bot-block",
                "severity": "blocking",
                "resolution": "open",
                "detector": _DRAFTER_DETECTOR_ID,
                "fields": {
                    "signature": source,
                    "description": (
                        f"Capture returned an {source} bot-block / WAF challenge page "
                        if source and source[:1].upper() in "AEIOU"
                        else f"Capture returned a {source} bot-block / WAF challenge page "
                    )
                    + "in place of the underlying content; the underlying URL was not retrieved.",
                    "remediation": "recapture_with_authenticated_session",
                },
            }
        )
    if issue := _detect_empty_body(soup):
        issues.append(issue)
    if issue := _detect_generic_title(title):
        issues.append(issue)
    if issue := _detect_noscript_heavy(soup):
        issues.append(issue)
    if issue := _detect_charset_mismatch(raw):
        issues.append(issue)

    cleaned_html, _root_selector, embeds, max_el = _clean_html(
        soup, record_id=record_id
    )

    segments: list[Segment]
    if cleaned_html:
        # The wrapping cleaned-HTML segment spans every addressable
        # element in the source artifact (some may have been chrome-
        # stripped — gaps in the range are expected). The normalizer
        # later breaks this into precise sub-ranges addressed by
        # `el=N` or `el=N-M` per the html schema's structural-recovery
        # guidance.
        wrapper_address = f"el=1-{max_el}" if max_el >= 1 else "el=1"
        segments = [
            Segment(
                atom="text",
                address=wrapper_address,
                perceptual=text_fingerprints(cleaned_html, text_algos),
                body=cleaned_html,
            )
        ]
    else:
        segments = []

    # Canonical hash per the mime schema's `canonical_strategy.algo`
    # (`blake3-canonical-html` — drop <script>/<style>/<svg>, collapse
    # whitespace, blake3); the strategy id encodes its hash family
    # (`blake3-canonical-html` → `blake3:`). Falls back to the HTML
    # default when the schema/caller doesn't override it.
    algo = canonical_algo or "blake3-canonical-html"
    canonical = records.format_hash(
        algo.split("-", 1)[0], content_hash.compute(algo, html_path)
    )

    recordbuild.add_blocks(build, segments)
    return {
        "fields": fields,
        "embeds": embeds,
        "title": title,
        "issues": issues,
        "canonical": canonical,
        "origin_uri_aliases": origin_uri_aliases,
    }


def _clean_html(
    soup: BeautifulSoup, *, record_id: str | None = None
) -> tuple[str, str, list[dict[str, Any]], int]:
    """Strip chrome from a fresh parse of `soup`, serialize the chosen
    root, and return (cleaned_html, root_selector, embeds, max_el).

    `max_el` is the highest `data-el="N"` index assigned (== the count
    of addressable elements in the original artifact). The wrapping
    text segment's address is `el=1-<max_el>` — a range that spans
    every addressable element so the normalizer can later break it
    into precise sub-ranges.

    Operates on a fresh re-parse so the caller's `soup` (used for block-
    page detection) is unaffected. When `record_id` is provided:

    - Every addressable element gets a `data-el="N"` annotation with its
      1-indexed position in the raw artifact (assigned BEFORE chrome
      strip, so positions are stable against the immutable artifact).
    - `<img>` tags additionally have their bloated base64 `data:` URIs
      stripped — the addressing scheme (`data-el="N"`) is all a consumer
      needs to construct a `corpus://<hash>?el=N` URI on demand.
    - A dedup'd image-embed manifest is returned: one embed dict per
      unique content (byte_hash), with `address` listing every `el=N`
      where those bytes appear (scalar when 1, list when 2+).
    """
    work = BeautifulSoup(str(soup), "html.parser")

    # Pre-pass against pre-strip work: assign el-indices to every
    # addressable element, and compute embed metadata for every <img>
    # with a usable base64 data URI. The work DOM is identical to the
    # source artifact at this point — positions are stable. Chrome
    # strip below removes some elements (decomposed addressable tags
    # lose their indices); annotation walks surviving tags by id().
    el_index_by_id: dict[int, int] = {}
    embed_by_hash: dict[str, dict[str, Any]] = {}
    if record_id:
        for n, tag in enumerate(work.find_all(_ADDRESSABLE_TAGS), start=1):
            if not isinstance(tag, Tag):
                continue
            el_index_by_id[id(tag)] = n
            if tag.name == "img":
                meta = _compute_img_embed_metadata(tag)
                if meta is None:
                    continue
                byte_hash = meta["byte_hash"]
                addr = f"el={n}"
                if byte_hash in embed_by_hash:
                    embed_by_hash[byte_hash]["addresses"].append(addr)
                else:
                    embed_by_hash[byte_hash] = {
                        "media_type": meta["media_type"],
                        "addresses": [addr],
                        "width": meta["width"],
                        "height": meta["height"],
                        "alt": meta["alt"],
                    }

    # Strip non-rendered infrastructure only (script/style/noscript/template/
    # link). No chrome/role/class heuristics — chrome removal is a capture-time,
    # per-host concern (origin overlay `capture.interactions[].remove`).
    for tag in work.find_all(_STRIP_TAGS):
        tag.decompose()

    _convert_field_pairs(work)
    _collapse_katex(work)
    _strip_comments(work)
    if record_id:
        _annotate_addressable(work, el_index_by_id)
    _strip_attrs(work)
    _unwrap_empty_wrappers(work)

    # Root is always <body> — the drafter does not guess a content root.
    root = work.find("body") or work
    if not isinstance(root, Tag):
        return "", "", [], 0

    max_el = max(el_index_by_id.values()) if el_index_by_id else 0
    embeds = _materialize_embeds(work, el_index_by_id, embed_by_hash) if record_id else []
    return (
        _collapse_excess_newlines(str(root)),
        _css_selector(root),
        embeds,
        max_el,
    )


def _annotate_addressable(
    work: BeautifulSoup, el_index_by_id: dict[int, int]
) -> None:
    """In-place: add `data-el="N"` to every surviving addressable
    element. N is the element's pre-strip artifact-order index, looked
    up from `el_index_by_id` by `id(tag)` — stable through chrome
    strip for surviving tags.

    For `<img>` tags, also drop `src` and `srcset` — the original base64
    `data:` URI is huge dead weight in the cleaned body, and the
    addressing scheme (`data-el="N"`) is all a consumer needs to
    construct a `corpus://<hash>?el=N` URI when it wants to fetch the
    bytes."""
    for tag in work.find_all(_ADDRESSABLE_TAGS):
        if not isinstance(tag, Tag):
            continue
        idx = el_index_by_id.get(id(tag))
        if not idx:
            continue
        tag["data-el"] = str(idx)
        if tag.name == "img":
            if "src" in tag.attrs:
                del tag.attrs["src"]
            if "srcset" in tag.attrs:
                del tag.attrs["srcset"]


def _materialize_embeds(
    work: BeautifulSoup,
    el_index_by_id: dict[int, int],
    embed_by_hash: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filter the pre-strip embed manifest down to embeds whose imgs
    survived chrome strip, then convert each entry to an embed dict
    (`{media_type, address, transport, fields}`, the shape
    `records.append_embed_block` consumes). Collapses single-entry
    `addresses` lists to scalar `address` per the polymorphic
    str | list[str] convention (spec §4.3)."""
    surviving_img_addresses: set[str] = set()
    for img in work.find_all("img"):
        if not isinstance(img, Tag):
            continue
        idx = el_index_by_id.get(id(img))
        if idx:
            surviving_img_addresses.add(f"el={idx}")

    out: list[dict[str, Any]] = []
    for byte_hash, meta in embed_by_hash.items():
        kept = [a for a in meta["addresses"] if a in surviving_img_addresses]
        if not kept:
            continue
        address: str | list[str] = kept[0] if len(kept) == 1 else kept
        extra: dict[str, Any] = {
            "width": meta["width"],
            "height": meta["height"],
        }
        if meta.get("alt"):
            extra["alt"] = meta["alt"]
        out.append(
            {
                "media_type": meta["media_type"],
                "address": address,
                "transport": f"blake3:{byte_hash}",
                "fields": extra,
            }
        )
    return out


def _compute_img_embed_metadata(img: Tag) -> dict[str, Any] | None:
    """Decode an `<img>`'s base64 `data:` URI; return `{media_type,
    byte_hash, width, height, alt}` or None if the src is missing /
    empty / unparseable. Empty `data:,` placeholders return None.

    `byte_hash` is the full 64-char blake3 hexdigest of the decoded
    bytes (the `transport`/dedup key, matching the artifact-identity
    hash convention). `width`/`height` come from PIL.Image.open for
    raster formats; for SVG we fall back to parsing `width=`/`height=`
    attributes from the SVG XML (PIL can't open SVG natively).

    Reads the highest-resolution inline source (largest `srcset` candidate, else
    `src`) via `largest_img_src` — the same selection the `el=` resolver uses, so the
    embed's hash/dims match what `corpus://<hash>?el=N` materialises."""
    src = (largest_img_src(img) or "").strip()
    if not src.startswith("data:") or src == "data:,":
        return None
    m = _DATA_URI_RE.match(src)
    if not m:
        return None
    media_type = m.group(1).lower()
    try:
        raw = base64.b64decode(m.group(2))
    except Exception:
        return None
    if not raw:
        return None
    byte_hash = _blake3.blake3(raw).hexdigest()  # full 64-char blake3
    width = height = 0
    try:
        with Image.open(io.BytesIO(raw)) as im:
            width, height = im.size
    except Exception:
        if media_type == "image/svg+xml":
            width, height = _svg_dimensions(raw)
            # Last resort: the <img>'s own declared pixel size. ALLDATA's
            # interactive wiring SVGs declare no root size but the host stamps
            # width/height on the <img> (e.g. 725x900), which is the real
            # display size.
            if not width:
                width = _attr_px(img, "width")
            if not height:
                height = _attr_px(img, "height")
    alt = str(img.get("alt") or "").strip()
    return {
        "media_type": media_type,
        "byte_hash": byte_hash,
        "width": width,
        "height": height,
        "alt": alt,
    }


def _collapse_katex(work: BeautifulSoup) -> None:
    """In-place: replace every `<span class="katex">` wrapper (and bare
    `<math>` element when not wrapped) with its LaTeX source extracted
    from the `<annotation encoding="application/x-tex">` descendant.
    Renders as `$...$` for inline equations and `$$...$$` for display
    equations.

    KaTeX emits a triple representation per equation: visible MathML +
    Unicode fallback + the LaTeX annotation. The MathML alone can be
    hundreds of nested tags per equation; for a page like the Isometric
    River Alkalinity protocol with dozens of equations, the MathML
    tree dominates the byte budget. The LaTeX annotation is the
    faithful source; emit just that and drop the visible-rendering
    siblings."""
    # Replace `<span class="katex">` wrappers.
    for katex_span in list(work.select("span.katex")):
        annotation = katex_span.find("annotation", encoding="application/x-tex")
        math = katex_span.find("math")
        is_display = math is not None and (math.get("display") == "block")
        if annotation is not None and annotation.string:
            latex = annotation.string.strip()
            wrapper = "$$" if is_display else "$"
            katex_span.replace_with(f"{wrapper}{latex}{wrapper}")
        else:
            # No LaTeX annotation — fall back to the MathML text content.
            katex_span.replace_with(katex_span.get_text(" ", strip=True))
    # Also handle bare `<math>` elements (sometimes appear without a
    # wrapping span — copy/paste fragments, alternative renderers).
    for math in list(work.find_all("math")):
        annotation = math.find("annotation", encoding="application/x-tex")
        is_display = math.get("display") == "block"
        if annotation is not None and annotation.string:
            latex = annotation.string.strip()
            wrapper = "$$" if is_display else "$"
            math.replace_with(f"{wrapper}{latex}{wrapper}")
        else:
            math.replace_with(math.get_text(" ", strip=True))


def _strip_comments(work: BeautifulSoup) -> None:
    """Remove all HTML comments (`<!-- ... -->`). SingleFile captures
    inline comments noting hydration boundaries (`<!--$-->`, `<!--/$-->`),
    React-Server-Components markers, and similar framework noise. None
    of it is content."""
    for c in list(work.find_all(string=lambda s: isinstance(s, Comment))):
        c.extract()


def _strip_attrs(work: BeautifulSoup) -> None:
    """In-place: drop every attribute on every surviving tag except the
    per-tag whitelist in `_KEEP_ATTRS` plus the global `id`/`data-el`.
    After this pass, surviving elements carry only semantically
    meaningful attributes: `href` on links, `alt` on images, `colspan`/
    `rowspan` on table cells, `lang` on `<html>`, etc."""
    for tag in work.find_all(True):
        if not isinstance(tag, Tag) or not tag.attrs:
            continue
        keep = _KEEP_ATTRS.get(tag.name, set()) | _GLOBAL_KEEP_ATTRS
        for attr_name in list(tag.attrs.keys()):
            if attr_name not in keep:
                del tag.attrs[attr_name]


def _unwrap_empty_wrappers(work: BeautifulSoup) -> None:
    """In-place: unwrap `<div>` and `<span>` elements that carry no
    surviving attributes. After `_strip_attrs` they're pure layout
    husks with no semantic content — flatten them so the resulting
    HTML reflects only structural intent.

    Iterates breadth-first because unwrapping a div can expose nested
    divs that should also unwrap. `unwrap()` is safe to call on
    elements still in the tree; BeautifulSoup re-parents children to
    the grandparent.

    `<section>` is intentionally NOT unwrapped — semantic HTML5
    sectioning carries the page's author-asserted section structure
    even when its class attributes were Tailwind chrome."""
    # Repeat until no changes — each pass can expose new candidates.
    while True:
        candidates = [
            t for t in work.find_all(True)
            if isinstance(t, Tag) and t.name in _UNWRAP_TAGS and not t.attrs
        ]
        if not candidates:
            break
        for t in candidates:
            t.unwrap()


_WHITESPACE_PRESERVE_PATTERN = re.compile(
    r"<(pre|code|textarea)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_EXCESS_NEWLINE_PATTERN = re.compile(r"\n{3,}")


def _collapse_excess_newlines(html: str) -> str:
    """Collapse runs of 3+ consecutive newlines in the serialized cleaned
    HTML down to a single blank line (`\\n\\n`). Chrome-strip passes leave
    orphan whitespace text nodes around removed elements; those individual
    nodes each look fine (`\\n`), but they concatenate at serialization
    into multi-blank-line gaps. Operating on the serialized string is the
    only way to see the concatenated runs.

    Preserves whitespace inside `<pre>` / `<code>` / `<textarea>` blocks
    where it is semantically significant. Carves those blocks out with
    placeholders, runs the collapse on the rest, then restores."""
    if "\n\n\n" not in html:
        return html
    preserved: list[str] = []
    sentinel = "\x00CORPUS_WS_PRESERVE_"

    def _stash(match: re.Match[str]) -> str:
        preserved.append(match.group(0))
        return f"{sentinel}{len(preserved) - 1}\x00"

    work = _WHITESPACE_PRESERVE_PATTERN.sub(_stash, html)
    work = _EXCESS_NEWLINE_PATTERN.sub("\n\n", work)
    if not preserved:
        return work
    return re.sub(
        re.escape(sentinel) + r"(\d+)\x00",
        lambda m: preserved[int(m.group(1))],
        work,
    )


def _detect_block_page(soup: BeautifulSoup, title: str | None) -> str | None:
    """Return the block-source name (e.g. 'Akamai') when the page matches a
    known bot-block / WAF challenge signature. Returns None otherwise.

    Operates on the full pre-strip soup so signatures see the block-page
    chrome before the structural walk decomposes it. Both the title regex
    AND the body regex must match for a signature to fire — false-positive
    aversion is the design priority. Body text is the soup's text content
    (post-tag-stripping by BeautifulSoup), with whitespace collapsed."""
    title_text = (title or "").strip()
    body_text = " ".join((soup.get_text(separator=" ") or "").split())
    for source, title_re, body_re in _BLOCK_PAGE_SIGNATURES:
        if title_re.search(title_text) and body_re.search(body_text):
            return source
    return None


def _detect_empty_body(soup: BeautifulSoup) -> dict[str, Any] | None:
    """Emit `partial-content/empty-body` when `<body>` contains no visible
    content. "Visible" here means: stripped of `<script>`/`<style>`/comments,
    the remaining text is empty AND there are no media elements
    (`<img>`/`<video>`/`<audio>`/`<svg>`/`<canvas>`). A page can validly
    consist of only an image (e.g. an infographic record), so we only fire
    when both text AND media are absent."""
    body = soup.find("body")
    if body is None:
        # No <body> at all — fragment, error stub, or stripped artifact.
        # Don't fire; the parent page may have been minimal HTML by design.
        return None
    # Clone and prune; we don't want to mutate the live soup.
    work = BeautifulSoup(str(body), "html.parser")
    for tag in work.find_all(["script", "style", "noscript"]):
        tag.decompose()
    text = " ".join((work.get_text(separator=" ") or "").split())
    if text:
        return None
    if work.find(["img", "video", "audio", "svg", "canvas", "iframe", "embed", "object"]):
        return None
    return {
        "id": "partial-content",
        "subtype": "empty-body",
        "severity": "blocking",
        "resolution": "open",
        "detector": _DRAFTER_DETECTOR_ID,
        "fields": {
            "description": (
                "Parsed <body> contained no visible text and no media elements "
                "after stripping script/style/noscript."
            ),
        },
    }


def _detect_generic_title(title: str | None) -> dict[str, Any] | None:
    """Emit `generic-title` when the title is a known placeholder /
    loading-state / empty value rather than article content."""
    from corpus.quality.signatures import GENERIC_TITLE_PATTERNS

    raw = (title or "").strip()
    for name, regex in GENERIC_TITLE_PATTERNS:
        if regex.match(raw):
            return {
                "id": "generic-title",
                "severity": "warning",
                "resolution": "open",
                "detector": _DRAFTER_DETECTOR_ID,
                "fields": {
                    "signature": name,
                    "title": raw[:200],
                },
            }
    return None


def _detect_noscript_heavy(soup: BeautifulSoup) -> dict[str, Any] | None:
    """Emit `noscript-heavy` when the page's primary visible text lives in
    `<noscript>` fallback blocks (i.e. JS-required page that didn't render
    on capture). Fires when noscript text exceeds 50% of total visible text
    and noscript text is at least 200 chars (so a single small `<noscript>`
    fallback doesn't trip on a normal page)."""
    noscript_text = " ".join(
        " ".join(tag.get_text(separator=" ").split())
        for tag in soup.find_all("noscript")
    ).strip()
    if len(noscript_text) < 200:
        return None
    # Clone and remove the noscript blocks to measure non-noscript text.
    work = BeautifulSoup(str(soup), "html.parser")
    for tag in work.find_all(["script", "style", "noscript"]):
        tag.decompose()
    rest_text = " ".join((work.get_text(separator=" ") or "").split())
    total = len(noscript_text) + len(rest_text)
    if total == 0 or len(noscript_text) / total <= 0.50:
        return None
    return {
        "id": "noscript-heavy",
        "severity": "warning",
        "resolution": "open",
        "detector": _DRAFTER_DETECTOR_ID,
        "fields": {
            "noscript_chars": len(noscript_text),
            "rest_chars": len(rest_text),
            "noscript_ratio": round(len(noscript_text) / total, 3),
        },
    }


def _detect_charset_mismatch(raw_bytes: bytes) -> dict[str, Any] | None:
    """Emit `encoding-corruption/charset-mismatch` when the decoded bytes
    contain common UTF-8 misdecode signatures (Ã©, â€™, etc.) — text that
    was probably encoded as UTF-8 but read as Latin-1/cp1252 somewhere in
    the pipeline. Fires when 3+ distinct signatures appear (single matches
    can be coincidence — e.g. a French legal citation containing "déjà"
    that happens to render correctly)."""
    from corpus.quality.signatures import MOJIBAKE_SIGNATURES

    try:
        text = raw_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return None
    hits: list[str] = []
    for sig in MOJIBAKE_SIGNATURES:
        if sig in text:
            hits.append(sig)
    if len(hits) < 3:
        return None
    return {
        "id": "encoding-corruption",
        "subtype": "charset-mismatch",
        "severity": "warning",
        "resolution": "open",
        "detector": _DRAFTER_DETECTOR_ID,
        "fields": {
            "signatures_matched": hits[:10],
            "distinct_signature_count": len(hits),
        },
    }


def _convert_field_pairs(work: BeautifulSoup) -> None:
    """In-place: detect the `<div><div>Label</div><div>Value</div></div>`
    label/value pattern (common in CMS-driven directory pages where the
    author chose nested divs instead of `<dl>`/`<dt>`/`<dd>`) and
    rewrite each match as a `<p><strong>Label:</strong> Value</p>`.

    Without this pre-walk, the normalizer would need to recognize this
    div-pair pattern itself; rewriting at draft time normalizes the
    structure so the normalizer sees ordinary prose.

    Pattern criteria (all required):
    - parent has exactly 2 direct-child elements
    - both children are `<div>`
    - neither child has descendant block-level tags (so it's a leaf
      content container, not a structural wrapper)
    - both children have non-empty stripped text

    Matches typical SCC accreditation directory entries (the
    `field-container` class), and similar CMS / Webflow directory
    layouts. Doesn't match nested-div containers used for layout
    (those usually have lots of children, complex descendants, or
    one of the two children is empty)."""
    for div in list(work.find_all("div")):
        children = [c for c in div.children if isinstance(c, Tag)]
        if len(children) != 2:
            continue
        label_div, value_div = children
        if label_div.name != "div" or value_div.name != "div":
            continue
        if label_div.find(_BLOCK_TAGS_FOR_FIELD_PAIRS) is not None:
            continue
        if value_div.find(_BLOCK_TAGS_FOR_FIELD_PAIRS) is not None:
            continue
        label_text = label_div.get_text(separator=" ", strip=True)
        value_text = value_div.get_text(separator=" ", strip=True)
        if not label_text or not value_text:
            continue
        new_p = work.new_tag("p")
        strong = work.new_tag("strong")
        strong.string = f"{label_text}:"
        new_p.append(strong)
        new_p.append(f" {value_text}")
        div.replace_with(new_p)


def _css_selector(tag: Tag) -> str:
    """Return a CSS-selector path identifying `tag` within the document.
    Walks up from the tag to the document root, recording each ancestor's
    tag name plus an `:nth-of-type(n)` suffix when needed for sibling
    disambiguation. The `<html>` tag (and the BeautifulSoup `[document]`
    pseudo-root) are not included in the path."""
    parts: list[str] = []
    cur: Tag | None = tag
    while cur is not None and cur.name not in (None, "[document]", "html"):
        siblings_same_tag = [
            s for s in cur.parent.find_all(cur.name, recursive=False)
        ] if cur.parent else [cur]
        if len(siblings_same_tag) > 1:
            idx = siblings_same_tag.index(cur) + 1
            parts.append(f"{cur.name}:nth-of-type({idx})")
        else:
            parts.append(cur.name)
        cur = cur.parent if isinstance(cur.parent, Tag) else None
    return ">".join(reversed(parts))


# ---------- metadata helpers ---------- #


# og:title is usually the clean human headline, but some sites put a generic
# social-share CTA there ("Check out this listing") while the page's real title
# lives in <title> — prefer <title> in that case. Anchored at the start; the
# trailing noun varies.
_SHARE_CTA_TITLE_RE = re.compile(r"^\s*check\s+out\s+(?:this|the|my|our)\b", re.IGNORECASE)


def _is_generic_title(title: str | None) -> bool:
    """True when `title` is uninformative — a placeholder/loading/error value
    (GENERIC_TITLE_PATTERNS) or a generic social-share CTA — rather than the
    page's real title. Used to decide og:title vs <title> preference."""
    from corpus.quality.signatures import GENERIC_TITLE_PATTERNS

    raw = (title or "").strip()
    if _SHARE_CTA_TITLE_RE.match(raw):
        return True
    return any(regex.match(raw) for _name, regex in GENERIC_TITLE_PATTERNS)


def _title(soup: BeautifulSoup) -> str:
    """Best available document title. Prefer og:title (usually the clean human
    headline); fall back to the <title> tag when og:title is generic — a
    placeholder or a social-share CTA (e.g. realtor.ca's "Check out this
    listing", whose <title> carries the real address). Last resort: whichever
    is non-empty."""
    og = _meta_content(soup, prop="og:title")
    title_tag = ""
    if (tag := soup.find("title")) and tag.string:
        title_tag = tag.string.strip()
    for candidate in (og, title_tag):
        if candidate and not _is_generic_title(candidate):
            return candidate
    return og or title_tag


def _meta_description(soup: BeautifulSoup) -> str:
    return _meta_content(soup, "description") or _meta_content(soup, prop="og:description")


def _html_lang(soup: BeautifulSoup) -> str:
    if (tag := soup.find("html")) and (lang := tag.get("lang")):
        return str(lang).strip()
    return ""


def _canonical_url(soup: BeautifulSoup) -> str:
    if tag := soup.find("link", rel="canonical"):
        return str(tag.get("href", "")).strip()
    return ""


def _og_site_name(soup: BeautifulSoup) -> str:
    return _meta_content(soup, prop="og:site_name")


def _meta_content(soup: BeautifulSoup, name: str | None = None, *, prop: str | None = None) -> str:
    if name and (tag := soup.find("meta", attrs={"name": name})):
        return str(tag.get("content", "")).strip()
    if prop and (tag := soup.find("meta", attrs={"property": prop})):
        return str(tag.get("content", "")).strip()
    return ""
