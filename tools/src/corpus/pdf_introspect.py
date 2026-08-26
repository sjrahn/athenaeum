"""PDF introspection — shared read-time PDF analysis used by both the resolver's
introspection ops and the drafter: the embedded text layer, `/Info` metadata,
per-page structural signals (image coverage, invisible-text / OCR-layer tells,
dimensions, rotation), the outline, per-word boxes, and visual-line geometry
(line assembly, cross-page chrome detection, heading candidates, body bands).

Reachable through the functional-URI resolver (`page=<N>&text`, `page=<N>&words`,
`page=<N>&probe`, `page=<N>&geometry`, `probe`, `outline`). See the `application/pdf`
schema guidance.

pypdf reads text + `/Info` + the content stream (image coverage, text render mode);
pypdfium2 reads page geometry, the text layer's character boxes, and the outline. Both
are base dependencies (the resolver and drafter already import them at module top).
"""

from __future__ import annotations

import logging
import re
from collections import Counter
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


# ---------- visual-line geometry (chrome, headings, body band) ---------- #

# Rects whose top edges fall within this fraction of page height belong to the same
# visual line. 0.004 of an A4 page is ~3.4pt — under a single line's leading, over the
# jitter within one line's glyphs.
_LINE_TOLERANCE = 0.004
# A line is chrome if its text repeats on at least this fraction of pages (floor of 3
# pages). Running heads and page furniture repeat; body text does not — and a cover
# page's one-off "Version 01.0" correctly stays body while the identical string in a
# running header is dropped.
_CHROME_PAGE_RATIO = 0.4
# A line is a heading CANDIDATE if its tallest glyph exceeds the page's modal glyph
# height by this factor and it opens with a section number. Best-effort only: weight is
# not exposed on the text layer, so a heading set in the same size as body and
# distinguished by bold alone will not trip this. `headings` is therefore a hint for the
# raster reader to confirm, never a structure to trust — an empty list means "none
# detected", not "none present".
_HEADING_HEIGHT_RATIO = 1.12
_NUMBERED = re.compile(r"^\s*(?:[IVX]+\.|\d+(?:\.\d+)*\.?)\s+\S")


def assemble_lines(page: Any) -> list[dict]:
    """Group a page's characters into visual lines, in relative coordinates.

    Works at character granularity (`count_chars` / `get_charbox`), not at pypdfium2's
    rect granularity. Rects are lossy — `get_text_bounded` over them drops hyphens and
    duplicates the odd glyph, so a hyphenated identifier like `PROJ-2024-001` comes back
    as `PROJ 2024 001`. Character indices are 1:1 with `get_text_range()` and already in
    reading order, so lines rebuild exactly, spaces included, with no x-sorting or gap
    heuristics.

    **Known failure: pages set in mathematical-italic Unicode** (the U+1D400 block, as
    some equation-heavy documents use for variable names). Those glyphs carry charboxes
    that do not sit on the surrounding text baseline, so banding shreds the page — one
    physical line can be reported at three or four different `y` values at once.
    Fragmentary `text` values (single characters, mid-word splits) are the tell. Treat
    geometry from such a page as unusable and adjudicate from the raster; do not derive
    addresses from it.
    """
    tp = page.get_textpage()
    pw, ph = page.get_width(), page.get_height()
    n = tp.count_chars()
    text = tp.get_text_range()

    lines: list[dict] = []
    cur: dict | None = None
    for i in range(min(n, len(text))):
        ch = text[i]
        if ch in "\r\n":
            cur = None  # hard break; next glyph opens a line
            continue
        left, bottom, right, top = tp.get_charbox(i)
        # Band on the BASELINE, not the top edge. Glyph tops vary within a line by more
        # than a line's worth — a period's top sits well below a capital's — so
        # top-banding shreds each line into words. Baselines agree closely; the
        # tolerance only has to absorb descenders.
        base = 1 - bottom / ph
        if cur is not None and abs(base - cur["_base"]) > _LINE_TOLERANCE:
            cur = None
        if cur is None:
            cur = {
                "_base": base,
                "_top": 1 - top / ph,
                "h": (top - bottom) / ph,
                "x0": left / pw,
                "x1": right / pw,
                "text": "",
            }
            lines.append(cur)
        cur["text"] += ch
        cur["_top"] = min(cur["_top"], 1 - top / ph)
        cur["h"] = max(cur["h"], (top - bottom) / ph)
        cur["x0"] = min(cur["x0"], left / pw)
        cur["x1"] = max(cur["x1"], right / pw)

    out: list[dict] = []
    for line in lines:
        stripped = line["text"].strip()
        if not stripped:
            continue
        out.append(
            {
                # `y` is the line's topmost glyph edge — the value a bbox wants, since a
                # crop must clear the tallest ascender, not the baseline.
                "y": round(line["_top"], 4),
                "h": round(line["h"], 4),
                "x0": round(line["x0"], 4),
                "x1": round(line["x1"], 4),
                "text": stripped,
            }
        )
    return out


def detect_chrome(pdf: Any) -> set[str]:
    """Return the set of line texts that are page furniture, not content.

    Chrome is only identifiable across pages: a running head, document-id banner or
    `N of M` footer repeats, body text does not. Scans every page, so cost is linear in
    the document.
    """
    repeats: Counter[str] = Counter()
    for pg in pdf:
        for line in assemble_lines(pg):
            if len(line["text"]) < 90:
                repeats[line["text"]] += 1
    threshold = max(3, len(pdf) * _CHROME_PAGE_RATIO)
    return {t for t, c in repeats.items() if c >= threshold}


def is_chrome(text: str, chrome_text: set[str]) -> bool:
    """True if a line is page furniture — repeated across pages, or a page number."""
    return text in chrome_text or bool(
        re.fullmatch(r"\d+\s+of\s+\d+|Page\s+\d+|\d+", text)
    )


def body_band(lines: list[dict], chrome_text: set[str]) -> tuple[float, float] | None:
    """Return (top, bottom) of the non-chrome content on a page, or None if blank."""
    body = [line for line in lines if not is_chrome(line["text"], chrome_text)]
    if not body:
        return None
    return (
        round(min(line["y"] for line in body), 4),
        round(max(line["y"] + line["h"] for line in body), 4),
    )


def classify_headings(
    lines: list[dict], chrome_text: set[str]
) -> tuple[list[dict], float]:
    """Annotate `lines` in place with `chrome`/`heading` bools; return (heading
    candidates, body glyph height).

    Modal glyph height is taken as the body text size — mode rather than mean, because
    footnotes drag a mean down and headings drag it up. See `_HEADING_HEIGHT_RATIO` for
    what counts as a heading candidate and its caveats.
    """
    heights = Counter(line["h"] for line in lines)
    body_h = heights.most_common(1)[0][0] if heights else 0.0

    headings: list[dict] = []
    for line in lines:
        line["chrome"] = is_chrome(line["text"], chrome_text)
        line["heading"] = (
            not line["chrome"]
            and body_h > 0
            and line["h"] >= body_h * _HEADING_HEIGHT_RATIO
            and bool(_NUMBERED.match(line["text"]))
        )
        if line["heading"]:
            headings.append({"y": line["y"], "h": line["h"], "text": line["text"]})
    return headings, body_h


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
