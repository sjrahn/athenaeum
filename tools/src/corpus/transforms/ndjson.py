"""NDJSON line selectors — one record of a newline-delimited JSON file, verbatim (spec §6.2
`line=`, *(v51)* `uuid=`).

    line=N        the file's N-th line (1-indexed, every physical line counted)    -> json
    uuid=<value>  the line whose top-level `uuid` field equals <value>             -> json

Either way the result is that line's exact text — never re-serialized, so a quote checks
against the bytes the transcript holds. `line=` is positional and survives append-only
growth (a re-capture extends the file; earlier lines keep their numbers, which is what
`corpus continuity` proves). `uuid=` names the record by its own key, so an anchor reads as
what it cites and a caller who knows the record's id (a prompt's uuid, as a capture's
context names it) needs no line count. A line that is not a JSON object, or has no `uuid`,
is simply not a match; a key that names no line, or more than one, is an error — an anchor
must resolve to exactly one record.

Streaming: lines are read one at a time and the scan stops at the match.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import RenderContext, register

#: Versioned op id (spec §6.4): folded into the cache key and sidecar `engine:` — bump on
#: any change to line counting, matching, or what the selected text includes.
ENGINE_VERSION = "ndjson-line@1"


def _lines(path: Path):
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        for n, raw in enumerate(fh, start=1):
            yield n, raw.rstrip("\r\n")


@register("ndjson", "line", "json")
def select_line(path: Path, value: str | None, ctx: RenderContext) -> str:
    """`?line=<N>` — the N-th physical line, verbatim."""
    try:
        want = int(str(value or "").strip())
    except ValueError as exc:
        raise ValueError(f"line={value!r}: not an integer line number") from exc
    if want < 1:
        raise ValueError(f"line={want}: lines are 1-indexed")
    for n, text in _lines(Path(path)):
        if n == want:
            return text
    raise ValueError(f"line={want}: the file has fewer lines")


@register("ndjson", "uuid", "json")
def select_uuid(path: Path, value: str | None, ctx: RenderContext) -> str:
    """`?uuid=<value>` — the one line whose top-level `uuid` equals `value`, verbatim."""
    want = str(value or "").strip()
    if not want:
        raise ValueError("uuid= requires a value")
    found: str | None = None
    needle = f'"{want}"'
    for n, text in _lines(Path(path)):
        if needle not in text:
            continue  # cheap pre-filter: a line that never spells the value cannot match
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("uuid") == want:
            if found is not None:
                raise ValueError(f"uuid={want}: more than one line carries it (line {n})")
            found = text
    if found is None:
        raise ValueError(f"uuid={want}: no line carries it")
    return found
