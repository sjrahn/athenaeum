"""PDF draft extraction (deterministic).

A PDF is drafted one of two ways, chosen by inspecting its bytes:

- **Born-digital** (the text layer is the real content). Extracts /Info metadata and
  per-page text. Produces either a list of `Section`s (one per top-level outline entry,
  addressed `pages=<start>-<end>` with the outline title as `entry:`) when the PDF
  carries a usable outline (TOC bookmarks), or a flat list of top-level `text` Segments
  addressed `page=<N>` when it doesn't.

- **Scanned image-of-document** (every page is a full-page raster — see
  `_is_scanned_pdf`). The page text, if any, is a machine-OCR layer baked in *before*
  capture: interpretation, not faithful source, and often low quality. We deliberately
  treat the PDF as if it had no text layer at all — sectionless, one body-empty `image`
  Segment per page addressed `page=<N>` (the positioning markers the image-of-document
  normalize pass re-reads into `text/ocr` segments at `page=<N>&bbox=...`). This keeps
  the corpus's own OCR (engine/confidence, region addressing) as the source of OCR text,
  rather than laundering a pre-baked OCR layer as born-digital `text`.

pypdf handles text extraction; pypdfium2 reads the outline (already a resolver dep).

Per spec §1.5/§4.3 the body is faithful — no interpretation, no editorial. A born-digital
PDF with no extractable text layer (DRM'd, vector-only) yields zero segments; the
normalizer adds a `partial-content` issue if needed.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from pypdf import PdfReader
from pypdf.generic import ContentStream

from corpus import content_hash, recordbuild, records
from corpus.draft import DrafterResult, register
from corpus.segments import Section, Segment

log = logging.getLogger(__name__)

# A page is treated as "blank" if its extracted text contains less than this many
# non-whitespace characters. Blank pages don't get their own text segments.
_BLANK_PAGE_THRESHOLD = 5

# A PDF is treated as a scanned image-of-document when *every* page is dominated by a
# raster image covering at least this fraction of the page area (a scanner sizes the
# page box to the scan, so real scans land at ~1.0; born-digital pages with no full-page
# image land at 0.0). Conservative threshold — when unsure we fall back to the text path,
# which never wrongly suppresses a genuine text layer.
_SCANNED_COVERAGE = 0.9


@register("application/application_pdf")
def draft(
    pdf_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,  # PDF text isn't fingerprinted (yet)
) -> DrafterResult:
    reader = PdfReader(str(pdf_path))

    fields: dict[str, Any] = {"page_count": len(reader.pages)}
    info = reader.metadata
    if info is not None:
        if v := _str(info.title):
            fields["title"] = v
        if v := _str(info.author):
            fields["author"] = v
        if v := _str(info.producer):
            fields["producer"] = v
        if v := _date(info.creation_date):
            fields["creation_date"] = v
        if v := _date(info.modification_date):
            fields["modification_date"] = v

    blocks: list[Section | Segment]
    if _is_scanned_pdf(reader):
        # Image-of-document: suppress the (machine-OCR) text layer and emit one
        # body-empty image-atom positioning marker per page, sectionless. The OCR
        # normalize pass reads each page region into `text/ocr` (see the schema guidance).
        blocks = [
            Segment(atom="image", address=f"page={i}", body="")
            for i in range(1, len(reader.pages) + 1)
        ]
    else:
        pages = [_extract_page_text(p) for p in reader.pages]
        page_segments = _build_page_segments(pages)
        outline = _read_outline_top_level(pdf_path)
        if outline:
            blocks = _wrap_in_outline_sections(
                page_segments=page_segments,
                outline=outline,
                page_count=len(pages),
            )
        else:
            blocks = list(page_segments)

    # Canonical hash per the mime schema's `canonical_strategy.algo` (the strategy id
    # encodes its hash family, e.g. `blake3-canonical-pdf` → `blake3:`); falls back to the
    # PDF default when the schema/caller doesn't override it.
    algo = canonical_algo or "blake3-canonical-pdf"
    canonical = records.format_hash(algo.split("-", 1)[0], content_hash.compute(algo, pdf_path))

    recordbuild.add_blocks(build, blocks)
    return {
        "fields": fields,
        "embeds": [],
        "issues": [],
        "canonical": canonical,
    }


# ---------- scanned-PDF detection ---------- #


def _is_scanned_pdf(reader: PdfReader) -> bool:
    """True when every page is dominated by a full-page raster image.

    This is the structural signature of a scanned document (with or without an
    auto-added OCR text layer), independent of which scanner/tool produced it — so we
    key on the bytes, never on a vendor `/Producer` string. A born-digital page (vector
    text, no full-page image) scores 0 coverage and fails the check; a single page that
    we can't measure (parse error, no content) also fails it, so the whole PDF falls
    back to the born-digital text path — the safe default that never suppresses real text.
    """
    pages = reader.pages
    if not pages:
        return False
    return all(_max_image_coverage(page, reader) >= _SCANNED_COVERAGE for page in pages)


def _mat_mul(m1: tuple[float, ...], m2: tuple[float, ...]) -> tuple[float, ...]:
    """Compose two PDF 2-D affine matrices [a b c d e f] (m1 applied first)."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


def _max_image_coverage(page: Any, reader: PdfReader) -> float:
    """Largest fraction of the page area covered by a single image-draw (`Do`) op.

    Walks the content stream tracking the CTM (q/Q stack + `cm` concatenation); for each
    `Do` painting an image XObject, the painted area is |det(CTM)| (the area of the
    transformed image unit square). Returns 0.0 on any parse failure or when the page has
    no image XObjects. Direct image draws only — a scanner that wraps the page image in a
    Form XObject would read as 0 here (→ born-digital fallback), which is acceptable: it
    errs toward keeping text, never toward dropping it.
    """
    try:
        res = page.get("/Resources")
        xobjects = res.get("/XObject") if res else None
    except Exception:
        return 0.0
    image_names: set[Any] = set()
    if xobjects:
        for key in xobjects:
            try:
                if xobjects[key].get_object().get("/Subtype") == "/Image":
                    image_names.add(key)
            except Exception:
                continue
    if not image_names:
        return 0.0

    try:
        mediabox = page.mediabox
        page_area = abs(float(mediabox.width) * float(mediabox.height))
    except Exception:
        return 0.0
    if page_area <= 0:
        return 0.0

    ctm: tuple[float, ...] = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    stack: list[tuple[float, ...]] = []
    max_cov = 0.0
    try:
        cs = ContentStream(page.get_contents(), reader)
        for operands, op in cs.operations:
            if op == b"q":
                stack.append(ctm)
            elif op == b"Q":
                ctm = stack.pop() if stack else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
            elif op == b"cm" and len(operands) == 6:
                ctm = _mat_mul(tuple(float(x) for x in operands), ctm)
            elif op == b"Do" and operands and operands[0] in image_names:
                a, b, c, d, _e, _f = ctm
                det = abs(a * d - b * c)  # area of the transformed unit square
                max_cov = max(max_cov, det / page_area)
    except Exception:
        return 0.0
    return max_cov


# ---------- helpers ---------- #


def _str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _date(value: Any) -> str:
    """Convert a pypdf datetime (or None) to ISO-8601 string."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds").replace("+00:00", "Z")
    return _str(value)


def _extract_page_text(page: Any) -> str:
    try:
        text = page.extract_text() or ""
    except Exception:
        text = ""
    # pypdf occasionally produces unpaired UTF-16 surrogates (e.g. \ud835 from
    # Mathematical Italic glyphs whose surrogate-pair partner was dropped). These
    # are invalid Unicode and break UTF-8 serialization at records.dump time. Scrub.
    text = text.encode("utf-8", errors="replace").decode("utf-8")
    return text.strip()


def _is_blank(text: str) -> bool:
    stripped = "".join(ch for ch in text if not ch.isspace())
    return len(stripped) < _BLANK_PAGE_THRESHOLD


def _build_page_segments(pages: list[str]) -> list[Segment]:
    """One Segment per non-blank page, addressed `page=<N>` (1-indexed)."""
    segs: list[Segment] = []
    for i, text in enumerate(pages, start=1):
        if _is_blank(text):
            continue
        segs.append(Segment(atom="text", address=f"page={i}", body=text))
    return segs


def _read_outline_top_level(pdf_path: Path) -> list[tuple[str, int]]:
    """Return the PDF's top-level outline entries as (title, start_page_1indexed)."""
    try:
        doc = pdfium.PdfDocument(str(pdf_path))
    except Exception as exc:
        log.debug("pypdfium2 open failed (no outline read): %s", exc)
        return []
    try:
        top: list[tuple[str, int]] = []
        for bookmark in doc.get_toc(max_depth=1):
            if bookmark.level != 0:
                continue
            try:
                title = bookmark.get_title() or ""
                dest = bookmark.get_dest()
                if dest is None:
                    continue
                page_idx = dest.get_index()
                if page_idx is None:
                    continue
            except Exception as exc:
                log.debug("outline entry parse failed: %s", exc)
                continue
            title = title.strip()
            if not title:
                continue
            top.append((title, page_idx + 1))
        top.sort(key=lambda t: t[1])
        return top
    finally:
        doc.close()


def _wrap_in_outline_sections(
    *,
    page_segments: list[Segment],
    outline: list[tuple[str, int]],
    page_count: int,
) -> list[Section]:
    """Group page Segments into Sections keyed by outline entries."""
    sections: list[Section] = []

    seg_by_page: dict[int, Segment] = {}
    for seg in page_segments:
        page_no = _page_from_address(seg.address)
        if page_no is not None:
            seg_by_page[page_no] = seg

    bounds: list[tuple[str, int, int]] = []
    for idx, (title, start) in enumerate(outline):
        end = outline[idx + 1][1] - 1 if idx + 1 < len(outline) else page_count
        bounds.append((title, start, max(end, start)))

    first_start = outline[0][1]
    if first_start > 1:
        preamble_segs = [
            seg_by_page[p] for p in range(1, first_start) if p in seg_by_page
        ]
        if preamble_segs:
            sections.append(Section.spanning(preamble_segs, entry="Preamble"))

    for title, start, end in bounds:
        children = [seg_by_page[p] for p in range(start, end + 1) if p in seg_by_page]
        if not children:
            continue
        sections.append(Section.spanning(children, entry=title))

    return sections


def _page_from_address(address: str | list[str]) -> int | None:
    if isinstance(address, list):
        if not address:
            return None
        address = address[0]
    if not isinstance(address, str) or not address.startswith("page="):
        return None
    rest = address.removeprefix("page=")
    page_str = rest.split("&", 1)[0]
    try:
        return int(page_str)
    except ValueError:
        return None
