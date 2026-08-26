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

# A scanline counts as inked if any pixel is at least this dark (0=black,
# 255=white). Antialiased glyph edges on a white page sit well below 200; JPEG
# ringing and scan noise sit well above it.
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
    kind: str  # "cuts" | "drift"
    page: int
    line: int  # 1-indexed line in the record file
    detail: str


def ink_rows(
    image_path: Path,
    *,
    ink_threshold: int = INK_THRESHOLD,
    min_gap_px: int = MIN_GAP_PX,
) -> list[Row]:
    """Measure text rows in a rendered page image, top to bottom.

    Pillow only — no numpy. `getextrema()` on a 1px-tall crop of the grayscale
    image is a C-level min/max scan of that scanline; two Pillow calls per row
    is fast enough that a per-pixel Python loop is never needed.
    """
    from PIL import Image

    with Image.open(image_path) as im:
        gray = im.convert("L")
        width, height = gray.size
        if not height:
            return []
        inked = [
            gray.crop((0, y, width, y + 1)).getextrema()[0] < ink_threshold
            for y in range(height)
        ]

    runs: list[list[int]] = []
    start: int | None = None
    for i, is_ink in enumerate(inked):
        if is_ink and start is None:
            start = i
        elif not is_ink and start is not None:
            runs.append([start, i])
            start = None
    if start is not None:
        runs.append([start, height])

    merged: list[list[int]] = []
    for run in runs:
        if merged and run[0] - merged[-1][1] < min_gap_px:
            merged[-1][1] = run[1]
        else:
            merged.append(run)
    return [Row(round(a / height, 4), round(b / height, 4)) for a, b in merged]


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
    bands: list[tuple[int, float, float, int]],
    rows_for_page,
    *,
    cut_tol: float = CUT_TOL,
    drift_tol: float = DRIFT_TOL,
    chrome: list[Row] | None = None,
) -> list[BandFinding]:
    """Check `(page, top, bottom, source_line)` bands against measured rows.

    `rows_for_page(page)` supplies the page's rows, so the caller controls
    rendering and caching. Pass `chrome` (from `detect_chrome`) to enable the
    chrome check and to keep running header/footer ink out of the drift
    measurement — without it a band that swallows the footer measures as
    perfectly tight, because the footer is ink like any other.
    """
    chrome = chrome or []
    findings: list[BandFinding] = []
    for page, top, bottom, line in bands:
        rows = rows_for_page(page)
        if not rows:
            continue
        for edge, which in ((top, "top"), (bottom, "bottom")):
            if edge <= 0.0 or edge >= 1.0:
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
    bands: list[tuple[int, float, float, int]],
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
    for page, top, bottom, _ in bands:
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
