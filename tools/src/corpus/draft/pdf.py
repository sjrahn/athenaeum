"""PDF draft extraction (deterministic, shape-aware addressing).

Each page picks its own content shape from `pdf_introspect.probe_page`'s advisory
`shape_hint`:

- **born-digital** (real vector text, no full-page raster) becomes an `atom: text`
  Segment whose body is the page's embedded text layer (`pdf_introspect.extract_page_text`),
  addressed to the page's non-chrome CONTENT BAND: `page=<N>&bbox=0,<top>,1,<height>`,
  computed from the text layer's character geometry (`pdf_introspect.assemble_lines` /
  `detect_chrome` / `body_band`) so a reader's crop already excludes the running header, the
  document-id banner, and the `N of M` footer. A page whose geometry can't be trusted
  (fragmented line assembly — see `_FRAGMENT_REJECT_RATIO`'s docstring — or a band spanning
  nearly the whole page) falls back to a bare `page=<N>` address instead: a wrong bbox
  silently sources content from the wrong region, whereas a bare address is merely
  imprecise. A born-digital page whose extracted text comes back effectively blank gets an
  image marker (below), not an empty text segment.
- **everything else** (scanned-ocr / scanned-no-text / no-text) gets the body-empty `atom:
  image` positioning marker at bare `page=<N>`. A scan's baked-in OCR text layer, when one
  exists, is never extracted or trusted here — turning pixels into text is normalizer work,
  powered by the resolver's `page=<N>&text` / `&words` / `&probe` ops.

The PDF's top-level outline (bookmarks) becomes `atom: structural` byte-marks — one per
resolvable root-level entry, `address=page=<N>`, `level: 1`, body = the bookmark title
verbatim — each inserted immediately before its page's own content segment, in document
order. Two top-level entries resolving to the same page keep only the first; a malformed
outline is a fact worth recording as-is, not silently patched (the normalizer rebuilds
structure by hand when a source's own outline lies).

No `Section` is ever emitted here — sections bind a FORM, which is normalizer judgment,
never a generic drafter's; the derived table of contents reads the structural marks instead.
The drafter also lifts the `/Info` metadata (page_count, title, author, producer, dates) —
faithful, cheap frontmatter — via `pdf_introspect.document_info`.

Any geometry failure — pypdfium2 can't open the document, a single page's probe throws —
degrades to the safe fallback (a bare `page=<N>` address, or an image marker) rather than
failing the draft. See the `application/pdf` schema's `normalization.guidance` for the full
normalizer playbook.

pypdf reads `/Info` + the embedded text layer; pypdfium2 supplies page geometry, chrome
detection, and the outline. Both are base dependencies already imported by the resolver's
introspection ops (`corpus.pdf_introspect`), which this drafter shares rather than
duplicates.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from pypdf import PdfReader

from corpus import content_hash, pdf_introspect, recordbuild, records, touches
from corpus.draft import DrafterResult, register
from corpus.fingerprint import algos_for_atom, text_fingerprints
from corpus.segments import Segment

log = logging.getLogger(__name__)

# A page is treated as "blank" if its extracted text contains less than this many
# non-whitespace characters. A blank born-digital page gets an image marker, not an
# empty text segment.
_BLANK_PAGE_THRESHOLD = 5

# Padding added above and below a page's measured content band, as a fraction of page
# height. Glyph extents are exact but a crop that hugs them looks clipped and leaves no
# room for a descender the text layer under-reports; ~2pt of slack on A4.
_BAND_PAD = 0.0025

# A content band spanning at least this fraction of the page is indistinguishable from
# "the whole page" — emit a bare `page=N` rather than a bbox that implies a precision it
# doesn't have.
_FULL_PAGE_BAND = 0.97

# Geometry is rejected for a page when this fraction of its assembled lines are 1-2
# characters long — the tell for a page `assemble_lines` cannot band (see its docstring).
# The threshold is deliberately loose because a *band* degrades far more gracefully than a
# boundary: it is the min/max extent over all content lines, so shredding a line into pieces
# leaves their union covering the same span. `A6.4-STAN-METH-004` p19 fragments at 10% and
# still bands correctly, while its per-line coordinates are useless for deriving a section
# boundary. This guards only against a page so broken that a stray glyph distorts the extent
# itself.
_FRAGMENT_REJECT_RATIO = 0.30


@register("application/application_pdf")
def draft(
    pdf_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,
) -> DrafterResult:
    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)

    fields: dict[str, Any] = {"page_count": page_count, **pdf_introspect.document_info(reader)}
    text_algos = algos_for_atom("text", fingerprint)

    try:
        doc: Any | None = pdfium.PdfDocument(str(pdf_path))
    except Exception as exc:
        log.debug("pypdfium2 open failed for %s: %s — every page falls back to an "
                   "image marker", pdf_path, exc)
        doc = None

    blocks: list[Segment] = []
    try:
        chrome: set[str] = set()
        outline_by_page: dict[int, str] = {}
        if doc is not None:
            try:
                chrome = pdf_introspect.detect_chrome(doc)
            except Exception as exc:
                log.debug("chrome detection failed, bands computed without it: %s", exc)
            outline_by_page = _top_level_outline_by_page(doc)

        for i in range(page_count):
            page_no = i + 1
            if title := outline_by_page.get(page_no):
                blocks.append(
                    Segment(atom="structural", address=f"page={page_no}", level=1, body=title)
                )
            blocks.append(_page_segment(reader, doc, i, page_no, chrome, text_algos))
        embeds = _attachment_embeds(doc) if doc is not None else []
    finally:
        if doc is not None:
            doc.close()

    # Canonical hash per the mime schema's `canonical_strategy.algo` (the strategy id
    # encodes its hash family, e.g. `blake3-canonical-pdf` → `blake3:`); falls back to the
    # PDF default when the schema/caller doesn't override it.
    algo = canonical_algo or "blake3-canonical-pdf"
    canonical = records.format_hash(algo.split("-", 1)[0], content_hash.compute(algo, pdf_path))

    recordbuild.add_blocks(build, blocks)
    return {
        "fields": fields,
        "embeds": embeds,
        "issues": _annotation_overlay_issues(reader),
        "canonical": canonical,
    }


_DETECTOR = touches.script_identifier("draft.application/application_pdf")

#: Annotation subtypes that draw content over the page the text layer does not hold: typed
#: text, opaque shapes that can hide what lies beneath, stamps, ink, redactions, and a
#: strike-out marking a value superseded. Link, Popup, Text (a note icon), Highlight and
#: Underline change nothing a reader takes as the page's content.
_OVERLAY_SUBTYPES = frozenset({"FreeText", "Square", "Circle", "Polygon", "PolyLine", "Line",
                               "Ink", "Stamp", "Redact", "StrikeOut"})
_ANNOT_HIDDEN, _ANNOT_NOVIEW = 2, 32


def _widget_has_value(annot: Any) -> bool:
    """A form widget drawing a filled value (its own `/V`, or its field's up the chain)."""
    node, seen = annot, 0
    while node is not None and seen < 8:
        v = node.get("/V")
        if v is not None:
            return str(v) not in ("", "/Off")
        parent = node.get("/Parent")
        node = parent.get_object() if parent is not None else None
        seen += 1
    return False


def _annotation_overlay_issues(reader: PdfReader) -> list[dict[str, Any]]:
    """`format-loss/annotation-overlay` at `page=<N>` for every page that draws visible
    annotations over its content (§4.3.3.2): the drafted body is the text layer, which
    holds none of what they draw and still holds what they may cover — a correction typed
    over a white box reads, in the text layer, as the value it replaced."""
    issues: list[dict[str, Any]] = []
    for n, page in enumerate(reader.pages, start=1):
        try:
            annots = page.get("/Annots")
            annots = annots.get_object() if annots is not None else []
            kinds: list[str] = []
            for ref in annots or []:
                a = ref.get_object()
                flags = int(a.get("/F", 0) or 0)
                if flags & (_ANNOT_HIDDEN | _ANNOT_NOVIEW):
                    continue
                sub = str(a.get("/Subtype", "")).lstrip("/")
                if sub in _OVERLAY_SUBTYPES or (sub == "Widget" and _widget_has_value(a)):
                    kinds.append(sub)
        except Exception as exc:  # a malformed annotation array never sinks the draft
            log.debug("annotation scan failed on page %d: %s", n, exc)
            continue
        if kinds:
            issues.append({
                "id": "format-loss",
                "subtype": "annotation-overlay",
                "severity": "warning",
                "detector": _DETECTOR,
                "address": f"page={n}",
                "fields": {"annotation_subtypes": sorted(set(kinds)),
                           "annotation_count": len(kinds)},
            })
    return issues


def _attachment_embeds(doc: Any) -> list[dict[str, Any]]:
    """One exposable-member row per embedded file / portfolio member (§7.1), addressed
    `attachment=<N>` in the resolver's enumeration (`transforms.pdf.attachments`). An entry
    pdfium cannot read has no bytes to roster and is skipped (resolving it says why)."""
    import blake3

    from corpus import mime as mime_mod
    from corpus.transforms import pdf as pdf_tf

    try:
        entries = pdf_tf.attachments(doc)
    except Exception as exc:  # a broken name tree never sinks the page draft
        log.debug("embedded-file enumeration failed: %s", exc)
        return []
    by_hash: dict[str, dict[str, Any]] = {}  # one row per distinct bytes, every address
    for n, (name, data) in enumerate(entries, start=1):
        if data is None:
            continue
        digest = blake3.blake3(data).hexdigest()
        if digest in by_hash:
            by_hash[digest]["addresses"].append(f"attachment={n}")
            continue
        media_type = mime_mod.sniff_head(data[:8192], name or None)
        fields: dict[str, Any] = {"bytes": len(data)}
        if name:
            fields["filename"] = name
        by_hash[digest] = {
            "media_type": media_type if media_type != "unknown" else "application/octet-stream",
            "addresses": [f"attachment={n}"], "fields": fields,
        }
    return [
        {"media_type": e["media_type"],
         "address": e["addresses"][0] if len(e["addresses"]) == 1 else e["addresses"],
         "transport": records.format_hash("blake3", digest), "fields": e["fields"]}
        for digest, e in by_hash.items()
    ]


# ---------- per-page shape + addressing ---------- #


def _page_segment(
    reader: PdfReader,
    doc: Any | None,
    index0: int,
    page_no: int,
    chrome: set[str],
    text_algos: list[str],
) -> Segment:
    """Decide one page's content shape and return its Segment.

    Falls back to a body-empty image marker whenever the shape can't be determined
    (no usable pypdfium2 doc, a page index out of range against it, or the probe itself
    throwing) — the same fallback a genuinely scanned page gets, since an undetermined
    shape must not be guessed as born-digital.
    """
    if doc is None or index0 >= len(doc):
        return Segment(atom="image", address=f"page={page_no}", body="")
    try:
        probe = pdf_introspect.probe_page(reader, doc, index0)
    except Exception as exc:
        log.debug("page %d: probe failed, falling back to image marker: %s", page_no, exc)
        return Segment(atom="image", address=f"page={page_no}", body="")

    if probe["shape_hint"] != "born-digital":
        return Segment(atom="image", address=f"page={page_no}", body="")

    body = pdf_introspect.extract_page_text(reader, index0)
    if _is_blank(body):
        return Segment(atom="image", address=f"page={page_no}", body="")

    address = _band_address(doc[index0], page_no, chrome) or f"page={page_no}"
    return Segment(
        atom="text",
        address=address,
        perceptual=text_fingerprints(body, text_algos),
        body=body,
    )


def _is_blank(text: str) -> bool:
    stripped = "".join(ch for ch in text if not ch.isspace())
    return len(stripped) < _BLANK_PAGE_THRESHOLD


def _band_address(fx_page: Any, page_no: int, chrome: set[str]) -> str | None:
    """The page's non-chrome content band as `page=<N>&bbox=0,<top>,1,<height>`, or None
    when the geometry can't be trusted or the band isn't worth stating (the caller falls
    back to a bare `page=<N>`)."""
    try:
        lines = pdf_introspect.assemble_lines(fx_page)
        if not lines:
            return None
        frags = sum(1 for line in lines if len(line["text"]) <= 2)
        if frags / len(lines) >= _FRAGMENT_REJECT_RATIO:
            log.debug("page %d: geometry looks fragmented, skipping bbox", page_no)
            return None
        band = pdf_introspect.body_band(lines, chrome)
        if band is None:
            return None
        top = max(0.0, round(band[0] - _BAND_PAD, 4))
        bottom = min(1.0, round(band[1] + _BAND_PAD, 4))
        height = round(bottom - top, 4)
        if height <= 0 or height >= _FULL_PAGE_BAND:
            return None
        return f"page={page_no}&bbox=0,{_f(top)},1,{_f(height)}"
    except Exception as exc:  # geometry is an optimisation, never a hard failure
        log.debug("page %d: band addressing failed, falling back to page=N: %s", page_no, exc)
        return None


def _f(value: float) -> str:
    """Format a coordinate without trailing zeros (`0.1461`, `0.23`, `0`)."""
    return f"{value:.4f}".rstrip("0").rstrip(".") or "0"


# ---------- outline structural marks ---------- #


def _top_level_outline_by_page(doc: Any) -> dict[int, str]:
    """Top-level outline entries as `{page: title}`, in ascending page order.

    Entries with no resolvable page or an empty title are dropped; when two entries
    resolve to the same page, `dict.setdefault` over the page-sorted (stable) list keeps
    whichever came first in the outline's own order."""
    roots = pdf_introspect.read_outline_tree(doc)
    entries = [
        (node.get("page"), (node.get("title") or "").strip())
        for node in roots
        if node.get("page") is not None and (node.get("title") or "").strip()
    ]
    entries.sort(key=lambda entry: entry[0])
    out: dict[int, str] = {}
    for page, title in entries:
        out.setdefault(page, title)
    return out
