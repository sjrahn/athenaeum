"""message/rfc822 transform — the materialization side of a `part=<N>` member address
(spec §12.11).

- `part=<N>` (message → bytes) — the 1-indexed Nth addressable MIME part's CTE-decoded
  payload bytes (`corpus.emlfile` applies the pinned depth-first part enumeration + decoding,
  shared with the eml drafter so the recorded address round-trips to byte-identical content).

The eml sibling of `transforms/mbox.py`: a part is served as raw `bytes` (cached verbatim,
`application/octet-stream`); the part's real media type lives on its embed block.
"""

from __future__ import annotations

from pathlib import Path

from .. import emlfile
from . import RenderContext, register


@register("message", "part", "bytes")
def extract_part(path: Path, value: str | None, ctx: RenderContext) -> bytes:
    """`?part=<N>` — the Nth addressable part's decoded bytes. `path` is the `.eml`."""
    if value is None or not value.strip():
        raise ValueError("part= requires a 1-indexed part ordinal")
    try:
        ordinal = int(value)
    except ValueError as exc:
        raise ValueError(f"part={value!r}: not an integer ordinal") from exc
    return emlfile.resolve_part(path.read_bytes(), ordinal)
