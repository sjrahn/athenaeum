"""mbox transform — the materialization side of a `msg=<N>` member address (spec §12.11).

- `msg=<N>` (mbox → bytes) — the 1-indexed Nth message's un-stuffed bytes. `<N>` is the
  ordinal the `mbox-manifest` drafter recorded on the message's embed; `corpus.mboxfile`
  applies the pinned separator + un-stuffing semantics so the recorded address round-trips
  to the byte-identical `message/rfc822` a `promote` would mint.

The mbox sibling of `transforms/zip.py` / `transforms/tar.py`: a message is served as raw
`bytes` (cached verbatim, `application/octet-stream`); the member's real `message/rfc822`
type lives on its embed block.
"""

from __future__ import annotations

from pathlib import Path

from .. import mboxfile
from . import RenderContext, register


@register("mbox", "msg", "bytes")
def extract_message(path: Path, value: str | None, ctx: RenderContext) -> bytes:
    """`?msg=<N>` — the 1-indexed Nth message's un-stuffed bytes. `path` is the `.mbox`."""
    if value is None or not value.strip():
        raise ValueError("msg= requires a 1-indexed message ordinal")
    try:
        ordinal = int(value)
    except ValueError as exc:
        raise ValueError(f"msg={value!r}: not an integer ordinal") from exc
    return mboxfile.resolve_member(path, ordinal)
