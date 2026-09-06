"""HTML transforms.

- `el=<N>` (HTML → htmlel) *(v35, §6.1.1)* — the element named by its 1-based
  document-order ordinal (a depth-first pre-order walk from the artifact's body),
  selected as an `HtmlElRef`. **Three grammar generations, dispatched by the record's
  `addressing:` stamp (§7.1), never by the value**: `scheme: ordinal` is the current
  ordinal space (`iter_elements_preorder` / `resolve_ordinal`, below); a stamp WITHOUT
  the key is the FROZEN 3.6 dotted child-index path (`element_path` /
  `resolve_element_path`); no stamp at all is the FROZEN pre-3.6 filtered index
  (`legacy_is_addressable`, below). A *terminal* `el=` materializes the element's
  inline bytes: an `<img>` decodes + renders to a PIL image (cache: PNG); a
  `<video>`/`<audio>` or `<a href="data:…">` attachment decodes to raw bytes (cache:
  the media's native extension). An image-output op after `el=` (`bbox`/`mark`/`fit`/…)
  auto-promotes the `<img>` to an image first (non-image carriers cannot promote).
- `selector=<css>` (HTML → image) — CSS selector identifying a single `<img>`;
  decodes its data URI. Back-compat with earlier records.
- `text` (HTML → text) and `el=<N>&text` (htmlel → text) *(v43, §6.2)* — the markup's
  own text reduction (`html_text`, below): document order, block-level elements and
  `<br>` as line breaks, table cells tab-separated, `<head>`/`<script>`/`<style>`/
  `<template>` dropped, whitespace normalized. Nothing removed on judgment — no chrome
  strip, no quote trim (that is `emlfile.body_text`'s job, deliberately separate) — and
  never a rendering. Unversioned like the PDF text layer's `page=<N>&text`.
- `cid:` carriers *(v43, §6.2 intra-container references)* — an `<img src="cid:…">`
  (or a `<video>`/`<audio>`/`<a>` whose source is a `cid:` URI) in MESSAGE-BORNE HTML
  names a sibling MIME part by Content-ID (RFC 2392). It materializes through the
  enclosing message the `part=` handler left in the context (`ctx["cid_source"]`,
  `emlfile.part_by_content_id`), never by inlining; with no enclosing message the
  reference is a hard error naming the missing part.

Inline media (every carrier) lives in the HTML as a base64 `data:` URI — `<img src>` /
`srcset`, a `<video>`/`<audio>`'s `<source src>` (or own `src`), or an attachment
`<a href>`. The drafter (`corpus.draft.html`) addresses each carrier by its `el=`
ordinal and the resolver re-materializes its bytes here. What the two share is the
ordinal walk itself (`iter_elements_preorder` / `element_ordinal` / `resolve_ordinal`)
and the carrier→data-URI map (`carrier_data_uri`) — there is no membership predicate to
drift, which is the 3.6 amendment's substance (§12.28), carried forward by v35's own
"one shared implementation" of the ordinal walk.

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
from bs4.element import CData, Comment, Declaration, Doctype, NavigableString, ProcessingInstruction
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

#: *(v35)* The ordinal address space's own pin — a NEW id, never a silent reinterpretation of
#: `@2`'s already-resolved (and cited) results: `el=5` means a different element under the two
#: grammars, so a URI that happens to collide across them (same hash, same value — impossible in
#: practice since a record carries exactly one scheme, §6.1.1) must never share a cache entry.
#: Selected per RECORD, never per value — `engine_version_for_addressing`, below.
ENGINE_VERSION_ORDINAL = "html-el@3"


def engine_version_for_addressing(el_addressing: dict | None) -> str:
    """The `html-el@` cache-key pin for the record's el= grammar generation (§6.1.1 dispatch,
    v35): `ENGINE_VERSION_ORDINAL` for an `addressing.scheme: ordinal` stamp, `ENGINE_VERSION`
    (the frozen `@2`) for the dotted-path and legacy-whitelist branches alike — both keep the
    cache identity they always had, since neither's resolution logic changed. The grammar is
    record-owned, not value-sniffed, so this reads the stamp rather than the URI."""
    if el_addressing and el_addressing.get("scheme") == "ordinal":
        return ENGINE_VERSION_ORDINAL
    return ENGINE_VERSION

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


# ---------- the el= ordinal walk (v35, spec §6.1.1) ---------- #
#
# The one shared implementation of the ordinal address space: the drafter computes ordinals
# with it, the resolver walks them back with it, and envelope derivation (`corpus.segments`)
# tests containment/siblinghood through it. Unlike the dotted path, an ordinal carries no
# containment algebra of its own (CHANGELOG v35: "not decidable from two addresses alone") —
# every relation question here reads the tree.


def iter_elements_preorder(root: Tag) -> list[Tag]:
    """Every element under `root`, in document order (depth-first pre-order) — the walk the
    ordinal address space is a 1-based position in (§6.1.1). `root` itself is excluded (the
    root has no ordinal, mirroring `element_path`'s root rule). BeautifulSoup's
    `find_all(True)` already walks in document order, so this is that call, named for what
    it means here — the shared basis `total_element_count` also reads, scoped to `root`
    rather than the whole document."""
    return root.find_all(True)


def element_ordinal(tag: Tag, root: Tag) -> int | None:
    """`tag`'s 1-based document-order ordinal under `root` (§6.1.1), or None when `tag` is
    not under `root` (or IS `root` — the root has no ordinal). Identity comparison (`is`),
    since BeautifulSoup tags compare structurally under `==`."""
    for i, t in enumerate(iter_elements_preorder(root), start=1):
        if t is tag:
            return i
    return None


def element_ordinals(root: Tag) -> dict[int, int]:
    """`id(tag) -> ordinal` for every element under `root`, computed in one walk — for a
    caller (the drafter) that needs many elements' ordinals rather than paying
    `element_ordinal`'s per-call walk once per element."""
    return {id(t): i for i, t in enumerate(iter_elements_preorder(root), start=1)}


def resolve_ordinal(root: Tag, n: int) -> Tag:
    """The element named by ordinal `n` under `root` (§6.1.1). Raises `ValueError` naming the
    walk length — bounds are a property of the ADDRESS (the `parse_index_span` lesson), so a
    sibling-range address's endpoints are bounds-checked here too, before anything asks
    whether they are siblings."""
    elements = iter_elements_preorder(root)
    if n < 1 or n > len(elements):
        raise ValueError(
            f"el={n}: out of range (the walk from <{root.name}> yields {len(elements)} "
            f"elements)"
        )
    return elements[n - 1]


def ordinal_interval(tag: Tag, root: Tag) -> tuple[int, int] | None:
    """`tag`'s subtree as an inclusive ordinal interval `(start, end)` under `root` (§6.1.1)
    — a subtree occupies a CONTIGUOUS ordinal run by construction of the pre-order walk, so
    `end` is `start` plus `tag`'s own element-descendant count. None when `tag` is not under
    `root`."""
    start = element_ordinal(tag, root)
    if start is None:
        return None
    return start, start + len(tag.find_all(True))


def ordinals_are_siblings(root: Tag, a: int, b: int) -> bool:
    """Whether ordinals `a` and `b` name elements that share a parent element (§6.1.1's
    sibling-range constraint) — a property of the parsed tree, never decidable from the two
    numbers alone (the v35 trade, CHANGELOG). Bounds-checks both via `resolve_ordinal`
    first, exactly as a point ordinal is bounds-checked."""
    ta, tb = resolve_ordinal(root, a), resolve_ordinal(root, b)
    return ta.parent is tb.parent


# ---------- the annotated view: a span-surgical byte splice (v35, §6.1.1/§6.2) ---------- #
#
# "Ordinals are counted by machines, never by eyes." The annotated view is the artifact's
# own bytes with `data-el="<N>"` spliced into every addressable element's own start tag —
# never a re-parse/re-serialization, which would renormalize quoting/entities and break the
# faithfulness ruling (the `jsonfields.strip_fields` discipline, applied here to insertion
# instead of removal). `html.parser` (fed the exact bytes BeautifulSoup decoded them as)
# stamps `sourceline`/`sourcepos` on every tag at parse time — the position of its opening
# `<`, as a (1-based line, 0-based CHARACTER column) pair in the DECODED text. Recovering a
# BYTE offset in the ORIGINAL bytes from that pair requires re-encoding under the exact same
# codec BeautifulSoup decoded with (`soup.original_encoding`); every computed offset is then
# verified against the raw bytes before it is trusted — a mismatch is a hard error, never a
# silent skip, because a partial annotation would invite exactly the guessing this surface
# exists to end.


class AnnotationError(ValueError):
    """The splice could not be proven correct against the raw bytes — a foreign encoding
    guess, a parser-implied element with no source position, or an offset that does not
    land on the element's own start tag. Raised rather than guessed around."""


def annotate_bytes(raw: bytes, soup: BeautifulSoup, root: Tag) -> bytes:
    """The annotated view (§6.1.1, v35): `raw` with ` data-el="<N>"` spliced into every
    element under `root`'s own start tag, immediately after the tag name — before any
    attributes the source already carries. A pure function of `(raw, the attested parse)`,
    provable by re-derivation: stripping exactly the injected spans recovers `raw`
    byte-for-byte.

    If a source element already carries its own `data-el` attribute, that attribute STAYS
    in the bytes (faithfulness — nothing is deleted); the injected one lands FIRST, right
    after the tag name. NOTE (measured, not the naive assumption): under THIS toolchain's
    attested parser (`html.parser`, via BeautifulSoup's `dict(attrs)` construction), a
    duplicate attribute resolves LAST-wins, not first — so a source element that already
    happens to carry `data-el` will show ITS OWN value, not ours, if the annotated bytes
    are re-parsed and a consumer reads `data-el` directly off the DOM. The byte-level
    faithfulness guarantee (nothing the source wrote is ever deleted, and ours is always
    present) holds regardless of which duplicate a given parser prefers; a reader that
    needs the authoritative ordinal must resolve it via the shared walk
    (`resolve_ordinal`/`element_ordinal`), never by trusting a `data-el` value read back
    off arbitrary re-parsed HTML.

    Raises `AnnotationError` — naming the offending element — when a splice point cannot be
    proven correct: no source position at all (a parser-implied element; `html.parser`
    rarely implies one, but nothing here assumes it never will), or the computed byte offset
    does not land on `<` followed by the element's own tag name in `raw`."""
    encoding = soup.original_encoding or "utf-8"
    try:
        text = raw.decode(encoding)
    except (LookupError, UnicodeDecodeError) as exc:
        raise AnnotationError(
            f"cannot annotate: the raw artifact does not decode cleanly under the parse's "
            f"own encoding ({encoding!r}): {exc}"
        ) from exc

    lines = text.split("\n")
    newline_bytes = len("\n".encode(encoding))
    line_byte_start = [0]
    for line in lines[:-1]:
        line_byte_start.append(line_byte_start[-1] + len(line.encode(encoding)) + newline_bytes)

    # Per-line character->byte cumulative offset, built lazily (only for lines an element
    # actually starts on) and reused across every tag on that line — O(document length)
    # overall rather than O(elements x line length).
    col_cache: dict[int, list[int]] = {}

    def byte_offset(line_no: int, col: int) -> int:
        idx = line_no - 1
        arr = col_cache.get(idx)
        if arr is None:
            arr = [0]
            total = 0
            for ch in lines[idx]:
                total += len(ch.encode(encoding))
                arr.append(total)
            col_cache[idx] = arr
        if col >= len(arr):
            raise AnnotationError(
                f"source position line {line_no} col {col} exceeds the decoded line's own "
                f"length — the attested encoding does not agree with the parse"
            )
        return line_byte_start[idx] + arr[col]

    splices: list[tuple[int, bytes]] = []
    for tag in iter_elements_preorder(root):
        n = element_ordinal(tag, root)
        if tag.sourceline is None or tag.sourcepos is None:
            raise AnnotationError(
                f"el={n} (<{tag.name}>): the parse carries no source position for this "
                f"element (parser-implied) — cannot annotate it span-surgically"
            )
        start = byte_offset(tag.sourceline, tag.sourcepos)
        if start >= len(raw) or raw[start : start + 1] != b"<":
            raise AnnotationError(
                f"el={n} (<{tag.name}>): the computed splice offset {start} does not land "
                f"on '<' in the raw artifact — refusing to guess"
            )
        i = start + 1
        while i < len(raw) and raw[i : i + 1] not in (b" ", b"\t", b"\n", b"\r", b"/", b">"):
            i += 1
        name_bytes = raw[start + 1 : i]
        if name_bytes.decode("ascii", errors="replace").lower() != tag.name:
            raise AnnotationError(
                f"el={n}: the raw bytes at the computed offset name "
                f"<{name_bytes.decode('ascii', errors='replace')}>, not <{tag.name}> — "
                f"refusing to guess"
            )
        splices.append((i, f' data-el="{n}"'.encode("ascii")))

    splices.sort(key=lambda s: s[0])  # document order == byte-offset order, already true
    out = bytearray()
    cursor = 0
    for pos, insertion in splices:
        out += raw[cursor:pos]
        out += insertion
        cursor = pos
    out += raw[cursor:]
    return bytes(out)


#: Versioned op id (spec §6.4) for the `annotated` view's SPLICE algorithm — folded into the
#: resolver's cache key exactly like `ENGINE_VERSION` above. The bytes it reads never drift
#: (it is a pure function of the raw artifact + attested parse); what could drift across a
#: release is the splice algorithm itself, so a change to it — never to `el=` materialization
#: — is what bumps this pin.
ANNOTATED_ENGINE_VERSION = "html-annotated@1"


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


def carrier_cid(tag: Tag) -> str | None:
    """The bare Content-ID a carrier element refers to through a `cid:` URI (RFC 2392 —
    `<img src="cid:logo@x">`, a `<video>`/`<audio>` source, an `<a href="cid:…">`), or None
    when the element carries no such reference. The intra-container counterpart of
    `carrier_data_uri` (§6.2): the bytes live in a sibling MIME part of the enclosing
    message, never in the HTML."""
    if not isinstance(tag, Tag):
        return None
    name = tag.name
    candidates: list[object] = []
    if name == "img":
        candidates.append(largest_img_src(tag))
    elif name in _MEDIA_CARRIER_TAGS:
        candidates.append(tag.get("src"))
        candidates.extend(
            source.get("src") for source in tag.find_all("source") if isinstance(source, Tag)
        )
    elif name == "a":
        candidates.append(tag.get("href"))
    for cand in candidates:
        if isinstance(cand, str) and cand.strip().lower().startswith("cid:"):
            cid = cand.strip()[4:].strip()
            if cid:
                return cid
    return None


def _cid_bytes(cid: str, ctx: RenderContext | None, where: str) -> tuple[str, bytes]:
    """Materialize a `cid:` reference to `(media_type, bytes)` through the enclosing
    message the `part=` handler left in `ctx["cid_source"]` (§6.2 intra-container
    references). No enclosing message, or no part with that Content-ID, is a hard error:
    the address names something real that this route cannot reach, never a quiet blank."""
    from pathlib import Path

    from .. import emlfile

    source = (ctx or {}).get("cid_source")
    if not source:
        raise ValueError(
            f"{where}: <cid:{cid}> refers to a sibling MIME part of an enclosing message, "
            f"and this artifact is not being resolved through one — reach it via "
            f"`msg=<N>&part=<M>&el=…` (or a promoted message's `part=`), never standalone"
        )
    found = emlfile.part_by_content_id(Path(str(source)).read_bytes(), cid)
    if found is None:
        raise ValueError(
            f"{where}: the enclosing message carries no part with Content-ID <{cid}>"
        )
    part, decoded = found
    media_type, _ = emlfile.part_facts(part, decoded)
    return media_type, decoded


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

    Which grammar the value is read under is decided by the RECORD, not the value —
    **three** generations (v35, §6.1.1): an `addressing:` stamp (§7.1) carrying
    `scheme: ordinal` speaks the total document-order ordinal space; a stamp WITHOUT the
    key is the frozen 3.6 dotted child-index path; no stamp at all is the frozen pre-3.6
    filtered index. The bare-integer spelling is valid under all three with different
    meanings, so sniffing the value would resolve silently to the wrong element — the
    exact failure this amendment exists to end.

    On either stamped branch the two attested facts are checked FIRST: a foreign parser
    identity or a diverging element count is a hard error, never a silent walk of the
    wrong tree. A sibling range is bounds-checked exactly like a point and only THEN
    declared unmaterializable — an envelope that runs past the tree names nothing, and
    reporting it as declared coverage is how confabulated span addresses stayed invisible
    to the gate (the `parse_index_span` lesson, kept)."""
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

        if addressing.get("scheme") == "ordinal":
            ordinal = furi.parse_el_ordinal(value)
            root = path_root(soup)
            if ordinal.is_point:
                tag = resolve_ordinal(root, ordinal.point)
                return HtmlElRef(tag=tag, index=ordinal.point)
            a, b = ordinal.sibling_range
            if not ordinals_are_siblings(root, a, b):
                raise ValueError(
                    f"el={furi.format_el_ordinal(ordinal)}: ordinals {a} and {b} are not "
                    f"siblings — a range's endpoints must share a parent element (§6.1.1, "
                    f"the v35 owner ruling); this is an invalid address, not a valid one "
                    f"with no byte surface"
                )
            # A valid sibling range names a real envelope of elements; it just has no
            # single byte surface. Not a defect — see `NotMaterializable`.
            raise NotMaterializable(
                f"el={furi.format_el_ordinal(ordinal)}: sibling-range envelope has no "
                f"single byte surface to materialize; a point ordinal is required for that"
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
    return _img_tag_to_pil(tag, f"el={ref.index}", ctx)


def htmlel_bytes(ref: HtmlElRef, ctx: RenderContext | None = None) -> tuple[str, bytes]:
    """Materialize a non-image carrier (`<video>`/`<audio>`/`<a href="data:…">`, or a
    `cid:`-referencing one through the enclosing message in `ctx`) to
    `(media_type, raw_bytes)`. Raises for an `<img>` (use `render_htmlel_image`) or a
    structural element with no inline bytes."""
    tag = ref.tag
    uri = carrier_data_uri(tag)
    if uri is None:
        cid = carrier_cid(tag)
        if cid is not None:
            return _cid_bytes(cid, ctx, f"el={ref.index} (<{tag.name}>)")
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


def _img_tag_to_pil(
    tag: Tag, selector_for_error: str, ctx: RenderContext | None = None
) -> Image.Image:
    if tag.name != "img":
        raise ValueError(
            f"selector {selector_for_error!r} resolved to <{tag.name}>, expected <img>"
        )
    src_raw = largest_img_src(tag) or ""
    src = str(src_raw).strip()
    if src.lower().startswith("cid:"):
        # An intra-container reference (§6.2): the bytes are a sibling MIME part of the
        # enclosing message, reached through `ctx["cid_source"]`.
        _, raw = _cid_bytes(src[4:].strip(), ctx, selector_for_error)
    elif not src.startswith("data:"):
        raise ValueError(
            f"<img src=> is not a data URI ({src[:60]!r}…) for {selector_for_error!r}; "
            "the html resolver only handles inline base64 data URIs and cid: references"
        )
    elif (match := _DATA_URI_RE.match(src)) is not None:
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


# ---------- the text reduction (`text` / `el=<N>&text`, v43 §6.2) ---------- #

#: Elements whose content is not the document's text: dropped whole.
_TEXT_SKIP_TAGS = frozenset({"head", "script", "style", "template", "noscript"})
#: Elements that break the line on both sides. `<br>` breaks once; `<td>`/`<th>` end a cell
#: with a tab (handled inline in `html_text`).
_TEXT_BLOCK_TAGS = frozenset({
    "address", "article", "aside", "blockquote", "center", "dd", "details", "dialog", "div",
    "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4",
    "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section", "summary",
    "table", "tbody", "tfoot", "thead", "tr", "ul",
})
_TEXT_SKIP_STRINGS = (Comment, Doctype, Declaration, ProcessingInstruction, CData)
_TEXT_SPACE_RE = re.compile(r"[ \xa0\r\f\v]+")
_TEXT_TAB_RE = re.compile(r" ?\t+ ?")
#: Whitespace inside a text node — source line breaks included — is one space, as a browser
#: lays it out; only structure (`_TEXT_BLOCK_TAGS`, `<br>`) breaks a line. `<pre>` keeps its
#: line breaks (its indentation still collapses: this is a text surface, not a rendering).
_TEXT_INLINE_WS_RE = re.compile(r"\s+")


def html_text(node: Tag | BeautifulSoup) -> str:
    """The markup's own text reduction (spec §6.2 `text`): every text node under `node`
    in document order; block-level elements and `<br>` become line breaks, table cells are
    tab-separated, `_TEXT_SKIP_TAGS` are dropped whole; runs of whitespace collapse to one
    space, lines are stripped, and runs of blank lines collapse to one. Deterministic under
    the pinned parser (`EL_PARSER_ID`), so a citation's quote matches it verbatim on every
    run. Nothing is removed on judgment: no chrome strip, no quote trimming. Source line
    breaks inside a text node are whitespace, as a browser lays them out — only structure
    breaks a line — except under `<pre>`, whose line breaks are kept (indentation still
    collapses: a text surface, not a rendering). Returns `''` for markup carrying no text."""
    pieces: list[str] = []

    def walk(parent: Tag, in_pre: bool) -> None:
        for child in parent.children:
            if isinstance(child, NavigableString):
                if isinstance(child, _TEXT_SKIP_STRINGS):
                    continue
                text = str(child)
                pieces.append(text if in_pre else _TEXT_INLINE_WS_RE.sub(" ", text))
            elif isinstance(child, Tag):
                name = (child.name or "").lower()
                if name in _TEXT_SKIP_TAGS:
                    continue
                if name == "br":
                    pieces.append("\n")
                    continue
                if name in ("td", "th"):
                    walk(child, in_pre)
                    pieces.append("\t")
                    continue
                block = name in _TEXT_BLOCK_TAGS
                if block:
                    pieces.append("\n")
                walk(child, in_pre or name == "pre")
                if block:
                    pieces.append("\n")

    walk(node, False)
    lines: list[str] = []
    for line in "".join(pieces).split("\n"):
        line = _TEXT_SPACE_RE.sub(" ", line)
        line = _TEXT_TAB_RE.sub("\t", line).strip(" \t")
        if line:
            lines.append(line)
        elif lines and lines[-1]:
            lines.append("")
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


@register("html", "text", "text")
def extract_text(soup: BeautifulSoup, value: str | None, ctx: RenderContext) -> str:
    """`?text` — the whole document's text reduction (`html_text`), spec §6.2 (v43)."""
    if value:
        raise ValueError("text takes no value")
    return html_text(soup)


@register("htmlel", "text", "text")
def extract_el_text(ref: HtmlElRef, value: str | None, ctx: RenderContext) -> str:
    """`?el=<N>&text` — the selected element's own subtree reduced exactly as `text`
    (the span-precise form), spec §6.2 (v43)."""
    if value:
        raise ValueError("text takes no value")
    return html_text(ref.tag)


def _is_svg_payload(raw: bytes) -> bool:
    """True when `raw` is a valid-looking SVG document — an `<svg` root within the leading
    bytes, tolerating an XML declaration, a DOCTYPE, comments, and a BOM."""
    head = raw[:4096].lstrip(b"\xef\xbb\xbf").lstrip()
    if not head.startswith(b"<"):
        return False
    return b"<svg" in head[:4096].lower()
