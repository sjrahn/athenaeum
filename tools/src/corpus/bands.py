"""Pixel-truth page geometry: measure text rows from the rendered raster.

`transforms.pdf.assemble_lines` reads geometry from the PDF's text layer, which
is fast and exact when the text layer is well-formed. It is not always. On pages
carrying Mathematical-Italic Unicode (U+1D400 block) it reports visually distinct
lines at identical baselines and shreds others into per-word fragments — and
those equation-heavy pages are precisely the ones whose addressing is hardest to
get right by eye, so the text-layer check goes quiet exactly where it is needed.

This module measures the same thing from the rendered image instead. Ink is
projected onto the vertical axis; runs of inked scanlines separated by more than
a line's leading become rows. It cannot be defeated by any text-layer defect,
because it never reads the text layer — which is also its limitation: it locates
rows, it cannot say what they say.

Use it to answer "where is the content on this page, really", and to check that
a record's `page=N&bbox=` bands land on content boundaries rather than through
the middle of a line.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# The darkest a pixel may be and still read as paper, on a light page (0=black, 255=white):
# the ceiling under the paper-relative cut (`BG_DELTA`, below). Antialiased glyph edges on a
# white page sit well below 200; JPEG ringing sits well above it.
INK_THRESHOLD = 200

# Inked runs separated by fewer than this many pixels are one row. Sized to
# absorb intra-line leading (the gap between a descender and the next line's
# ascender) without merging separate paragraphs: at the resolver's 1568px
# longest edge an A4 page renders body leading at roughly 4-5px and paragraph
# spacing at 14px or more.
MIN_GAP_PX = 6

# How far a band edge may sit inside a row before it counts as cutting it,
# rather than merely touching the row's antialiased boundary.
CUT_TOL = 0.0015

# Whitespace a band may carry beyond the ink it contains before the band counts
# as drifted off its content. Generous: a band legitimately padded away from its
# text stays quiet, a band shifted onto the wrong block does not.
DRIFT_TOL = 0.02


@dataclass(frozen=True)
class Row:
    """One measured run of ink, as a fraction of page height."""

    top: float
    bottom: float

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass(frozen=True)
class BandFinding:
    kind: str  # "cuts" | "opaque" | "chrome" | "drift"
    page: int
    line: int  # 1-indexed line in the record file
    detail: str


def ink_rows(
    image_path: Path,
    *,
    min_gap_px: int = MIN_GAP_PX,
) -> list[Row]:
    """Measure text rows in a rendered page image, top to bottom — the whole page's rows on
    its cleaned ink mask (`PageInk`, below). Pillow only — no numpy."""
    return PageInk(image_path).rows(min_gap_px=min_gap_px)


# ---------- the cleaned ink mask (bands v2, 2026-09-28) ---------- #
#
# `ink_rows` above projects every pixel darker than a fixed threshold across the full page
# width, and three kinds of page defeat it (arbre-ath-steven's 96-run PDF eval, all three
# reproduced on committed records):
#
# - a full-bleed photograph inks every scanline, so the page measures as ONE row [0, 1] and
#   every band edge on it reports as a cut (e00c8dfa: 64 of them);
# - a scan's box rules ink every scanline they cross (the rules around f1452162's account
#   summary merge [0.12, 0.65] into one row), and its show-through (the reverse side, bleeding
#   at ~200 on a 236 paper tone) sits under the fixed threshold;
# - on a two-column page the right column's lines fill the left column's paragraph gaps
#   (e84ada4d: a left-column band's edge measured against a row [0.286, 0.49] that only exists
#   when both columns are projected together).
#
# `PageInk` answers the audit's real question — does the line y=edge, across the BAND's own
# x-range, slice through a line of text? — with three corrections, one per failure: ink is
# measured against the page's own paper tone (the histogram mode), ink in long vertical runs
# (rules, photographs) is removed before projecting, and the test is local: a window around
# the edge, split into columns at its gutters, each column measured on its own. A column whose
# ink is unbroken across the whole window is not a text row at all (photo, background) and is
# reported as unmeasurable rather than as a cut.

# Renders taller than this are box-downsampled first — a 9165px scan measures no better than a
# 2339px one, and area-averaging is itself the denoise a scan's specks need.
MAX_MEASURE_HEIGHT = 2400

# Ink is at least this far from the page's paper tone (the histogram mode). On a white page
# this is 195, the fixed threshold's old neighbourhood; on a scan's 236 paper it is 176, under
# the show-through band.
BG_DELTA = 60

# A vertical ink run longer than this fraction of the page height is not glyph ink — no
# character stands that tall — so it is a rule, a box edge, or a picture, and it is removed
# before rows are projected. Sized well above a display title's cap height (~0.05).
RULE_MIN_FRAC = 0.08

# A scanline counts as inked when at least this share of the measured width is ink (and never
# fewer than MIN_INK_PX pixels): a scan's show-through survives any tone threshold as sparse
# dark specks, about one pixel per scanline, where a line of text inks dozens.
MIN_INK_FRAC = 0.01
MIN_INK_PX = 2

# The window around an edge the local test reads, as a fraction of page height either side.
EDGE_WINDOW = 0.05

# A row thinner than this (fraction of page height) is a horizontal rule, not a line of text —
# the smallest print a page carries (6pt, ~0.005) stands taller. An edge along a rule cuts
# nothing a reader needs.
MIN_TEXT_ROW = 0.003

# A run of ink-free pixel columns at least this wide (fraction of page width) separates two
# columns of text; a word space (~0.005) does not.
GUTTER_FRAC = 0.012


class PageInk:
    """One rendered page, measured on demand (see the block comment). `rows()` reads the page
    under its own paper tone; `edge_cut()` re-reads the window around the edge under the
    WINDOW's paper tone, because a page's tone is not uniform — a light-text-on-dark panel
    on an otherwise white page measures as solid ink under the page's."""

    def __init__(self, image_path: Path, *, max_height: int = MAX_MEASURE_HEIGHT) -> None:
        from PIL import Image

        with Image.open(image_path) as im:
            gray = im.convert("L")
        if gray.height > max_height:
            gray = gray.resize(
                (max(1, round(gray.width * max_height / gray.height)), max_height), Image.BOX
            )
        self.gray = gray
        self.width, self.height = gray.size
        self._rule_px = max(2, round(self.height * RULE_MIN_FRAC))
        self._page: _Ink | None = None

    def _px(self, v: float, axis: int) -> int:
        size = self.width if axis == 0 else self.height
        return max(0, min(size, round(v * size)))

    def _ink(self, xa: int, xb: int, ya: int, yb: int) -> _Ink:
        """The cleaned ink mask of a box, toned by that box's own paper. Rule removal reads a
        rule's full length, so the crop it runs on is padded a rule's length either way."""
        pa, pb = max(0, ya - self._rule_px), min(self.height, yb + self._rule_px)
        tone = self.gray.crop((xa, ya, xb, yb))
        mask = _clean_mask(self.gray.crop((xa, pa, xb, pb)), _paper(tone), self._rule_px)
        return _Ink(mask.crop((0, ya - pa, xb - xa, yb - pa)), xa, ya, self.width, self.height)

    def rows(
        self,
        x0: float = 0.0,
        x1: float = 1.0,
        y0: float = 0.0,
        y1: float = 1.0,
        *,
        min_gap_px: int = MIN_GAP_PX,
    ) -> list[Row]:
        """Text rows inside the box, in page fractions — `ink_rows`, on the cleaned mask."""
        if self._page is None:
            self._page = self._ink(0, self.width, 0, self.height)
        return self._page.rows(
            self._px(x0, 0), self._px(x1, 0), self._px(y0, 1), self._px(y1, 1), min_gap_px
        )

    def edge_cut(
        self, edge: float, x0: float = 0.0, x1: float = 1.0, *, cut_tol: float = CUT_TOL
    ) -> tuple[str, Row, tuple[float, float]] | None:
        """Does the line y=edge across [x0, x1] slice a text row? `("cuts", row, column)`
        when it does, `("opaque", row, column)` when the ink it meets is unbroken
        across the whole window (a picture, a background — no row to cut), else None."""
        xa, xb = self._px(x0, 0), self._px(x1, 0)
        ya = self._px(max(0.0, edge - EDGE_WINDOW), 1)
        yb = self._px(min(1.0, edge + EDGE_WINDOW), 1)
        if xb <= xa or yb <= ya:
            return None
        win = self._ink(xa, xb, ya, yb)
        unmeasured = None
        for ca, cb in win.columns(xa, xb, ya, yb, max(2, round(self.width * GUTTER_FRAC))):
            col = (round(ca / self.width, 4), round(cb / self.width, 4))
            for row in win.rows(ca, cb, ya, yb, MIN_GAP_PX):
                if row.height < MIN_TEXT_ROW:
                    continue
                if not row.top + cut_tol < edge < row.bottom - cut_tol:
                    continue
                if win.unbroken(ca, cb, ya, yb):
                    unmeasured = unmeasured or ("opaque", row, col)
                    continue
                return ("cuts", row, col)
        return unmeasured


class _Ink:
    """A cleaned ink mask (L, 0/255) whose top-left sits at page pixel (ox, oy); every
    method takes and returns PAGE coordinates."""

    def __init__(self, mask, ox: int, oy: int, page_w: int, page_h: int) -> None:
        self.mask, self.ox, self.oy = mask, ox, oy
        self.page_w, self.page_h = page_w, page_h
        self._profiles: dict[tuple, list[int]] = {}

    def _scan_counts(self, xa: int, xb: int, ya: int, yb: int) -> list[int]:
        """Ink pixels on each scanline of the box, top to bottom (one C-level resize)."""
        key = (xa, xb, ya, yb)
        if key not in self._profiles:
            from PIL import Image

            box = (xa - self.ox, ya - self.oy, xb - self.ox, yb - self.oy)
            col = self.mask.crop(box).resize((1, yb - ya), Image.BOX)
            self._profiles[key] = [round(v * (xb - xa) / 255) for v in col.tobytes()]
        return self._profiles[key]

    def rows(self, xa: int, xb: int, ya: int, yb: int, min_gap_px: int) -> list[Row]:
        if xb <= xa or yb <= ya:
            return []
        floor = _ink_floor(xb - xa)
        flags = [c >= floor for c in self._scan_counts(xa, xb, ya, yb)]
        return [
            Row(round((ya + a) / self.page_h, 4), round((ya + b) / self.page_h, 4))
            for a, b in _runs(flags, min_gap_px)
        ]

    def columns(self, xa: int, xb: int, ya: int, yb: int, gutter: int) -> list[tuple[int, int]]:
        """The inked x-spans of the box, split at ink-free gutters at least `gutter` wide."""
        from PIL import Image

        box = (xa - self.ox, ya - self.oy, xb - self.ox, yb - self.oy)
        strip = self.mask.crop(box).resize((xb - xa, 1), Image.BOX)
        return [(xa + a, xa + b) for a, b in _runs([v > 0 for v in strip.tobytes()], gutter)]

    def unbroken(self, xa: int, xb: int, ya: int, yb: int) -> bool:
        """True when no scanline of the box is blank — text lines always leave one between
        them, however tight the leading; a picture or a background never does."""
        floor = _ink_floor(xb - xa)
        return all(c >= floor for c in self._scan_counts(xa, xb, ya, yb))


def _paper(gray) -> int:
    """The paper tone: the most common gray level."""
    hist = gray.histogram()
    return max(range(256), key=hist.__getitem__)


def _clean_mask(gray, paper: int, rule_px: int):
    """Ink against `paper` (dark ink on light paper, light ink on dark), less every pixel
    lying in a vertical run at least `rule_px` tall."""
    from PIL import ImageChops

    if paper >= 128:
        cut = min(INK_THRESHOLD, paper - BG_DELTA)
        ink = gray.point(lambda v: 255 if v < cut else 0)
    else:
        cut = paper + BG_DELTA
        ink = gray.point(lambda v: 255 if v > cut else 0)
    return ImageChops.subtract(ink, _long_vertical_runs(ink, rule_px))


def _ink_floor(width_px: int) -> int:
    return max(MIN_INK_PX, round(width_px * MIN_INK_FRAC))


class TextLayer:
    """A PDF's text-layer words, page by page — the second opinion on a raster cut.

    Ink cannot tell a glyph from a stroke: on vector line art (an assembly diagram's callout
    label) the strokes around a label merge with it into one tall "row", and every edge of the
    label's own band measures as a cut (arbre-ath-steven's v50 validation, 2026-09-29: 3-7 per
    run on an IKEA manual, every one a label band inside a drawing). Where a page carries a
    text layer, a cut is a cut only if a word's box straddles the edge inside the band's
    x-range; a page with no words (a scan, a drawing with outlined text) keeps the raster's
    verdict."""

    def __init__(self, pdf_path: Path) -> None:
        import pypdfium2 as pdfium

        self._doc = pdfium.PdfDocument(str(pdf_path))
        self._words: dict[int, list[dict]] = {}

    def words(self, page: int) -> list[dict]:
        if page not in self._words:
            from corpus import pdf_introspect

            try:
                self._words[page] = pdf_introspect.page_words(self._doc, page - 1)["words"]
            except Exception:
                self._words[page] = []
        return self._words[page]

    def close(self) -> None:
        self._doc.close()


# A text-layer word box under-reports its glyphs' rendered extent — math, accents, sub- and
# superscripts reach past it — so an edge anywhere inside a word's box, however close to its
# rim, confirms the cut (no `CUT_TOL` margin: the box is already tight), and each box is padded
# by this share of its own height to catch an edge grazing ink just past it. Relative to the
# word, so a small label and a large heading behave alike. Measured 2026-09-29 against the two
# cases that bound it: an edge 0.0002 inside an `A₀` box (e84ada4d p2) must confirm, and a
# callout label's band drawn 0.002-0.003 clear of its 0.043-tall word (4855c63a p5) must not —
# 15% of that word is 0.0065, so the pad stays well under 5%.
WORD_GRAZE_FRAC = 0.04


def word_crosses(words: list[dict], edge: float, x0: float, x1: float) -> bool:
    """True when some word overlapping [x0, x1] has `edge` inside its (padded) box."""
    for w in words:
        x, y, bw, bh = w["bbox"]
        pad = bh * WORD_GRAZE_FRAC
        if x < x1 and x + bw > x0 and y - pad < edge < y + bh + pad:
            return True
    return False


def confirm_cut(
    hit: tuple[str, Row, tuple[float, float]] | None,
    words: list[dict] | None,
    edge: float,
    x0: float,
    x1: float,
) -> tuple[str, Row, tuple[float, float]] | None:
    """A raster `cuts` verdict, confirmed against the text layer where the page has one: with
    words on the page and none straddling the edge, the ink it cut is drawing, not text —
    reported `opaque`."""
    if hit is None or hit[0] != "cuts" or not words:
        return hit
    if word_crosses(words, edge, x0, x1):
        return hit
    return ("opaque", hit[1], hit[2])


def _runs(flags: list[bool], min_gap: int) -> list[tuple[int, int]]:
    """Half-open [a, b) runs of True, bridging False gaps shorter than `min_gap`."""
    out: list[list[int]] = []
    start: int | None = None
    for i, f in enumerate(flags):
        if f and start is None:
            start = i
        elif not f and start is not None:
            out.append([start, i])
            start = None
    if start is not None:
        out.append([start, len(flags)])
    merged: list[list[int]] = []
    for run in out:
        if merged and run[0] - merged[-1][1] < min_gap:
            merged[-1][1] = run[1]
        else:
            merged.append(run)
    return [(a, b) for a, b in merged]


def _long_vertical_runs(ink, length: int):
    """The pixels of `ink` (L, 0/255) lying in a vertical run at least `length` tall — an
    erosion then a dilation by a one-pixel-wide column `length` tall, each built from
    log-doubling shifts (Pillow only)."""
    from PIL import ImageChops

    def shifted(im, dy: int):
        from PIL import Image

        out = Image.new("L", im.size, 0)
        w, h = im.size
        if dy > 0:  # content moves up: out[y] = im[y + dy]
            out.paste(im.crop((0, dy, w, h)), (0, 0))
        else:
            out.paste(im.crop((0, 0, w, h + dy)), (0, -dy))
        return out

    eroded, span, step = ink, 1, 1
    while span < length:
        k = min(step, length - span)
        eroded = ImageChops.darker(eroded, shifted(eroded, k))
        span += k
        step *= 2
    grown, span, step = eroded, 1, 1
    while span < length:
        k = min(step, length - span)
        grown = ImageChops.lighter(grown, shifted(grown, -k))
        span += k
        step *= 2
    return grown



# Chrome lives in the page margins. Recurrence alone is NOT enough to identify
# it: body paragraphs near the top of a page align across pages often enough to
# be mistaken for a running header (measured — a two-line list item at
# [0.1288, 0.1562] recurred on 3 of 6 pages of `A6.4-STAN-METH-005` and was
# wrongly classified until this gate was added). A candidate must therefore both
# recur AND sit outside the text block.
CHROME_TOP_MAX = 0.12  # a header ends above this
CHROME_BOTTOM_MIN = 0.93  # a footer begins below this


def detect_chrome(
    rows_by_page: dict[int, list[Row]],
    *,
    tol: float = 0.004,
    min_ratio: float = 0.7,
) -> list[Row]:
    """Rows that recur at the same y across most pages AND sit in a margin.

    A running header sits at the same height on every page; body text only
    appears to. Needs no text layer, so it works on the equation pages where
    `transforms.pdf.detect_chrome` cannot be trusted.
    """
    if len(rows_by_page) < 3:
        return []
    clusters: list[tuple[float, float, set[int]]] = []
    for page, rows in rows_by_page.items():
        for row in rows:
            if not (row.bottom <= CHROME_TOP_MAX or row.top >= CHROME_BOTTOM_MIN):
                continue
            for i, (top, bottom, pages) in enumerate(clusters):
                if abs(top - row.top) <= tol and abs(bottom - row.bottom) <= tol:
                    pages.add(page)
                    clusters[i] = (top, bottom, pages)
                    break
            else:
                clusters.append((row.top, row.bottom, {page}))
    threshold = max(2, int(len(rows_by_page) * min_ratio))
    return [
        Row(top, bottom)
        for top, bottom, pages in clusters
        if len(pages) >= threshold
    ]


def _is_chrome(row: Row, chrome: list[Row], tol: float = 0.004) -> bool:
    return any(
        abs(row.top - c.top) <= tol and abs(row.bottom - c.bottom) <= tol
        for c in chrome
    )


def audit_bands(
    bands: list[tuple],
    rows_for_page,
    *,
    cut_tol: float = CUT_TOL,
    drift_tol: float = DRIFT_TOL,
    chrome: list[Row] | None = None,
    page_ink=None,
    page_words=None,
) -> list[BandFinding]:
    """Check `(page, top, bottom, source_line[, x0, x1])` bands against measured rows.

    `rows_for_page(page)` supplies the page's rows, so the caller controls
    rendering and caching. Pass `chrome` (from `detect_chrome`) to enable the
    chrome check and to keep running header/footer ink out of the drift
    measurement — without it a band that swallows the footer measures as
    perfectly tight, because the footer is ink like any other.

    Pass `page_ink(page) -> PageInk | None` to measure each band against its OWN x-range
    (`PageInk.edge_cut` for the cut test, the band's columns only for drift) — the only
    measurement that survives full-bleed pages, scans, and multi-column layouts. An edge
    over unbroken ink (a picture, a background) is reported as `opaque`, never as a cut.
    Pass `page_words(page) -> list[word]` (`TextLayer.words`) to confirm each raster cut
    against the text layer (`confirm_cut`): on a page with words, a cut no word straddles is
    drawing ink, reported `opaque`.
    """
    chrome = chrome or []
    findings: list[BandFinding] = []
    for band in bands:
        page, top, bottom, line = band[:4]
        x0, x1 = (band[4], band[5]) if len(band) >= 6 else (0.0, 1.0)
        ink = page_ink(page) if page_ink is not None else None
        rows = ink.rows(x0, x1) if ink is not None else rows_for_page(page)
        if not rows:
            continue
        for edge, which in ((top, "top"), (bottom, "bottom")):
            if edge <= 0.0 or edge >= 1.0:
                continue
            if ink is not None:
                hit = ink.edge_cut(edge, x0, x1, cut_tol=cut_tol)
                if page_words is not None:
                    hit = confirm_cut(hit, page_words(page), edge, x0, x1)
                if hit is not None:
                    kind, row, (ca, cb) = hit
                    findings.append(
                        BandFinding(
                            "cuts" if kind == "cuts" else "opaque", page, line,
                            f"{which} edge {edge} falls inside the text row "
                            f"[{row.top}, {row.bottom}] (columns [{ca}, {cb}])"
                            if kind == "cuts" else
                            f"{which} edge {edge} crosses non-text ink "
                            f"[{row.top}, {row.bottom}] (columns [{ca}, {cb}]) — a picture, "
                            f"a background, or drawing strokes no text-layer word spans",
                        )
                    )
                continue
            for row in rows:
                if row.top + cut_tol < edge < row.bottom - cut_tol:
                    findings.append(
                        BandFinding(
                            "cuts", page, line,
                            f"{which} edge {edge} falls inside the text row "
                            f"[{row.top}, {row.bottom}]",
                        )
                    )
                    break
        inside = [r for r in rows if r.top >= top - 0.004 and r.bottom <= bottom + 0.004]
        swallowed = [r for r in inside if _is_chrome(r, chrome)]
        for row in swallowed:
            findings.append(
                BandFinding(
                    "chrome", page, line,
                    f"band [{top}, {bottom}] contains running chrome at "
                    f"[{row.top}, {row.bottom}]",
                )
            )
        content = [r for r in inside if not _is_chrome(r, chrome)]
        if content:
            first, last = content[0].top, content[-1].bottom
            lead, trail = first - top, bottom - last
            if lead > drift_tol or trail > drift_tol:
                findings.append(
                    BandFinding(
                        "drift", page, line,
                        f"band [{top}, {bottom}] holds content only in "
                        f"[{round(first, 4)}, {round(last, 4)}] "
                        f"(lead {round(lead, 4)}, trail {round(trail, 4)})",
                    )
                )
    return findings


def uncovered(
    bands: list[tuple],
    rows_by_page: dict[int, list[Row]],
    chrome: list[Row],
    *,
    tol: float = 0.004,
    min_chars_height: float = 0.004,
) -> list[tuple[int, Row]]:
    """Content rows on addressed pages that no band covers.

    The defect this catches is silent: a boundary landing in whitespace orphans
    a heading between two bands. It cuts nothing and drifts nothing — the
    content simply never appears in any crop.
    """
    by_page: dict[int, list[tuple[float, float]]] = {}
    for page, top, bottom, *_ in bands:
        by_page.setdefault(page, []).append((top, bottom))
    out: list[tuple[int, Row]] = []
    for page, spans in sorted(by_page.items()):
        for row in rows_by_page.get(page, []):
            if _is_chrome(row, chrome) or row.height < min_chars_height:
                continue
            mid = (row.top + row.bottom) / 2
            if not any(a - tol <= mid <= b + tol for a, b in spans):
                out.append((page, row))
    return out


def matches_chrome_profile(
    row: Row,
    chrome: list[Row],
    *,
    height_tol: float = 0.002,
    y_tol: float = 0.025,
) -> bool:
    """True when a row has a chrome cluster's exact shape but a shifted y.

    `detect_chrome` clusters rows by y within 0.004, which a footer that moves
    between the front matter and the body defeats. On A6.4-STAN-METH-003 the
    "N of 16" footer sits at [0.9554, 0.9643] on body pages but [0.9401, 0.949]
    on the table-of-contents page — the same height to four decimals, y off by
    0.0153, four times the clustering tolerance. That row then reports as
    uncovered *content*, and a normalizer "fixing" it bands the footer, turning
    a phantom gap into a real chrome swallow. One did exactly that this wave
    until told otherwise.

    This deliberately does NOT suppress anything — `uncovered` still returns the
    row. Loosening the chrome clustering itself would risk swallowing a genuine
    short line in the margin, and hiding content loss is the one failure this
    module exists to prevent. It only lets a caller mark which uncovered rows
    carry a running-furniture signature, so an operator can tell a phantom from
    real loss without rendering the crop.
    """
    return any(
        abs(row.height - c.height) <= height_tol
        and abs(row.top - c.top) <= y_tol
        and (row.bottom <= CHROME_TOP_MAX or row.top >= CHROME_BOTTOM_MIN)
        for c in chrome
    )


def snap(edge: float, rows: list[Row]) -> float | None:
    """Nearest whitespace midpoint to `edge`, or None if there is no gap.

    A convenience for repairing a single cutting edge. It deliberately does NOT
    repair a *shifted* band: snapping moves an edge to the closest gap, and when
    a whole band sits on the wrong block the closest gap is the wrong one. Those
    need the body re-matched to the page, not a nudge.
    """
    gaps = [
        ((rows[i].bottom + rows[i + 1].top) / 2)
        for i in range(len(rows) - 1)
        if rows[i + 1].top > rows[i].bottom
    ]
    if not gaps:
        return None
    return round(min(gaps, key=lambda g: abs(g - edge)), 4)
