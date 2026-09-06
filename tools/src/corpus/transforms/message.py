"""message/rfc822 transform — the materialization side of a `part=<N>` member address and
the `block=<N>` body-segment address (spec §12.11 / §6.2).

- `part=<N>` (message → bytes) — the 1-indexed Nth addressable MIME part's CTE-decoded
  payload bytes (`corpus.emlfile` applies the pinned depth-first part enumeration + decoding,
  shared with the eml drafter so the recorded address round-trips to byte-identical content).
- `header=<name>` (message → text) *(v43)* — one header, RFC 2047-decoded to a single line
  (repeats newline-joined in file order); pinned `eml-header@1`. The envelope's own facts
  as a citable surface — `msg=<N>&header=subject` — without promoting the message.
- `block=<N>` (message → text) — the message's derived reply-only body text (`corpus.emlfile.
  body_text`, the SAME quoted-history-trimmed extraction the drafter's `block=1` segment was
  authored from — one derivation, never a copy). An eml message carries exactly one body
  block, its own `block=1`; any other ordinal names nothing the drafter ever emitted, so it's
  a genuine `address-unresolvable` finding (`corpus lint --resolve`), not silently accepted.

The eml sibling of `transforms/mbox.py`: a part is served as raw `bytes` (cached verbatim),
and its DECLARED facts — the embed's media type (`emlfile.part_facts`), filename, charset —
ride the render context (`member_mime` / `member_name` / `member_charset`) into the
resolver's member re-chaining (§6.2): a part carries no filename to sniff a mime from (its
address is an ordinal), so without the declaration a `text/plain` body would sniff as
`unknown` and print as an opaque cache path rather than decode to text as a terminal member
address must; the same declaration lets a `text/html` part re-enter the HTML pipeline
(`part=<N>&el=<M>`, `part=<N>&text`). The resolver's byte sniff still wins wherever it
positively identifies the bytes — the declaration is the fallback, never an override of a
magic signature. The handler also leaves the message's own path in the context as
`cid_source`: a `cid:` carrier in the part's HTML is a reference to a sibling part of THIS
message (§6.2 intra-container references), materialized through it by the html transforms.
"""

from __future__ import annotations

import re
from pathlib import Path

from .. import emlfile
from . import RenderContext, register

#: Versioned op id (spec §6.4 / `ledger.md` §13.2's op-version pin), folded into the cache key
#: and sidecar `engine:` field exactly like `transforms.mbox.ENGINE_VERSION` — a later change to
#: part enumeration, CTE decoding, or the terminal textual decode is a NEW id, never a silent
#: reinterpretation of an already-resolved (and potentially already-cited) result.
ENGINE_VERSION = "eml-part@1"

#: The `header=<name>` op's own pin (v43, §6.2) — RFC 2047 decode, single-line fold, and the
#: file-order newline join of a repeated header are its semantics; a change is a NEW id.
HEADER_ENGINE_VERSION = "eml-header@1"

_WS = re.compile(r"\s+")


@register("message", "part", "bytes")
def extract_part(path: Path, value: str | None, ctx: RenderContext) -> bytes:
    """`?part=<N>` — the Nth addressable part's decoded bytes. `path` is the `.eml`."""
    if value is None or not value.strip():
        raise ValueError("part= requires a 1-indexed part ordinal")
    try:
        ordinal = int(value)
    except ValueError as exc:
        raise ValueError(f"part={value!r}: not an integer ordinal") from exc
    part, decoded = emlfile.part_member(path.read_bytes(), ordinal)
    media_type, _ = emlfile.part_facts(part, decoded)
    ctx["member_mime"] = media_type
    # This message is the container a `cid:` carrier in the part's HTML refers back into
    # (§6.2 intra-container references) — the html transforms read it from here.
    ctx["cid_source"] = path
    if filename := part.get_filename():
        ctx["member_name"] = filename
    if charset := part.get_content_charset():
        ctx["member_charset"] = charset
    return decoded


@register("message", "header", "text")
def extract_header(path: Path, value: str | None, ctx: RenderContext) -> str:
    """`?header=<name>` — one header of the message as text (spec §6.2, v43): RFC 2047-
    decoded, folded onto a single line (runs of whitespace collapse to one space); a header
    that repeats (`Received`, `References` split across lines is ONE header) yields every
    instance in file order, newline-separated. Name is case-insensitive. A header the
    message does not carry is an error, not an empty string — the address names nothing.
    The `prop=` shape on the mail axis: span-precise citation of a message's own envelope
    facts (subject, from, date, message-id) without promoting the message."""
    name = (value or "").strip()
    if not name:
        raise ValueError("header= requires a header name (subject, from, date, …)")
    msg = emlfile.parse(path.read_bytes())
    values = msg.get_all(name)
    if not values:
        raise ValueError(f"header={name!r}: message carries no such header")
    return "\n".join(_WS.sub(" ", str(v)).strip() for v in values) + "\n"


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
