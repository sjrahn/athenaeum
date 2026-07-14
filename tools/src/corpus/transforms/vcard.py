"""vCard transform — the materialization side of a `card=<N>` member address (spec §12.11).

- `card=<N>` (vcard → bytes) — the 1-indexed Nth card's exact member bytes. `<N>` is the
  ordinal the `vcard-manifest` drafter recorded on the card's embed; `corpus.vcardfile` applies
  the pinned `BEGIN:VCARD`/`END:VCARD` byte-span semantics so the recorded address round-trips
  to the byte-identical `text/vcard` a `promote` would mint.

The vCard sibling of `transforms/mbox.py` / `transforms/zip.py`: a card is served as raw `bytes`
(cached verbatim, `application/octet-stream`); the member's real `text/vcard` type lives on its
embed block.
"""

from __future__ import annotations

from pathlib import Path

from .. import vcardfile
from . import RenderContext, register


@register("vcard", "card", "bytes")
def extract_card(path: Path, value: str | None, ctx: RenderContext) -> bytes:
    """`?card=<N>` — the 1-indexed Nth card's exact member bytes. `path` is the `.vcf`."""
    if value is None or not value.strip():
        raise ValueError("card= requires a 1-indexed card ordinal")
    try:
        ordinal = int(value)
    except ValueError as exc:
        raise ValueError(f"card={value!r}: not an integer ordinal") from exc
    return vcardfile.resolve_member(path, ordinal)
