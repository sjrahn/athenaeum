"""PDF introspection — the read-time analysis the resolver's PDF ops expose to a
normalizer, plus the `/Info` metadata the drafter lifts.

The PDF drafter is mechanical: it rasterizes every page to a body-empty `image` segment
(`page=<N>`) and makes **no** born-digital-vs-scanned determination and extracts **no**
text. Everything an agent needs to make that determination — the embedded text layer,
per-word boxes, per-page structural signals (image coverage, invisible-text / OCR-layer
tells, dimensions, rotation), and the outline — lives here and is reachable through the
functional-URI resolver (`page=<N>&text`, `page=<N>&words`, `page=<N>&probe`, `probe`,
`outline`). See the `application/pdf` schema guidance.

pypdf reads text + `/Info` + the content stream (image coverage, text render mode);
pypdfium2 reads page geometry, the text layer's character boxes, and the outline. Both
are base dependencies (the resolver and drafter already import them at module top).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pypdf import PdfReader
from pypdf.generic import ContentStream

log = logging.getLogger(__name__)

# A page whose largest single image covers at least this fraction of the page area is a
# full-page raster — the structural signature of a scanned page. Advisory now (the
# `probe` op reports it and the agent decides), not a drafter switch.
SCANNED_COVERAGE = 0.9


# ---------- /Info metadata ---------- #


def info_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def info_date(value: Any) -> str:
    """A pypdf datetime (or None) as an ISO-8601 string."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds").replace("+00:00", "Z")
    return info_str(value)


def document_info(reader: PdfReader) -> dict[str, Any]:
    """The `/Info`-derived frontmatter fields (no `page_count`). Drafter + probe share."""
    out: dict[str, Any] = {}
    info = reader.metadata
    if info is None:
        return out
    if v := info_str(info.title):
        out["title"] = v
    if v := info_str(info.author):
        out["author"] = v
    if v := info_str(info.producer):
        out["producer"] = v
    if v := info_date(info.creation_date):
        out["creation_date"] = v
    if v := info_date(info.modification_date):
        out["modification_date"] = v
    return out


# ---------- page text layer ---------- #


def extract_page_text(reader: PdfReader, index0: int) -> str:
    """Page `index0` (0-indexed) embedded text via pypdf, scrubbed of the unpaired UTF-16
    surrogates pypdf occasionally emits (invalid Unicode that breaks UTF-8 serialization)."""
    try:
        text = reader.pages[index0].extract_text() or ""
    except Exception:
        text = ""
    return text.encode("utf-8", errors="replace").decode("utf-8").strip()


# ---------- image coverage + render-mode (scanned / OCR-layer signals) ---------- #


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


def max_image_coverage(page: Any, reader: PdfReader) -> float:
    """Largest fraction of the page area covered by a single image-draw (`Do`) op.

    Walks the content stream tracking the CTM (q/Q stack + `cm` concatenation); for each
    `Do` painting an image XObject, the painted area is |det(CTM)| (the area of the
    transformed image unit square). Returns 0.0 on any parse failure or when the page has
    no image XObjects. Direct image draws only — a scanner that wraps the page image in a
    Form XObject reads as 0 here.
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


def has_invisible_text(page: Any, reader: PdfReader) -> bool:
    """True when the page uses an invisible text render mode (`Tr 3` / `Tr 7`) — the
    classic signature of an OCR text layer painted under (or over) a scanned page image."""
    try:
        cs = ContentStream(page.get_contents(), reader)
    except Exception:
        return False
    for operands, op in cs.operations:
        if op == b"Tr" and operands:
            try:
                if int(operands[0]) in (3, 7):
                    return True
            except Exception:
                continue
    return False


# ---------- outline / TOC ---------- #


def read_outline_tree(doc: Any) -> list[dict[str, Any]]:
    """The PDF outline (bookmarks) as a nested tree: `[{title, page, children}]`.

    `page` is 1-indexed (None when the bookmark has no resolvable destination). Built
    from pypdfium2's flat `get_toc()` (each bookmark carries a `.level`) via a level stack.
    """
    try:
        bookmarks = list(doc.get_toc())
    except Exception as exc:
        log.debug("outline read failed: %s", exc)
        return []
    root: list[dict[str, Any]] = []
    stack: list[tuple[int, list[dict[str, Any]]]] = []
    for bm in bookmarks:
        try:
            title = (bm.get_title() or "").strip()
            dest = bm.get_dest()
            idx = dest.get_index() if dest is not None else None
            level = int(bm.level)
        except Exception as exc:
            log.debug("outline entry parse failed: %s", exc)
            continue
        node: dict[str, Any] = {
            "title": title,
            "page": (idx + 1) if idx is not None else None,
            "children": [],
        }
        while stack and stack[-1][0] >= level:
            stack.pop()
        (stack[-1][1] if stack else root).append(node)
        stack.append((level, node["children"]))
    return root


# ---------- per-word boxes ---------- #


def page_words(doc: Any, index0: int) -> dict[str, Any]:
    """Page `index0` (0-indexed) text-layer words with per-word bounding boxes.

    Each word is `{text, bbox: [x, y, w, h]}` with bbox in [0, 1] fractions of the page,
    origin top-left (matching the `bbox=` address convention) — pypdfium2 reports char
    boxes in PDF points with origin bottom-left, so the y axis is flipped. Words are
    assembled from characters, split on whitespace; the box is the union of its chars'.
    """
    page = doc[index0]
    width, height = page.get_size()
    textpage = page.get_textpage()
    words: list[dict[str, Any]] = []
    try:
        count = textpage.count_chars()
        chars: list[str] = []
        box: list[float] | None = None

        def flush() -> None:
            nonlocal box, chars
            if chars and box is not None and width > 0 and height > 0:
                left, bottom, right, top = box
                words.append(
                    {
                        "text": "".join(chars),
                        "bbox": [
                            round(left / width, 5),
                            round((height - top) / height, 5),
                            round((right - left) / width, 5),
                            round((top - bottom) / height, 5),
                        ],
                    }
                )
            chars = []
            box = None

        for i in range(count):
            ch = textpage.get_text_range(i, 1)
            if not ch or ch.isspace():
                flush()
                continue
            try:
                cb = textpage.get_charbox(i)
            except Exception:
                continue
            if cb is None:
                continue
            chars.append(ch)
            if box is None:
                box = list(cb)
            else:
                box[0] = min(box[0], cb[0])
                box[1] = min(box[1], cb[1])
                box[2] = max(box[2], cb[2])
                box[3] = max(box[3], cb[3])
        flush()
    finally:
        textpage.close()
    return {
        "page": index0 + 1,
        "width_pt": round(width, 2),
        "height_pt": round(height, 2),
        "word_count": len(words),
        "words": words,
    }


# ---------- structural probe ---------- #


def _shape_hint(coverage: float, char_count: int, invisible: bool) -> str:
    """Advisory page-shape classification from the structural signals — the agent decides."""
    if coverage >= SCANNED_COVERAGE:
        return "scanned-ocr" if char_count > 0 else "scanned-no-text"
    if char_count == 0:
        return "no-text"  # vector-only / empty / DRM'd text
    return "born-digital"


def probe_page(reader: PdfReader, doc: Any, index0: int) -> dict[str, Any]:
    """Per-page structural signals (0-indexed page). Advisory `shape_hint` plus the raw
    measurements an agent uses to judge born-digital vs scanned and how to proceed."""
    pp_page = reader.pages[index0]
    text = extract_page_text(reader, index0)
    coverage = max_image_coverage(pp_page, reader)
    invisible = has_invisible_text(pp_page, reader)
    fx_page = doc[index0]
    width, height = fx_page.get_size()
    try:
        rotation = int(fx_page.get_rotation())
    except Exception:
        rotation = 0
    char_count = len(text)
    return {
        "page": index0 + 1,
        "width_pt": round(width, 2),
        "height_pt": round(height, 2),
        "rotation": rotation,
        "text_char_count": char_count,
        "word_count": len(text.split()),
        "image_coverage": round(coverage, 4),
        "has_invisible_text": invisible,
        "shape_hint": _shape_hint(coverage, char_count, invisible),
    }


def _summarize_shape(hints: list[str]) -> str:
    uniq = set(hints)
    if not uniq:
        return "empty"
    if len(uniq) == 1:
        return next(iter(uniq))
    if uniq <= {"scanned-ocr", "scanned-no-text"}:
        return "scanned"
    return "mixed"


def probe_document(reader: PdfReader, doc: Any) -> dict[str, Any]:
    """Whole-document probe: per-page table + `/Info`, outline presence, and a doc-level
    `shape_summary`. The born-digital-vs-scanned determination tool."""
    page_count = len(reader.pages)
    pages = [probe_page(reader, doc, i) for i in range(page_count)]
    outline = read_outline_tree(doc)
    try:
        encrypted = bool(reader.is_encrypted)
    except Exception:
        encrypted = False
    return {
        "page_count": page_count,
        "encrypted": encrypted,
        "has_outline": bool(outline),
        "info": document_info(reader),
        "shape_summary": _summarize_shape([p["shape_hint"] for p in pages]),
        "pages": pages,
    }
