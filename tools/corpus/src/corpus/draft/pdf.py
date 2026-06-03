"""PDF draft extraction (deterministic).

Extracts /Info metadata and per-page text from a PDF artifact. Produces either a list
of `Section`s (one per top-level outline entry, addressed `pages=<start>-<end>` with
the outline title as `entry:`) when the PDF carries a usable outline (TOC bookmarks),
or a flat list of top-level `text` Segments addressed `page=<N>` when it doesn't.

pypdf handles text extraction; pypdfium2 reads the outline (already a resolver dep).

Per spec §1.5/§4.3 the body is faithful — no interpretation, no editorial. A PDF with
no extractable text layer (scanned, DRM'd, image-only) yields zero segments; the
normalizer adds a `partial-content` issue if needed.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from pypdf import PdfReader

from corpus import content_hash, recordbuild, records
from corpus.draft import DrafterResult, register
from corpus.segments import Section, Segment

log = logging.getLogger(__name__)

# A page is treated as "blank" if its extracted text contains less than this many
# non-whitespace characters. Blank pages don't get their own text segments.
_BLANK_PAGE_THRESHOLD = 5


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
    title: str | None = None
    if info is not None:
        if v := _str(info.title):
            fields["pdf_title"] = v
            title = v
        if v := _str(info.author):
            fields["pdf_author"] = v
        if v := _str(info.producer):
            fields["pdf_producer"] = v
        if v := _date(info.creation_date):
            fields["pdf_creation_date"] = v
        if v := _date(info.modification_date):
            fields["pdf_modification_date"] = v

    pages = [_extract_page_text(p) for p in reader.pages]
    page_segments = _build_page_segments(pages)

    blocks: list[Section | Segment]
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
        "title": title,
        "issues": [],
        "canonical": canonical,
    }


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
            sections.append(
                Section(
                    address=f"pages=1-{first_start - 1}",
                    entry="Preamble",
                    segments=preamble_segs,
                )
            )

    for title, start, end in bounds:
        children = [seg_by_page[p] for p in range(start, end + 1) if p in seg_by_page]
        if not children:
            continue
        sections.append(
            Section(
                address=f"pages={start}-{end}" if end > start else f"pages={start}",
                entry=title,
                segments=children,
            )
        )

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
