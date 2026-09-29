"""Per-page text coverage: how much of a born-digital PDF page's text layer the record renders.

The one critical failure of arbre-ath-steven's 96-run PDF eval (2026-09-28) passed every gate:
a normalize pass replaced page 3's ~11k characters of fine print with a copy of page 1's
transaction table, reported the page "reflowed", and lint was clean. Nothing compared a
page's rendering with the page. For a born-digital page the comparison is cheap and needs no
judgment — the text layer is the page's own words — so this module makes it:

    coverage(page) = |words the page's addressed regions carry ∩ words its segments render|
                     / |words the page's addressed regions carry|

Only the regions the record ADDRESSES are counted — `page=N&bbox=…` limits the page's words to
the band, a bare `page=N` takes the whole page — so a region the record deliberately leaves
out (chrome, a form's sanctioned drop) costs nothing here; that is `corpus bands`'s uncovered
report, a different question. Words are compared as sets of NFKC-folded, lowercased tokens of
three or more letters/digits, which survives reflow, markdown, and table pipes, and loses only
what a faithful rendering legitimately changes (a word hyphenated across a line, math the
record typesets as LaTeX) — hence a generous threshold, owned by the lint rule.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"[^\W_]{3,}")
_PAGE_RE = re.compile(r"(?:^|&)page=(\d+)(?:&|$)")
_BBOX_RE = re.compile(r"(?:^|&)bbox=([\d.]+),([\d.]+),([\d.]+),([\d.]+)(?:&|$)")
_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|<>~])")
_TAG_RE = re.compile(r"<[^>]+>")

# A page whose addressed regions carry fewer distinct tokens than this has too little text
# layer to judge — a scan, a figure page, a title page.
MIN_PAGE_TOKENS = 40

# How far outside a band a word's centre may sit and still count as inside it.
_BAND_TOL = 0.005


@dataclass(frozen=True)
class PageCoverage:
    page: int
    coverage: float
    tokens: int  # distinct tokens in the page's addressed regions
    missing: tuple[str, ...]  # a sample of the page tokens no segment renders


# Scripts written without spaces between words (Thai, Lao, Khmer, Myanmar, CJK, kana): a
# "word" there is wherever the text layer and the rendering happen to break a run, and the two
# break differently — so runs in these scripts compare as character bigrams instead.
_UNSPACED_RE = re.compile(
    "[\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff"
    "\uf900-\ufaff]+"
)


def tokens(text: str) -> set[str]:
    text = unicodedata.normalize("NFKC", text)
    text = _TAG_RE.sub(" ", _ESCAPE_RE.sub(r"\1", text))
    out: set[str] = set()
    for run in _UNSPACED_RE.findall(text):
        out.update(run[i : i + 2] for i in range(len(run) - 1))
    for tok in _TOKEN_RE.findall(_UNSPACED_RE.sub(" ", text)):
        out.add(tok.lower())
    return out


def _regions(address: str) -> tuple[int, tuple[float, float, float, float] | None] | None:
    page = _PAGE_RE.search(address)
    if page is None:
        return None
    box = _BBOX_RE.search(address)
    return int(page.group(1)), (tuple(float(v) for v in box.groups()) if box else None)


def page_coverage(segments: list[Any], pdf_path: Path) -> list[PageCoverage]:
    """Coverage of every born-digital page the record's text segments address, in page order.
    A scanned page is left out — its text layer, where it has one, is an OCR engine's guess
    (invisible text over a page image), not the page's own words — and so is a page with too
    little text layer to judge (`MIN_PAGE_TOKENS`)."""
    import pypdfium2 as pdfium
    from pypdf import PdfReader

    from corpus import pdf_introspect

    regions: dict[int, list[tuple[float, float, float, float] | None]] = {}
    rendered: dict[int, set[str]] = {}
    whole: set[str] = set()  # an address-less segment renders the whole transport
    for seg in segments:
        if seg.atom != "text" or not seg.body:
            continue
        body = tokens(seg.body)
        addrs = seg.address if isinstance(seg.address, list) else [seg.address]
        for addr in addrs:
            if addr is None:
                whole |= body
                continue
            parsed = _regions(str(addr))
            if parsed is None:
                continue
            page, box = parsed
            regions.setdefault(page, []).append(box)
            rendered.setdefault(page, set()).update(body)

    out: list[PageCoverage] = []
    reader = PdfReader(str(pdf_path))
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        for page in sorted(regions):
            if not 1 <= page <= len(doc) or _scanned(reader, page - 1):
                continue
            words = pdf_introspect.page_words(doc, page - 1).get("words", [])
            boxes = regions[page]
            have: set[str] = set()
            for w in words:
                x, y, bw, bh = w["bbox"]
                cx, cy = x + bw / 2, y + bh / 2
                if any(_inside(cx, cy, b) for b in boxes):
                    have |= tokens(w["text"])
            if len(have) < MIN_PAGE_TOKENS:
                continue
            got = rendered.get(page, set()) | whole
            missing = sorted(have - got)
            out.append(
                PageCoverage(
                    page=page,
                    coverage=round(1 - len(missing) / len(have), 3),
                    tokens=len(have),
                    missing=tuple(missing[:12]),
                )
            )
    finally:
        doc.close()
    return out


def region_tokens(doc: Any, addresses: str | list[str] | None) -> set[str] | None:
    """The text-layer tokens inside the region(s) an address names, from an open pypdfium2
    document — or None when an address names no PDF page region."""
    from corpus import pdf_introspect

    addrs = addresses if isinstance(addresses, list) else [addresses]
    out: set[str] = set()
    for addr in addrs:
        parsed = _regions(str(addr or ""))
        if parsed is None:
            return None
        page, box = parsed
        if not 1 <= page <= len(doc):
            return None
        for w in pdf_introspect.page_words(doc, page - 1).get("words", []):
            x, y, bw, bh = w["bbox"]
            if _inside(x + bw / 2, y + bh / 2, box):
                out |= tokens(w["text"])
    return out


def _scanned(reader: Any, index0: int) -> bool:
    from corpus import pdf_introspect

    try:
        pp = reader.pages[index0]
        return (
            pdf_introspect.max_image_coverage(pp, reader) >= pdf_introspect.SCANNED_COVERAGE
            or pdf_introspect.has_invisible_text(pp, reader)
        )
    except Exception:
        return True  # unjudgeable, so not judged


def _inside(cx: float, cy: float, box: tuple[float, float, float, float] | None) -> bool:
    if box is None:
        return True
    x, y, w, h = box
    return x - _BAND_TOL <= cx <= x + w + _BAND_TOL and y - _BAND_TOL <= cy <= y + h + _BAND_TOL
