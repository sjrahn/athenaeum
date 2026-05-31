"""XLS draft extraction (deterministic, no LLM).

Legacy Excel 97-2003 binary workbooks (OLE2 Compound Documents, not the OOXML zip
xlsx uses). Read via `xlrd` (the `[office]` extra), imported lazily so
`import corpus.draft` works without it.

- One Section per *visible* worksheet, addressed `sheet=<name>` (hidden sheets are
  internal chrome and skipped). Each sheet renders as a markdown table of cached cell
  values via the xlsx drafter's shared rendering helpers; empty sheets become a
  body-empty segment + an address-scoped `format-loss` issue (spec §4.3.3.1).
- Key gap vs xlsx: **formula detection is unavailable** — xlrd 2.x exposes only the
  cached value type, not `XL_CELL_FORMULA`, so every populated sheet renders its
  cached values regardless of whether they are user-entered or computed. The
  normalizer is the authority on calculator-vs-data routing for xls records.

Mode: `body-draft`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from corpus import touches
from corpus.draft import DrafterResult, register
from corpus.draft.xlsx import _col_label, _emit_markdown_table, _fmt_cell, loss_issue
from corpus.fingerprint import text as text_fp
from corpus.functional_uri import quote_value
from corpus.segments import Section, Segment

_ROW_CAP = 1000
_XLS_SCHEMA_ID = "application/application_vnd.ms-excel"

# Workbook-scope defined-name prefixes that are Excel internals, not author-meaningful.
_INTERNAL_NAME_PREFIXES = ("_FilterDatabase", "_xlnm.", "_xlfn.", "Print_")


def _xlrd():
    try:
        import xlrd
    except ImportError as e:
        raise ImportError(
            "xls drafting requires the `[office]` extra. Install with: "
            "uv pip install 'ath-corpus[office]'"
        ) from e
    return xlrd


def draft(
    xls_path: Path,
    *,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
) -> DrafterResult:
    detector = touches.script_identifier("draft.xls")
    xlrd = _xlrd()
    fields: dict[str, Any] = {}
    sections: list[Section] = []
    issues: list[dict[str, Any]] = []

    book = xlrd.open_workbook(str(xls_path), formatting_info=False)
    try:
        visible_sheets = [sh for sh in book.sheets() if sh.visibility == 0]
        fields["sheet_names"] = [sh.name for sh in visible_sheets]
        fields["sheet_count"] = len(visible_sheets)
        if v := (book.user_name or "").strip():
            fields["workbook_modified_by"] = v
        if named := _read_defined_names(book):
            fields["named_ranges"] = named

        for sheet in visible_sheets:
            seg, seg_issues = _worksheet_segment(sheet, detector)
            sections.append(
                Section(
                    address=f"sheet={quote_value(sheet.name)}",
                    entry=sheet.name,
                    segments=[seg],
                )
            )
            issues.extend(seg_issues)
    finally:
        book.release_resources()

    return {
        "fields": fields,
        "segments": sections,
        "embeds": [],
        "title": None,
        "issues": issues,
    }


register(_XLS_SCHEMA_ID)(draft)


# ---------- per-sheet rendering ---------- #


def _worksheet_segment(sheet, detector: str) -> tuple[Segment, list[dict[str, Any]]]:
    address = f"sheet={quote_value(sheet.name)}"
    body, truncated = _render_worksheet(sheet, _ROW_CAP)

    if not body.strip():
        empty = Segment(atom="text", address=address, perceptual=None, body="")
        return empty, [
            loss_issue(
                address=address,
                severity="info",
                reason=f"worksheet {sheet.name!r} is empty — no cells with values",
                detector=detector,
            )
        ]

    issues: list[dict[str, Any]] = []
    if truncated:
        reason = (
            f"sheet {sheet.name!r} truncated to the first {_ROW_CAP} rows; "
            f"further rows omitted"
        )
        issues.append(
            loss_issue(
                address=address,
                severity="warning",
                reason=reason,
                detector=detector,
                row_cap=_ROW_CAP,
            )
        )
    seg = Segment(
        atom="text",
        address=address,
        perceptual=text_fp.fingerprint_text(body),
        body=body,
    )
    return seg, issues


def _render_worksheet(sheet, row_cap: int) -> tuple[str, bool]:
    nrows, ncols = sheet.nrows, sheet.ncols
    if nrows == 0 or ncols == 0:
        return ("", False)

    rows: list[list[str]] = []
    truncated = False
    width = 0
    for r in range(nrows):
        if len(rows) >= row_cap:
            truncated = True
            break
        formatted = [_fmt_cell(_cell_value(sheet, r, c)) for c in range(ncols)]
        if not rows and not any(cell for cell in formatted):
            continue
        rows.append(formatted)
        width = max(width, len(formatted))
    while rows and not any(cell for cell in rows[-1]):
        rows.pop()
    if not rows:
        return ("", truncated)
    for row in rows:
        if len(row) < width:
            row.extend("" for _ in range(width - len(row)))
    header = rows[0]
    if all(not cell for cell in header):
        header = [_col_label(i) for i in range(width)]
    else:
        header = [cell or _col_label(i) for i, cell in enumerate(header)]
    return (_emit_markdown_table(header, rows[1:]), truncated)


def _cell_value(sheet, row: int, col: int) -> Any:
    """Python-typed cell value; xlrd date floats → datetime/date per the workbook's
    datemode. Empty/blank → None."""
    xlrd = _xlrd()
    cell = sheet.cell(row, col)
    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
        return None
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return bool(cell.value)
    if cell.ctype == xlrd.XL_CELL_DATE:
        from datetime import date, datetime

        tup = xlrd.xldate_as_tuple(cell.value, sheet.book.datemode)
        return date(*tup[:3]) if tup[3:] == (0, 0, 0) else datetime(*tup)
    if cell.ctype == xlrd.XL_CELL_ERROR:
        return f"#ERROR ({xlrd.error_text_from_code.get(cell.value, cell.value)})"
    return cell.value


def _read_defined_names(book) -> list[str]:
    """User-defined named ranges, excluding Excel internals, in declaration order."""
    out: list[str] = []
    for entry in book.name_obj_list:
        name = entry.name or ""
        if name and not name.startswith(_INTERNAL_NAME_PREFIXES):
            out.append(name)
    return out
