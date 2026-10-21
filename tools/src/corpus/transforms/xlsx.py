"""OOXML spreadsheet transforms — a worksheet selector plus a cell-range op (spec §6.2
`bbox=` on a spreadsheet, §12.11 `sheet=<name>` (+ `bbox=<A1-range>`)).

Grammar (selector + sub-op — mirrors the PDF `page=` and CSV `row=` selectors):

    sheet=<name>                 the worksheet's used range as text          -> xlsxsheet
    sheet=<name>&bbox=<A1-range> that cell range as text                     -> text
    sheet=<name>&crop=<A1-range> alias for bbox (spec §6.2)                  -> text

`sheet=<name>` yields an intermediate `xlsxsheet` working value (`XlsxSheetRef`). A
**terminal** `sheet=<name>` renders the sheet's used range (trailing all-blank rows and
columns trimmed) in the resolver, exactly as a terminal `row=N` renders the row's raw
text — so a stored segment's `address: sheet=<name>` resolves.

**The rendering contract** (what a cited cell range reads as, pinned by `ENGINE_VERSION`):

- Values are the workbook's CACHED values (`openpyxl` `data_only=True`) — what Excel last
  displayed. A formula cell reads as its last-saved result; a workbook saved without
  cached results (some generators never compute them) reads empty for those cells. The
  formula text itself is never the reading.
- One cell → `cell_text`: empty for no value, `TRUE`/`FALSE` for booleans, ISO-8601 for
  dates/times, Python `str()` for numbers (`5`, `0.25`, `1e-05` — the stored number, not
  the cell's display format), and a string's characters verbatim (embedded newlines and
  tabs kept).
- Cells in a row are joined by a TAB; rows by a NEWLINE (`\\n`). A `bbox=` range renders
  its exact rectangle, blank cells included; a bare `sheet=` renders A1 through the last
  populated row and column.

The drafter (`corpus.draft.xlsx`) renders the SAME cells through the same `cell_text`
(plus markdown-table escaping), so a quote taken from a drafted body verifies against
the resolved range and vice versa — two surfaces, one reading of each cell.

`openpyxl` (the `[office]` extra) is imported lazily: importing this module registers
the handlers without it; resolving raises a clear ImportError.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from . import RenderContext, register

#: Versioned op id (spec §6.4 / `ledger.md` §13.2's op-version pin), folded into the
#: resolver's cache key and sidecar whenever a `sheet=` param is present. Pinned on
#: `sheet` (the axis every spreadsheet reading starts from) rather than on the
#: polymorphic `bbox`, whose param name the image crop shares. Bump on ANY change to the
#: rendering contract above — value formatting, separators, trimming.
ENGINE_VERSION = "xlsx-sheet@1"

_A1_RE = re.compile(r"^\$?([A-Z]{1,3})\$?([1-9][0-9]*)$")


@dataclass(frozen=True)
class XlsxSheetRef:
    """A selected worksheet: the workbook on disk plus the sheet's exact tab name."""

    path: Path
    name: str


def _openpyxl():
    try:
        import openpyxl
    except ImportError as e:
        raise ImportError(
            "resolving a spreadsheet `sheet=` address requires the `[office]` extra "
            "(openpyxl). Install with: uv tool install --editable 'tools[office]'"
        ) from e
    return openpyxl


def cell_text(value: Any) -> str:
    """One cell's reading (the rendering contract above) — shared with the drafter."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


def _col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


def col_letters(index: int) -> str:
    """1-based column index → A1 letters (1 → `A`, 27 → `AA`)."""
    out = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


def parse_a1_range(value: str | None) -> tuple[int, int, int, int]:
    """`B2:G30` / `A1` → `(min_row, min_col, max_row, max_col)`, 1-based inclusive.
    Strict: upper-case column letters, a first corner above-left of the second. Anything
    else (relative floats meant for an image, `A:C` whole columns, a reversed range) is
    a ValueError naming the grammar."""
    if value is None or not value.strip():
        raise ValueError("bbox= on a spreadsheet requires an A1 range (e.g. bbox=B2:G30)")
    text = value.strip()
    corners = text.split(":")
    if len(corners) not in (1, 2):
        raise ValueError(f"bbox={value!r}: not an A1 range (expected e.g. B2:G30 or A1)")
    parsed = []
    for corner in corners:
        m = _A1_RE.match(corner)
        if m is None:
            raise ValueError(
                f"bbox={value!r}: {corner!r} is not an A1 cell reference — a spreadsheet "
                f"bbox is a cell range (e.g. bbox=B2:G30), not relative image coordinates"
            )
        parsed.append((int(m.group(2)), _col_index(m.group(1))))
    (r0, c0), (r1, c1) = parsed[0], parsed[-1]
    if r1 < r0 or c1 < c0:
        raise ValueError(
            f"bbox={value!r}: the first corner must be above and left of the second"
        )
    return r0, c0, r1, c1


def _render_rows(rows: list[list[str]]) -> str:
    return "\n".join("\t".join(r) for r in rows)


def _read_rows(
    ref: XlsxSheetRef, bounds: tuple[int, int, int, int] | None
) -> list[list[str]]:
    wb = _openpyxl().load_workbook(ref.path, read_only=True, data_only=True)
    try:
        ws = wb[ref.name]
        if bounds is None:
            rows = [
                [cell_text(v) for v in row]
                for row in ws.iter_rows(min_row=1, min_col=1, values_only=True)
            ]
            while rows and not any(rows[-1]):
                rows.pop()
            width = max(
                (i + 1 for r in rows for i, c in enumerate(r) if c), default=0
            )
            return [(r + [""] * width)[:width] for r in rows]
        r0, c0, r1, c1 = bounds
        width = c1 - c0 + 1
        out: list[list[str]] = []
        for row in ws.iter_rows(
            min_row=r0, max_row=r1, min_col=c0, max_col=c1, values_only=True
        ):
            cells = [cell_text(v) for v in row]
            out.append((cells + [""] * width)[:width])
        # read-only mode stops at the sheet's last stored row; a range reaching past it
        # still renders its full rectangle (blank rows), so the shape never depends on
        # where the workbook's data happens to end
        while len(out) < r1 - r0 + 1:
            out.append([""] * width)
        return out
    finally:
        wb.close()


@register("xlsx", "sheet", "xlsxsheet")
def select_sheet(path: Path, value: str | None, ctx: RenderContext) -> XlsxSheetRef:
    """`?sheet=<name>` — the worksheet with exactly this tab name (case-sensitive; the
    URI parser has already percent-decoded `%26`/`%23`/`%25`)."""
    if value is None or value == "":
        raise ValueError("sheet= requires a worksheet tab name")
    wb = _openpyxl().load_workbook(path, read_only=True, data_only=True)
    try:
        worksheets = [ws.title for ws in wb.worksheets]
        if value not in worksheets:
            if value in wb.sheetnames:
                raise ValueError(
                    f"sheet={value!r} is a chart sheet — it has no cells to read"
                )
            raise ValueError(
                f"sheet={value!r}: no such worksheet (workbook has {worksheets})"
            )
    finally:
        wb.close()
    return XlsxSheetRef(path=Path(path), name=value)


def render_sheet(ref: XlsxSheetRef) -> str:
    """A terminal `sheet=<name>`: the used range (A1 through the last populated row and
    column) as text."""
    return _render_rows(_read_rows(ref, None))


@register("xlsxsheet", "bbox", "text")
def select_range(ref: XlsxSheetRef, value: str | None, ctx: RenderContext) -> str:
    """`?sheet=<name>&bbox=<A1-range>` — that rectangle as text."""
    return _render_rows(_read_rows(ref, parse_a1_range(value)))


@register("xlsxsheet", "crop", "text")
def select_range_crop(ref: XlsxSheetRef, value: str | None, ctx: RenderContext) -> str:
    """`crop=` — alias for `bbox=` (spec §6.2)."""
    return select_range(ref, value, ctx)
