"""XLSX draft extraction (deterministic, no LLM).

OOXML spreadsheets are zip containers of XML parts. The drafter:

- Pulls workbook frontmatter via direct zip + ElementTree parsing (`xl/workbook.xml`,
  `docProps/core.xml`, `docProps/app.xml`) — dep-light. A second openpyxl pass
  (`data_only=False`) counts formula cells per sheet; the zip member list surfaces
  external links, pivot tables, macros, and defined names.
- Emits, per worksheet, a leading STRUCTURAL byte-mark carrying the sheet's own name
  verbatim (spec §4.3.2.3) followed by its rendered content — both addressed `sheet=<name>`
  (a normalizer carving a sub-region of the content appends `&bbox=<A1-range>`). Flat, no
  `Section` (a section binds a FORM, never a generic drafter's, §7.8/§4.3.2.1). Static-data
  sheets get a markdown table fingerprinted via simhash. A sheet longer than `_ROW_BAND`
  rows is drafted whole, as consecutive row BANDS — one segment each, addressed
  `sheet=<name>&bbox=A<first>:<last-col><last>` with real sheet row numbers — so no row
  is dropped and no one segment body grows without bound. `_ROW_CAP` is only a
  body-size ceiling (rows past it stay citable through the resolver's `bbox=`).
- Tables carry a BLANK header row and every sheet row as data: which row (if any) names
  the columns is a normalizer judgment (a 14-row preamble, a two-row header), never a
  drafter guess. Cells are unpadded; each cell's text is `transforms.xlsx.cell_text` —
  the same reading the resolver renders for `sheet=…&bbox=…`, so a quote verifies
  against either surface. Sheets whose own cells carry
  formulas or external references — plus chart-only and empty sheets — get a body-empty
  segment and an address-scoped `format-loss` issue (spec §4.3.3.1 shape; reconciliation #2
  vs the reference's CarbonAi `format_loss`). Per-sheet *classification* stays the
  normalizer's job.

`openpyxl` (the `[office]` extra) is imported lazily, so `import corpus.draft` works
without it; drafting an actual xlsx without the extra raises a clear ImportError.

Mode: `body-draft`.
"""

from __future__ import annotations

import re
import zipfile
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from corpus import recordbuild, touches
from corpus.draft import DrafterResult, register
from corpus.fingerprint import algos_for_atom, text_fingerprints
from corpus.functional_uri import quote_value
from corpus.segments import _STRUCTURAL as _STRUCTURAL_ATOM
from corpus.segments import Segment
from corpus.transforms.xlsx import cell_text, col_letters

_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
}

#: Rows per drafted band — a sheet longer than this is drafted as consecutive
#: `bbox`-addressed band segments rather than one segment.
_ROW_BAND = 1000
#: Body-size ceiling (rows) for one worksheet; past it the draft stops with a
#: `format-loss` issue. The rows stay citable through the resolver's `sheet=…&bbox=…`.
_ROW_CAP = 100_000
_XLSX_SCHEMA_ID = "application/application_vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _openpyxl():
    try:
        import openpyxl
    except ImportError as e:
        raise ImportError(
            "xlsx drafting requires the `[office]` extra. Install with: "
            "uv pip install 'athenaeum[office]'"
        ) from e
    return openpyxl


def loss_issue(
    *, address: str, severity: str, reason: str, detector: str, **fields: Any
) -> dict[str, Any]:
    """A spec §4.3.3.1 `format-loss` issue, segment-scoped via `address`."""
    return {
        "id": "format-loss",
        "severity": severity,
        "detector": detector,
        "address": address,
        "fields": {"reason": reason, **fields},
    }


def draft(
    xlsx_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,
) -> DrafterResult:
    detector = touches.script_identifier("draft.xlsx")
    fields: dict[str, Any] = {}

    with zipfile.ZipFile(xlsx_path) as zf:
        members = set(zf.namelist())
        if "xl/workbook.xml" in members:
            sheet_names = _read_sheet_names(zf)
            if sheet_names:
                fields["sheet_names"] = sheet_names
                fields["sheet_count"] = len(sheet_names)
        if "docProps/core.xml" in members:
            fields.update(_read_core_props(zf))
        if "docProps/app.xml" in members:
            fields.update(_read_app_props(zf))
        complexity = _zip_complexity(zf, members)

    sheet_meta = _sheet_formula_metadata(xlsx_path)
    complexity["sheet_meta"] = sheet_meta
    complexity["formula_count"] = sum(m["formula_count"] for m in sheet_meta.values())

    fields["formula_count"] = complexity["formula_count"]
    fields["external_links"] = complexity["external_links"]
    if complexity["named_ranges"]:
        fields["named_ranges"] = complexity["named_ranges"]
    fields["has_pivot_tables"] = complexity["has_pivot_tables"]
    fields["has_macros"] = complexity["has_macros"]

    segs, issues = _draft_sheet_sections(
        xlsx_path, complexity, detector, algos_for_atom("text", fingerprint)
    )

    recordbuild.add_blocks(build, segs)
    return {
        "fields": fields,
        "embeds": [],
        "issues": issues,
    }


register(_XLSX_SCHEMA_ID)(draft)


# ---------- per-sheet segments ---------- #


def _draft_sheet_sections(
    xlsx_path: Path, complexity: dict[str, Any], detector: str, text_algos: list[str]
) -> tuple[list[Segment], list[dict[str, Any]]]:
    """A flat structural-mark-then-content pair per worksheet (+ chart-sheet). Returns
    (segments, issues) where issues are address-scoped format-loss entries."""
    sheet_meta: dict[str, dict[str, Any]] = complexity.get("sheet_meta", {})
    wb = _openpyxl().load_workbook(xlsx_path, read_only=True, data_only=True)
    segments: list[Segment] = []
    issues: list[dict[str, Any]] = []
    try:
        for ws in wb.worksheets:
            meta = sheet_meta.get(ws.title, {})
            seg, seg_issues = _worksheet_segment(
                ws,
                formula_count=meta.get("formula_count", 0),
                uses_external_ref=meta.get("uses_external_ref", False),
                detector=detector,
                text_algos=text_algos,
            )
            segments.extend(_sheet_segments(ws.title, seg))
            issues.extend(seg_issues)
        for cs in wb.chartsheets:
            seg, seg_issues = _chartsheet_segment(cs, detector)
            segments.extend(_sheet_segments(cs.title, seg))
            issues.extend(seg_issues)
    finally:
        wb.close()
    return segments, issues


def _sheet_segments(sheet_title: str, child: Segment | list[Segment]) -> list[Segment]:
    """A worksheet's flat segment pair (spec §4.3.2.3, §7.8/§4.3.2.1 — 3.12
    reconciliation, #153): a leading STRUCTURAL byte-mark carrying the sheet's own name
    verbatim, followed by its rendered content. No `Section` — a section binds a FORM,
    never a generic drafter's. Both share the sheet's own address (`sheet=<name>`): the
    mark says a sheet named X sits here, the segment renders what its cells hold. Shared
    by the xlsx and xls drafters (the xls drafter has no chart-sheet case). `child` may be
    a list — a banded sheet's row-band segments; the mark always carries the bare sheet
    address."""
    children = child if isinstance(child, list) else [child]
    return [
        Segment(
            atom=_STRUCTURAL_ATOM,
            address=_segment_address(sheet_title),
            level=1,
            body=sheet_title,
        ),
        *children,
    ]


def _worksheet_segment(
    ws, *, formula_count: int, uses_external_ref: bool, detector: str, text_algos: list[str]
) -> tuple[list[Segment], list[dict[str, Any]]]:
    """Render a worksheet to its content Segment(s) + any address-scoped issues."""
    address = _segment_address(ws.title)

    if formula_count > 0 or uses_external_ref:
        return [_empty_segment(address)], [
            _formula_issue(ws.title, address, formula_count, uses_external_ref, detector)
        ]

    bands, truncated = _render_worksheet_bands(ws, _ROW_CAP, _ROW_BAND)
    if not bands:
        return [_empty_segment(address)], [_empty_sheet_issue(ws.title, address, detector)]

    issues: list[dict[str, Any]] = []
    if truncated:
        reason = (
            f"sheet {ws.title!r} truncated to the first {_ROW_CAP} rows; "
            f"further rows omitted from the body"
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
    segs = [
        Segment(
            atom="text",
            address=address if bbox is None else f"{address}&bbox={bbox}",
            perceptual=text_fingerprints(body, text_algos),
            body=body,
        )
        for bbox, body in bands
    ]
    return segs, issues


def _chartsheet_segment(cs, detector: str) -> tuple[Segment, list[dict[str, Any]]]:
    address = _segment_address(cs.title)
    issue = loss_issue(
        address=address,
        severity="warning",
        reason=f"chart-only sheet {cs.title!r}; no cell content to render",
        detector=detector,
    )
    return _empty_segment(address), [issue]


def _empty_segment(address: str) -> Segment:
    """A body-empty text segment (no fingerprint) — the lossless markdown table could
    not be produced (formula / external-ref / chart-only / empty sheet)."""
    return Segment(atom="text", address=address, perceptual=None, body="")


def _formula_issue(
    title: str, address: str, formula_count: int, uses_external_ref: bool, detector: str
) -> dict[str, Any]:
    parts = []
    if formula_count > 0:
        parts.append(f"{formula_count} formula cell(s)")
    if uses_external_ref:
        parts.append("external workbook references")
    composition = " and ".join(parts) if parts else "computed cells"
    return loss_issue(
        address=address,
        severity="warning",
        reason=(
            f"worksheet {title!r} contains {composition}; cells are computed snapshots "
            f"and the formulas / references are not preserved in the draft body"
        ),
        detector=detector,
        formula_count=formula_count,
        external_references=uses_external_ref,
    )


def _empty_sheet_issue(title: str, address: str, detector: str) -> dict[str, Any]:
    return loss_issue(
        address=address,
        severity="info",
        reason=f"worksheet {title!r} is empty — no cells with values",
        detector=detector,
    )


def _segment_address(sheet_title: str) -> str:
    """`sheet=<name>` — the worksheet axis. A normalizer carving a sub-region appends
    `&bbox=<A1-range>`; query-reserved chars in the name are percent-encoded."""
    return f"sheet={quote_value(sheet_title)}"


# ---------- worksheet → markdown ---------- #


def _trim_rows(rows: list[list[str]]) -> list[list[str]]:
    """Trailing all-blank rows dropped, every row cut/padded to the last populated
    column (openpyxl's used range routinely overshoots it). `[]` when nothing is
    populated."""
    while rows and not any(cell for cell in rows[-1]):
        rows.pop()
    last_col = max((i for r in rows for i, cell in enumerate(r) if cell), default=-1)
    if last_col < 0:
        return []
    width = last_col + 1
    return [(r + [""] * width)[:width] for r in rows]


def _rows_to_markdown(rows: list[list[str]], truncated: bool) -> tuple[str, bool]:
    """Shared worksheet-rows → markdown-table tail for the xlsx + xls drafters. `rows` are
    already `_fmt_cell`'d strings, with leading all-blank rows skipped and the row cap
    applied by the caller (those steps are iteration-specific). Trims trailing blank rows
    AND trailing all-blank columns and emits the table (blank header — see
    `_emit_markdown_table`). Returns `(body, truncated)`."""
    rows = _trim_rows(rows)
    return (_emit_markdown_table(rows) if rows else "", truncated)


def _render_worksheet_bands(
    ws, row_cap: int, band: int
) -> tuple[list[tuple[str | None, str]], bool]:
    """Stream cells via `iter_rows(values_only=True)` → markdown band table(s). Returns
    `([(bbox, body), …], truncated)`: one `(None, body)` for a sheet of at most `band`
    rows (the segment keeps the bare `sheet=<name>` address), else one entry per band
    with its A1 range — real sheet row numbers, the sheet-wide last populated column."""
    rows: list[list[str]] = []
    first_row = 0
    truncated = False
    for row_number, row_values in enumerate(
        ws.iter_rows(min_row=1, min_col=1, values_only=True), start=1
    ):
        formatted = [_fmt_cell(v) for v in row_values]
        if not rows and not any(cell for cell in formatted):
            continue
        if len(rows) >= row_cap:
            truncated = True
            break
        if not rows:
            first_row = row_number
        rows.append(formatted)
    rows = _trim_rows(rows)
    if not rows:
        return [], truncated
    if len(rows) <= band:
        return [(None, _emit_markdown_table(rows))], truncated
    last_col = col_letters(len(rows[0]))
    out: list[tuple[str | None, str]] = []
    for start in range(0, len(rows), band):
        chunk = rows[start:start + band]
        r0 = first_row + start
        r1 = r0 + len(chunk) - 1
        out.append((f"A{r0}:{last_col}{r1}", _emit_markdown_table(chunk)))
    return out, truncated


def _render_worksheet(ws, row_cap: int) -> tuple[str, bool]:
    """The whole sheet (up to `row_cap` rows) as ONE markdown table — the unbanded
    reading. Returns `(body, truncated)`."""
    bands, truncated = _render_worksheet_bands(ws, row_cap, row_cap)
    return (bands[0][1] if bands else "", truncated)


def _fmt_cell(value: Any) -> str:
    """One cell as a markdown-table-safe string: `transforms.xlsx.cell_text` (the
    resolver's reading of the same cell) with `\\`/`|` escaped and line breaks as `<br>`
    — both of which quote verification reads back as the cell's own text."""
    s = cell_text(value)
    if isinstance(value, (bool, int, float, datetime, date, time)) or value is None:
        return s
    s = s.replace("\\", "\\\\").replace("|", "\\|")
    return s.replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")


def _emit_markdown_table(rows: list[list[str]]) -> str:
    """Emit a GFM table: a BLANK header row (which row names the columns, if any, is the
    normalizer's call — never guessed here), then every row as data. Unpadded — padding
    is raw-source decoration every renderer ignores, and one long cell would pad a whole
    column."""
    cols = len(rows[0]) if rows else 0

    def line(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    out = [line([""] * cols), "| " + " | ".join(["---"] * cols) + " |"]
    out.extend(line((row + [""] * cols)[:cols]) for row in rows)
    return "\n".join(out)


# ---------- complexity detection ---------- #


def _zip_complexity(zf: zipfile.ZipFile, members: set[str]) -> dict[str, Any]:
    return {
        "external_links": any(m.startswith("xl/externalLinks/") for m in members),
        "has_pivot_tables": any(m.startswith("xl/pivotTables/") for m in members),
        "has_macros": "xl/vbaProject.bin" in members,
        "named_ranges": _read_defined_names(zf) if "xl/workbook.xml" in members else [],
    }


def _read_defined_names(zf: zipfile.ZipFile) -> list[str]:
    try:
        with zf.open("xl/workbook.xml") as fh:
            tree = ET.parse(fh)
    except (ET.ParseError, KeyError):
        return []
    names_el = tree.getroot().find("main:definedNames", _NS)
    if names_el is None:
        return []
    return [dn.get("name") for dn in names_el.findall("main:definedName", _NS) if dn.get("name")]


_EXTERNAL_REF_RE = re.compile(r"\[\d+\]")


def _sheet_formula_metadata(xlsx_path: Path) -> dict[str, dict[str, Any]]:
    """Per-sheet formula count + whether any formula references an external workbook
    (a second openpyxl pass with `data_only=False`)."""
    out: dict[str, dict[str, Any]] = {}
    wb = _openpyxl().load_workbook(xlsx_path, read_only=True, data_only=False)
    try:
        for ws in wb.worksheets:
            count = 0
            uses_external = False
            for row in ws.iter_rows():
                for cell in row:
                    if cell.data_type != "f":
                        continue
                    count += 1
                    if cell.value and _EXTERNAL_REF_RE.search(str(cell.value)):
                        uses_external = True
            out[ws.title] = {"formula_count": count, "uses_external_ref": uses_external}
    finally:
        wb.close()
    return out


# ---------- frontmatter extraction ---------- #


def _read_sheet_names(zf: zipfile.ZipFile) -> list[str]:
    try:
        with zf.open("xl/workbook.xml") as fh:
            tree = ET.parse(fh)
    except (ET.ParseError, KeyError):
        return []
    sheets_el = tree.getroot().find("main:sheets", _NS)
    if sheets_el is None:
        return []
    return [sh.get("name") for sh in sheets_el.findall("main:sheet", _NS) if sh.get("name")]


def _read_core_props(zf: zipfile.ZipFile) -> dict[str, Any]:
    try:
        with zf.open("docProps/core.xml") as fh:
            root = ET.parse(fh).getroot()
    except (ET.ParseError, KeyError):
        return {}
    out: dict[str, Any] = {}
    for qname, key in (
        ("dc:creator", "creator"),
        ("cp:lastModifiedBy", "modified_by"),
        ("dcterms:created", "created_at"),
        ("dcterms:modified", "modified_at"),
        ("dc:title", "title"),
    ):
        if v := _text(root, qname):
            out[key] = v
    return out


def _read_app_props(zf: zipfile.ZipFile) -> dict[str, Any]:
    try:
        with zf.open("docProps/app.xml") as fh:
            root = ET.parse(fh).getroot()
    except (ET.ParseError, KeyError):
        return {}
    out: dict[str, Any] = {}
    for el in root.iter():
        local = re.sub(r"^\{[^}]+\}", "", el.tag)
        if local == "Application" and el.text:
            out["application"] = el.text.strip()
        elif local == "Company" and el.text:
            out["company"] = el.text.strip()
    return out


def _text(root: ET.Element, qname: str) -> str:
    el = root.find(qname, _NS)
    return el.text.strip() if el is not None and el.text is not None else ""
