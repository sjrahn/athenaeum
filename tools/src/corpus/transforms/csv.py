"""CSV transforms — a row selector plus a column sub-op (spec §6.2 `row=`, `col=`).

Grammar (selector + sub-op — mirrors the PDF `page=` selector, `transforms/pdf.py`):

    row=N                        select DATA row N (1-indexed, header excluded)  -> csvrow
    row=N&col=<name-or-index>    that row's single field value                   -> text

`row=N` yields an intermediate `csvrow` working value (`CsvRowRef`) carrying the row's
exact raw source text plus its RFC-4180-parsed fields — and the header row's field names,
when the dialect declares one — so a following `col=` can resolve a header-name match
without re-reading the file. A **terminal** `row=N` auto-renders to its raw source text in
the resolver (`resolver.resolve`'s `csvrow` -> `text` step), mirroring `pdfpage`'s
terminal-render contract: `address: row=N` resolves to the row's bytes exactly as
`page=N` resolves to the page image.

Dialect (delimiter, quote character, quoting mode, header-row presence) is NEVER
hardcoded here — the mime schema (`text_csv.yaml`'s `csv_dialect:`, read into the render
context by the resolver, spec §7.1) supplies it, so a corpus meeting a deviant "CSV"
export (semicolon-delimited, header-less) declares its own dialect and this engine
follows it. Quoting is RFC-4180-aware via the standard library `csv` module: a quoted
field's embedded delimiter, quote character, or newline never splits a row, and every
extra physical line a multi-line quoted field pulls in rides the SAME logical row's raw
text.

Streaming: rows are read one at a time from disk via a line iterator; `row=N` stops the
moment row N is produced — later rows, and the whole-file materialization a naive
`readlines()` would force, are never read.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import RenderContext, register

#: Versioned op id (spec §6.4 / `ledger.md` §13.2's op-version pin): a resolved result's
#: cache key and sidecar `engine:` field fold this in (`resolver.py`, alongside the
#: ffmpeg/transcribe version labels), so a later change to row/col extraction semantics
#: is a NEW id, never a silent reinterpretation of an already-cited result. Bump on any
#: change to header handling, quoting, or column-resolution rules.
ENGINE_VERSION = "csv-row-col@1"

_QUOTING_BY_NAME: dict[str, int] = {
    "minimal": csv.QUOTE_MINIMAL,
    "all": csv.QUOTE_ALL,
    "nonnumeric": csv.QUOTE_NONNUMERIC,
    "none": csv.QUOTE_NONE,
}


@dataclass
class CsvRowRef:
    """A selected CSV data row (mirrors `pdfpage` / `PdfPageRef`, `transforms/pdf.py`):
    its exact raw source text (RFC-4180-aware — spans every physical line an embedded
    newline pulled in), its parsed fields, and the header row's field names when the
    dialect declares one (`header_row: true`)."""

    raw: str
    fields: list[str]
    header: list[str] | None


def _dialect_config(ctx: RenderContext) -> dict[str, Any]:
    cfg = ctx.get("csv_dialect")
    return cfg if isinstance(cfg, dict) else {}


def _reader_dialect(cfg: dict[str, Any]) -> type[csv.Dialect]:
    """Build a `csv.Dialect` from the mime schema's declared `csv_dialect:` — the
    engine's ONLY source of delimiter/quoting/header knowledge."""
    quoting_name = str(cfg.get("quoting", "minimal") or "minimal").strip().lower()
    quoting = _QUOTING_BY_NAME.get(quoting_name)
    if quoting is None:
        raise ValueError(
            f"csv_dialect.quoting: unrecognized value {quoting_name!r} "
            f"(expected one of {sorted(_QUOTING_BY_NAME)})"
        )
    delimiter_ = str(cfg.get("delimiter", ",") or ",")
    quotechar_ = str(cfg.get("quotechar", '"') or '"')
    doublequote_ = bool(cfg.get("doublequote", True))
    quoting_ = quoting

    # NOTE: the class-attribute names below intentionally shadow the `_dialect` locals
    # above (`delimiter`, `quotechar`, …) — a class body binds a name assigned within it
    # to ITS OWN namespace for the whole suite, so `delimiter = delimiter` would read the
    # not-yet-bound class-local name on the right-hand side (`NameError`) rather than the
    # enclosing local. The trailing-underscore locals sidestep the shadow.
    class _Dialect(csv.Dialect):
        delimiter = delimiter_
        quotechar = quotechar_
        doublequote = doublequote_
        escapechar = None
        lineterminator = "\r\n"  # unused by the reader (it splits on \r/\n unconditionally)
        quoting = quoting_

    return _Dialect


def _iter_logical_rows(
    path: Path, dialect: type[csv.Dialect]
) -> Iterator[tuple[str, list[str]]]:
    """Yield `(raw_source_text, fields)` per logical row, streaming. The wrapping
    generator tracks exactly how many physical lines `csv.reader` consumed to produce
    each output row (2+ when a quoted field embeds a newline), so `raw_source_text` is
    never truncated at the first embedded newline. `newline=""` — the `csv` module's own
    documented contract — keeps an embedded `\\r\\n`/`\\n` inside a quoted field verbatim
    rather than translated by universal-newlines decoding."""
    consumed: list[str] = []

    def _lines() -> Iterator[str]:
        with path.open("r", newline="", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                consumed.append(line)
                yield line

    reader = csv.reader(_lines(), dialect=dialect)
    for fields in reader:
        raw = "".join(consumed)
        consumed.clear()
        yield raw, fields


@register("csv", "row", "csvrow")
def select_row(path: Path, value: str | None, ctx: RenderContext) -> CsvRowRef:
    """`?row=<N>` — the 1-indexed Nth DATA row (header excluded when the dialect
    declares one). Streams to row N and stops; later rows are never read."""
    if value is None or not value.strip():
        raise ValueError("row= requires a 1-indexed row ordinal")
    try:
        ordinal = int(value)
    except ValueError as exc:
        raise ValueError(f"row={value!r}: not an integer ordinal") from exc
    if ordinal < 1:
        raise ValueError(f"row={ordinal}: ordinals are 1-indexed")

    cfg = _dialect_config(ctx)
    dialect = _reader_dialect(cfg)
    header_row = bool(cfg.get("header_row", True))

    header: list[str] | None = None
    data_seen = 0
    for raw, fields in _iter_logical_rows(path, dialect):
        if header_row and header is None:
            header = fields
            continue
        data_seen += 1
        if data_seen == ordinal:
            return CsvRowRef(raw=raw, fields=fields, header=header)
    raise ValueError(f"row={ordinal}: out of range ({data_seen} data row(s))")


@register("csvrow", "col", "text")
def select_col(row: CsvRowRef, value: str | None, ctx: RenderContext) -> str:
    """`row=<N>&col=<name-or-index>` — that row's single field value. A header-name
    match (case-sensitive, exact) wins when the dialect declares a header row and `value`
    matches one of its fields; otherwise `value` is a 1-indexed integer column."""
    if value is None or not value.strip():
        raise ValueError("col= requires a column name or a 1-indexed index")
    name = value.strip()
    if row.header is not None and name in row.header:
        idx = row.header.index(name)
    elif name.lstrip("-").isdigit():
        idx = int(name) - 1
        if idx < 0:
            raise ValueError(f"col={name}: ordinals are 1-indexed")
    elif row.header is not None:
        raise ValueError(
            f"col={name!r}: no such header (row has {len(row.header)} column(s): "
            f"{row.header})"
        )
    else:
        raise ValueError(
            f"col={name!r}: not a 1-indexed integer column (this csv declares no "
            f"header row, so col= must be an index)"
        )
    if not 0 <= idx < len(row.fields):
        raise ValueError(f"col={name!r}: row has {len(row.fields)} field(s)")
    return row.fields[idx]
