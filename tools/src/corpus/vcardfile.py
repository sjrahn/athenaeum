"""Shared vCard helpers — the byte-exact card-extraction axis between the `vcard-manifest`
drafter (`draft/vcard_manifest.py`), the `card=<N>` member transform (`transforms/vcard.py`),
and containment streaming (`containment.open_member_stream`). The vCard sibling of
`mboxfile` / `ziparchive`.

A delivered `.vcf` address-book export (RFC 6350 / RFC 2426) is a flat concatenation of contact
cards, each delimited by a `BEGIN:VCARD` … `END:VCARD` pair. This module owns the **pinned
extraction semantics** (spec §12.11, §12.18 step 4), so a card's member bytes are deterministic
and promotable (§8.1):

- A card's member bytes are the **verbatim byte span** from the start of its `BEGIN:VCARD` line
  through the end of its `END:VCARD` line, INCLUDING that line's terminator — everything between
  preserved exactly (folded RFC 6350 continuation lines, CRLF or bare LF, QUOTED-PRINTABLE
  payloads, an embedded-bytes `PHOTO`). RFC 6350 line-unfolding is a **read-time** concern of a
  consumer, NEVER applied to the member bytes: identity is bytes (§2), so a promoted card
  round-trips as a standalone `text/vcard` artifact.
- Ordinals are 1-indexed over the **successfully-delimited** cards in file order. A malformed
  card — a `BEGIN:VCARD` with no matching `END:VCARD` before the next `BEGIN`/EOF — is skipped
  (parse-tolerant, house doctrine) and leaves no ordinal, so the surviving cards number
  contiguously and a recorded `card=<N>` always round-trips.

Line delimiting is done on the raw bytes (splitting on `\\n`, so a CRLF's `\\r` rides inside the
line span and the pins stay byte-exact regardless of terminator). Display-name / VERSION /
PRODID parsing runs on a card's *own* member bytes via the text parser below — metadata about
the span, never touching the span's identity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import blake3

# A card delimiter line, tolerant of trailing whitespace / CRLF and case (RFC 6350 is
# case-insensitive on the BEGIN/END keywords and the VCARD value).
_BEGIN = b"BEGIN:VCARD"
_END = b"END:VCARD"


def _is_begin(line: bytes) -> bool:
    return line.strip().upper() == _BEGIN


def _is_end(line: bytes) -> bool:
    return line.strip().upper() == _END


def _iter_line_spans(raw: bytes) -> list[tuple[int, int]]:
    """The `(start, end)` byte offsets of every physical line, each span INCLUDING its
    terminator. Splits on `\\n`, so a CRLF line keeps its `\\r` inside the span and a bare-LF
    line its `\\n` — the pins are byte-exact for either terminator. A final line with no
    terminator runs to EOF."""
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(raw)
    while i < n:
        j = raw.find(b"\n", i)
        if j == -1:
            spans.append((i, n))
            break
        spans.append((i, j + 1))
        i = j + 1
    return spans


# ---------- byte-exact card scan (drafter / transform / containment) ---------- #


@dataclass
class CardFacts:
    """The per-card facts the manifest drafter records: the exact member's byte span +
    blake3 identity + length, plus the parsed display name (embed `description:`) and the
    card's VERSION / PRODID (file-fact candidates)."""

    ordinal: int
    start: int  # byte offset of the BEGIN:VCARD line start
    end: int  # byte offset just past the END:VCARD line terminator
    blake3: str
    bytes: int
    display_name: str
    version: str | None
    prodid: str | None


@dataclass
class VcardScan:
    """One pass over a `.vcf`: the per-ordinal facts for every successfully-delimited card,
    and the count of malformed cards skipped (parse-tolerant)."""

    count: int
    skipped: int
    facts: list[CardFacts]


def scan(raw: bytes) -> VcardScan:
    """Delimit every card in `raw` and compute its byte-exact member facts. A `BEGIN:VCARD`
    with no matching `END:VCARD` before the next `BEGIN`/EOF is skipped and counted (never
    fatal). Ordinals number the surviving cards 1..K in file order."""
    spans = _iter_line_spans(raw)
    facts: list[CardFacts] = []
    skipped = 0
    ordinal = 0
    i = 0
    n = len(spans)
    while i < n:
        s0, e0 = spans[i]
        if not _is_begin(raw[s0:e0]):
            i += 1
            continue
        # Scan forward for END, stopping early on a fresh BEGIN (a missing-END malformed card).
        j = i + 1
        while j < n:
            sj, ej = spans[j]
            if _is_begin(raw[sj:ej]) or _is_end(raw[sj:ej]):
                break
            j += 1
        if j >= n or not _is_end(raw[spans[j][0] : spans[j][1]]):
            skipped += 1
            i = j  # resume at the next BEGIN (or EOF)
            continue
        card_start = spans[i][0]
        card_end = spans[j][1]  # through the END line's terminator, inclusive
        member = raw[card_start:card_end]
        ordinal += 1
        display, version, prodid = _card_metadata(member, ordinal)
        facts.append(
            CardFacts(
                ordinal=ordinal,
                start=card_start,
                end=card_end,
                blake3=blake3.blake3(member).hexdigest(),
                bytes=len(member),
                display_name=display,
                version=version,
                prodid=prodid,
            )
        )
        i = j + 1
    return VcardScan(count=ordinal, skipped=skipped, facts=facts)


def resolve_member(path: Path, ordinal: int) -> bytes:
    """The 1-indexed `ordinal` card's exact member bytes (the pinned byte span). Round-trips
    to the byte-identical `text/vcard` a `promote` would mint (spec §12.11). Raises
    `ValueError` when the ordinal doesn't exist."""
    if ordinal < 1:
        raise ValueError(f"card={ordinal}: ordinals are 1-indexed")
    raw = path.read_bytes()
    for facts in scan(raw).facts:
        if facts.ordinal == ordinal:
            return raw[facts.start : facts.end]
    total = scan(raw).count
    raise ValueError(f"card={ordinal}: no such card (file holds {total} card(s))")


def _card_metadata(member: bytes, ordinal: int) -> tuple[str, str | None, str | None]:
    """`(display_name, version, prodid)` parsed from a card's own member bytes. Read-time
    metadata about the span — the bytes stay verbatim; unfolding happens only here for parsing."""
    cards, _skipped = parse_cards(member)
    if not cards:
        return f"Card {ordinal}", None, None
    card = cards[0]
    return card.display_name(ordinal), _clean(card.value("VERSION")) or None, _clean(
        card.value("PRODID")
    ) or None


# ====================================================================== #
# Text parse — unfold, split into cards, parse properties (metadata only)
# ====================================================================== #


class Property:
    """One parsed vCard property line: `[group.]NAME *(";" param) ":" value`."""

    __slots__ = ("group", "name", "params", "value")

    def __init__(
        self, group: str | None, name: str, params: list[tuple[str | None, str]], value: str
    ) -> None:
        self.group = group
        self.name = name
        self.params = params  # ordered (key|None, value); key None = a bare vCard 2.1 type
        self.value = value


class Card:
    """One parsed vCard (an ordered list of properties)."""

    __slots__ = ("properties",)

    def __init__(self, properties: list[Property]) -> None:
        self.properties = properties

    def value(self, name: str) -> str | None:
        for p in self.properties:
            if p.name.upper() == name.upper():
                return p.value
        return None

    def display_name(self, ordinal: int) -> str:
        """The embed `description:` / TOC label: FN, else a formed N, else
        ORG / NICKNAME / EMAIL / TEL, else the ordinal (the 2.x fallback chain — many Google
        contacts carry no FN)."""
        if fn := _clean(self.value("FN")):
            return fn
        if (n := self.value("N")) and (formed := _format_n(n)):
            return formed
        for name in ("ORG", "NICKNAME", "EMAIL", "TEL"):
            if v := _clean(self.value(name)):
                # ORG is `Unit;Sub;…` structured — the first component is the org name.
                return v.split(";", 1)[0].strip() if name == "ORG" else v
        return f"Card {ordinal}"


# A folded continuation begins with a single space or tab (RFC 6350 §3.2).
_QP_RE = re.compile(r"ENCODING\s*=\s*QUOTED-PRINTABLE", re.IGNORECASE)


def _decode(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    if text and text[0] == "﻿":  # strip a leading BOM
        text = text[1:]
    return text


def unfold(text: str) -> list[str]:
    """Return logical lines with RFC 6350 folding undone. A physical line that starts with a
    space or tab continues the previous line (the leading whitespace is dropped). The vCard
    2.1 QUOTED-PRINTABLE soft break — a value line that ends with `=` — also continues onto the
    next physical line (the `=` is dropped, no separator). Tolerant of CRLF and bare LF."""
    logical: list[str] = []
    for physical in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if logical and physical[:1] in (" ", "\t"):
            logical[-1] += physical[1:]
        elif logical and logical[-1].endswith("=") and _QP_RE.search(logical[-1]):
            logical[-1] = logical[-1][:-1] + physical
        else:
            logical.append(physical)
    return logical


def parse_cards(raw: bytes) -> tuple[list[Card], int]:
    """Parse the bytes into `(cards, skipped_count)`. A `BEGIN:VCARD` with no matching
    `END:VCARD`, or a run with no parseable properties, is skipped (tolerant). Used for
    metadata (display name / VERSION / PRODID) — NOT for byte identity (`scan` owns that)."""
    lines = unfold(_decode(raw))
    cards: list[Card] = []
    skipped = 0
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].strip().upper() != "BEGIN:VCARD":
            i += 1
            continue
        j = i + 1
        while j < n and lines[j].strip().upper() != "END:VCARD":
            if lines[j].strip().upper() == "BEGIN:VCARD":
                break  # nested/missing END — the inner BEGIN starts a fresh card
            j += 1
        if j >= n or lines[j].strip().upper() != "END:VCARD":
            skipped += 1  # ran off the end / hit another BEGIN with no END
            i = j
            continue
        props = _parse_properties(lines[i + 1 : j])
        if props:
            cards.append(Card(props))
        else:
            skipped += 1
        i = j + 1
    return cards, skipped


def _parse_properties(lines: list[str]) -> list[Property]:
    props: list[Property] = []
    for line in lines:
        if not line.strip():
            continue
        prop = _parse_property(line)
        if prop is not None:
            props.append(prop)
    return props


def _parse_property(line: str) -> Property | None:
    name_params, sep, value = _split_on_unquoted_colon(line)
    if not sep:
        return None  # no colon — not a property line; skip tolerantly
    tokens = _split_unquoted(name_params, ";")
    if not tokens or not tokens[0]:
        return None
    group, name = _split_group(tokens[0])
    if not name:
        return None
    params: list[tuple[str | None, str]] = []
    for tok in tokens[1:]:
        key, eq, val = tok.partition("=")
        if eq:
            params.append((key.strip(), val.strip().strip('"')))
        elif tok.strip():
            params.append((None, tok.strip()))
    return Property(group=group, name=name.strip().upper(), params=params, value=value)


def _split_on_unquoted_colon(line: str) -> tuple[str, str, str]:
    """Split at the first `:` that is not inside a double-quoted parameter value."""
    in_quote = False
    for idx, ch in enumerate(line):
        if ch == '"':
            in_quote = not in_quote
        elif ch == ":" and not in_quote:
            return line[:idx], ":", line[idx + 1 :]
    return line, "", ""


def _split_unquoted(text: str, sep: str) -> list[str]:
    """Split on `sep`, but never inside a double-quoted run."""
    out: list[str] = []
    buf: list[str] = []
    in_quote = False
    for ch in text:
        if ch == '"':
            in_quote = not in_quote
            buf.append(ch)
        elif ch == sep and not in_quote:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return out


def _split_group(token: str) -> tuple[str | None, str]:
    """`item1.TEL` → (`item1`, `TEL`); `TEL` → (None, `TEL`). Only a leading group prefix
    splits (property names carry no dot per RFC 6350)."""
    if "." in token:
        group, _, name = token.partition(".")
        return (group.strip() or None), name
    return None, token


def _format_n(n: str) -> str:
    """Form a display name from the structured `N` value
    (`Family;Given;Additional;Prefixes;Suffixes`) → `Prefixes Given Additional Family Suffixes`."""
    comps = [c.strip() for c in n.split(";")]
    comps += [""] * (5 - len(comps))
    family, given, additional, prefixes, suffixes = comps[:5]
    ordered = [prefixes, given, additional, family, suffixes]
    return " ".join(c for c in ordered if c).strip()


def _clean(value: str | None) -> str:
    return (value or "").strip()
