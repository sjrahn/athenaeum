"""message/rfc822 transform — the materialization side of a `part=<N>` member address and
the `block=<N>` body-segment address (spec §12.11 / §6.2).

- `part=<N>` (message → bytes) — the 1-indexed Nth addressable MIME part's CTE-decoded
  payload bytes (`corpus.emlfile` applies the pinned depth-first part enumeration + decoding,
  shared with the eml drafter so the recorded address round-trips to byte-identical content).
- `block=<N>` (message → text) — the message's derived reply-only body text (`corpus.emlfile.
  body_text`, the SAME quoted-history-trimmed extraction the drafter's `block=1` segment was
  authored from — one derivation, never a copy). An eml message carries exactly one body
  block, its own `block=1`; any other ordinal names nothing the drafter ever emitted, so it's
  a genuine `address-unresolvable` finding (`corpus lint --resolve`), not silently accepted.

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


@register("message", "block", "text")
def extract_block(path: Path, value: str | None, ctx: RenderContext) -> str:
    """`?block=<N>` (or `block=<start>-<end>`) — the message's derived body text (spec
    §6.2): resolves against `corpus.emlfile.body_text`, the SAME extraction the eml
    drafter's `block=1` segment was authored from. `path` is the `.eml`."""
    if value is None or not value.strip():
        raise ValueError("block= requires a 1-indexed block ordinal (or ordinal range)")
    start, _, end = value.partition("-")
    try:
        lo = int(start)
        hi = int(end) if end else lo
    except ValueError as exc:
        raise ValueError(f"block={value!r}: not an integer ordinal (or range)") from exc
    if lo != 1 or hi != 1:
        raise ValueError(
            f"block={value!r}: message/rfc822 has exactly one body block (block=1)"
        )
    msg = emlfile.parse(path.read_bytes())
    text = emlfile.body_text(msg)
    if not text:
        raise ValueError("block=1: message carries no derived body text")
    return text
