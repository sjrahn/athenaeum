"""vCard transforms — the materialization side of a `card=<N>` member address (spec §12.11)
and a `prop=<N>` property-value op (spec §6.2, §12.11).

- `card=<N>` (vcard → bytes) — the 1-indexed Nth card's exact member bytes. `<N>` is the
  ordinal the `vcard-manifest` drafter recorded on the card's embed; `corpus.vcardfile` applies
  the pinned `BEGIN:VCARD`/`END:VCARD` byte-span semantics so the recorded address round-trips
  to the byte-identical `text/vcard` a `promote` would mint.

The vCard sibling of `transforms/mbox.py` / `transforms/zip.py`: a card is served as raw `bytes`
(cached verbatim, `application/octet-stream`); the member's real `text/vcard` type lives on its
embed block.

- `prop=<N>` (vcard → text) — the record's OWN card's 1-indexed Nth property, decoded exactly
  as the `contact-card` shaper decodes it (`shape/contact_card.py`'s `prop=N` segment
  addressing), so a citation's `?prop=N` anchor resolves to the SAME datum a human checking
  citability sees rendered in the formed record. Both consumers share `vcardfile.is_binary` /
  `vcardfile.decoded_value` — one point of truth, never two hand-synced copies (the `units.py`
  `turn=` precedent). A binary-encoded property (PHOTO/LOGO/SOUND/KEY, ENCODING=B/BASE64) has
  no decoded text — same as the shaper's segment, which renders it header-only — so `prop=`
  raises a clear error rather than guessing at a rendering.
"""

from __future__ import annotations

from pathlib import Path

from .. import vcardfile
from . import RenderContext, register

#: Versioned op id (spec §6.4 / `ledger.md` §13.2's op-version pin), folded into the cache
#: key and sidecar `engine:` field exactly like `transforms.csv.ENGINE_VERSION` — a later
#: change to property indexing or decode semantics is a NEW id, never a silent
#: reinterpretation of an already-resolved (and potentially already-cited) result.
ENGINE_VERSION = "vcard-prop@1"


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


@register("vcard", "prop", "text")
def select_prop(path: Path, value: str | None, ctx: RenderContext) -> str:
    """`?prop=<N>` — the record's own card's 1-indexed Nth property, decoded. `path` is the
    record's `.vcf` bytes; the record represents exactly ONE card (`cards[0]`, mirroring
    `shape/contact_card.py`'s `_load_card`) — a multi-card `.vcf` addresses its OTHER cards via
    `card=<M>` first (a distinct record once promoted), never `prop=` directly on the
    container."""
    if value is None or not value.strip():
        raise ValueError("prop= requires a 1-indexed property ordinal")
    try:
        ordinal = int(value)
    except ValueError as exc:
        raise ValueError(f"prop={value!r}: not an integer ordinal") from exc
    if ordinal < 1:
        raise ValueError(f"prop={ordinal}: ordinals are 1-indexed")

    cards, _skipped = vcardfile.parse_cards(path.read_bytes())
    if not cards:
        raise ValueError(
            "prop=: no parseable BEGIN:VCARD…END:VCARD span in this record's bytes"
        )
    props = cards[0].properties
    if not 1 <= ordinal <= len(props):
        noun = "property" if len(props) == 1 else "properties"
        raise ValueError(f"prop={ordinal}: out of range ({len(props)} {noun})")
    prop = props[ordinal - 1]
    if vcardfile.is_binary(prop):
        raise ValueError(
            f"prop={ordinal}: property {prop.name} is binary-encoded (ENCODING=B/BASE64) — "
            "no decoded text (the bytes are the record's own artifact, resolvable as a "
            "self-slice; the formed record's segment renders it header-only likewise)"
        )
    return vcardfile.decoded_value(prop)
