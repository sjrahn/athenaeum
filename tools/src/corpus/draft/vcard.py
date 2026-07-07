"""text/vcard draft extraction (deterministic, no LLM).

A delivered vCard address-book export (RFC 6350 / RFC 2426): one `.vcf` file holding N
contact cards (`BEGIN:VCARD … END:VCARD`). One delivered file stays ONE record; each card
is an `el=`-addressable SEGMENT of it, never its own record (a downstream ledger cites an
individual contact by `corpus://<hash>?el=<N>`). Three mechanical moves:

1. **UNFOLD** RFC 6350 continuation lines (a continuation starts with a space or tab; the
   drafter also tolerates the vCard 2.1 `QUOTED-PRINTABLE` `=`-soft-break continuation), then
   split the stream into cards.
2. **One `<!--segment text-->` per card** at `el=<ordinal>` (1-indexed block order), body = a
   faithful labeled rendering of every property (`- **[group.]NAME** (params): value`), the
   group prefix / parameters / value preserved VERBATIM (a reader reconstructs the card), and
   the card's display name on the segment `entry:` so `corpus toc` reads as a contact directory.
3. **Embedded-bytes PHOTO → embed + marker.** A `PHOTO` carrying its bytes inline
   (`ENCODING=b`/`BASE64`, or a `data:` URI) is lifted to a content-addressed
   `<!--embed image/*-->` (dedup'd by transport) with a body-empty `<!--segment image-->`
   positioning marker at the card's `el=` — the HTML inline-data-URI precedent. The megabytes
   never sit in the body and the bytes are never dropped. A PHOTO whose value is an external
   URL (Google Contacts exports every photo this way) is NOT embedded — it renders as a field.

Parse-tolerantly (house doctrine): a card that will not parse is logged as an info issue and
skipped, never failing the whole file. What a contact MEANS is ledger knowledge, never a record
assertion (ATH-CORPUS 2.0) — the body is faithful form only.
"""

from __future__ import annotations

import base64
import binascii
import quopri
import re
from pathlib import Path
from typing import Any

import blake3

from corpus import mime, recordbuild, records, touches
from corpus.draft import DrafterResult, register
from corpus.fingerprint import algos_for_atom, text_fingerprints
from corpus.segments import Segment

_SCHEMA_ID = "text/text_vcard"
_DETECTOR = touches.script_identifier("draft." + _SCHEMA_ID)

# TYPE= parameter value → image MIME, for an embedded PHOTO that declares its format.
_PHOTO_TYPE_MIME = {
    "JPEG": "image/jpeg",
    "JPG": "image/jpeg",
    "PNG": "image/png",
    "GIF": "image/gif",
    "WEBP": "image/webp",
    "TIFF": "image/tiff",
    "TIF": "image/tiff",
    "BMP": "image/bmp",
}


@register(_SCHEMA_ID)
def draft(
    binary_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,
) -> DrafterResult:
    raw = binary_path.read_bytes()
    cards, skipped = parse_cards(raw)

    text_algos = algos_for_atom("text", fingerprint)
    blocks: list[Segment] = []
    # Embeds deduped by transport across the whole file (the same face reused across cards
    # collapses to one embed with an address list — the HTML embed model).
    embeds_by_transport: dict[str, dict[str, Any]] = {}
    embed_order: list[str] = []

    versions: list[str] = []
    prodids: list[str] = []

    for ordinal, card in enumerate(cards, start=1):
        _collect(versions, card.value("VERSION"))
        _collect(prodids, card.value("PRODID"))
        el = f"el={ordinal}"

        body = _render_card_body(card)
        blocks.append(
            Segment(
                atom="text",
                address=el,
                entry=card.display_name(ordinal),
                perceptual=text_fingerprints(body, text_algos) if body else None,
                body=body,
            )
        )

        # Lift embedded-bytes photos → embed + body-empty marker at the card's el=.
        photos = [p for p in card.properties if _is_embedded_photo(p)]
        for k, prop in enumerate(photos, start=1):
            decoded = _photo_bytes(prop)
            if not decoded:
                continue
            addr = el if len(photos) == 1 else f"{el}&photo={k}"
            media_type = _photo_media_type(prop, decoded)
            transport = records.format_hash("blake3", blake3.blake3(decoded).hexdigest())
            existing = embeds_by_transport.get(transport)
            if existing is None:
                fields: dict[str, Any] = {}
                if params := _photo_param_text(prop):
                    fields["alt"] = params
                embeds_by_transport[transport] = {
                    "media_type": media_type,
                    "address": addr,
                    "transport": transport,
                    "fields": fields,
                }
                embed_order.append(transport)
            else:
                existing["address"] = _append_address(existing["address"], addr)
            blocks.append(Segment(atom="image", address=addr, body=""))

    recordbuild.add_blocks(build, blocks)

    fields: dict[str, Any] = {"card_count": len(cards)}
    if versions:
        fields["vcard_version"] = versions[0] if len(versions) == 1 else versions
    # PRODID is per-card (each contact records the exporter that last touched it), so a
    # long-lived address book carries many; only surface it as a file fact when uniform.
    if len(prodids) == 1:
        fields["product_id"] = prodids[0]

    issues: list[dict[str, Any]] = []
    if not cards:
        issues.append(
            _issue("no BEGIN:VCARD cards parsed from the file.", subtype="empty-body")
        )
    if skipped:
        issues.append(
            _issue(
                f"{skipped} malformed card(s) skipped (no END, or unparseable) — "
                f"parse-tolerant per house doctrine.",
                severity="warning",
            )
        )

    embeds = [embeds_by_transport[t] for t in embed_order]
    return {"fields": fields, "embeds": embeds, "issues": issues}


# ====================================================================== #
# Parse — unfold, split into cards, parse properties
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

    def param(self, key: str) -> str | None:
        """First param value for `key` (case-insensitive), or None."""
        for k, v in self.params:
            if k is not None and k.upper() == key.upper():
                return v
        return None

    def type_values(self) -> list[str]:
        """The declared TYPE values — `TYPE=CELL`, bare `CELL` (2.1), all upper-cased."""
        out: list[str] = []
        for k, v in self.params:
            if k is None:
                out.append(v.upper())
            elif k.upper() == "TYPE":
                out.extend(t.strip().upper() for t in v.split(",") if t.strip())
        return out


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
        """The TOC label: FN, else a formed N, else ORG / NICKNAME / EMAIL / TEL, else the
        ordinal. Every card gets a non-empty entry (many Google contacts carry no FN)."""
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
    """Parse the file into `(cards, skipped_count)`. A `BEGIN:VCARD` with no matching
    `END:VCARD`, or a run with no parseable properties, is skipped (tolerant)."""
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
        # BEGIN/END/VERSION structural lines that slipped in are kept as properties too so the
        # rendering is lossless — except the card's own BEGIN/END, already stripped by the split.
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


# ====================================================================== #
# Render — faithful labeled body
# ====================================================================== #


def _render_card_body(card: Card) -> str:
    """One markdown list item per property: `- **[group.]NAME** (params): value`. Embedded-bytes
    PHOTOs are OMITTED (represented by their embed + image marker); everything else — including a
    URL-valued PHOTO — renders verbatim so the card is losslessly reconstructable."""
    lines: list[str] = []
    for prop in card.properties:
        if _is_embedded_photo(prop):
            continue
        label = f"{prop.group}.{prop.name}" if prop.group else prop.name
        value, params = _rendered_value_and_params(prop)
        lines.append(f"- **{label}**{_param_suffix(params)}: {value}")
    return "\n".join(lines)


def _rendered_value_and_params(
    prop: Property,
) -> tuple[str, list[tuple[str | None, str]]]:
    """The property's faithful CONTENT value + the parameters worth surfacing. A
    QUOTED-PRINTABLE value is decoded to its true text (honouring `CHARSET`), and the
    now-consumed `ENCODING`/`CHARSET` params are dropped — the encoding was transport, not
    content. Every other value renders verbatim (vCard value escaping `\\n`/`\\,`/`\\;` and the
    semicolon-structured `N`/`ADR` components preserved, so the card is reconstructable)."""
    enc = (prop.param("ENCODING") or "").strip().lower()
    if enc == "quoted-printable":
        charset = prop.param("CHARSET") or "utf-8"
        try:
            value = quopri.decodestring(prop.value.encode("ascii", "ignore")).decode(
                charset, errors="replace"
            )
        except LookupError:
            value = quopri.decodestring(prop.value.encode("ascii", "ignore")).decode(
                "utf-8", errors="replace"
            )
        params = [
            (k, v)
            for k, v in prop.params
            if k is None or k.upper() not in ("ENCODING", "CHARSET")
        ]
        return value, params
    return prop.value, prop.params


def _param_suffix(params: list[tuple[str | None, str]]) -> str:
    """` (key=value; bareval; …)` reconstructing the property parameters, or `` when none."""
    if not params:
        return ""
    parts = [v if k is None else f"{k}={v}" for k, v in params]
    return " (" + "; ".join(parts) + ")"


def _photo_param_text(prop: Property) -> str:
    """The PHOTO parameters, verbatim-ish, for the embed `alt` (provenance about the property)."""
    return "; ".join(v if k is None else f"{k}={v}" for k, v in prop.params)


# ====================================================================== #
# Embedded-photo detection + decode
# ====================================================================== #


def _is_embedded_photo(prop: Property) -> bool:
    """A PHOTO (or LOGO) that carries its BYTES inline — `ENCODING=b`/`BASE64`, or a `data:`
    URI value. A `PHOTO:https://…` (external URL, no encoding param) is NOT embedded."""
    if prop.name not in ("PHOTO", "LOGO"):
        return False
    enc = (prop.param("ENCODING") or "").strip().lower()
    if enc in ("b", "base64"):
        return True
    return prop.value.strip().lower().startswith("data:")


def _photo_bytes(prop: Property) -> bytes | None:
    """Decode an embedded PHOTO's bytes (base64 payload or `data:` URI), or None on garbage."""
    value = prop.value.strip()
    if value.lower().startswith("data:"):
        _, _, payload = value.partition(",")
        value = payload
    enc = (prop.param("ENCODING") or "").strip().lower()
    try:
        if enc == "quoted-printable":
            return quopri.decodestring(value.encode("ascii", "ignore"))
        return base64.b64decode(_strip_ws(value), validate=False)
    except (binascii.Error, ValueError):
        return None


def _photo_media_type(prop: Property, decoded: bytes) -> str:
    """The embedded photo's MIME: the `data:` prefix, else the `TYPE=` param, else a sniff."""
    value = prop.value.strip()
    if value.lower().startswith("data:"):
        meta = value[5:].split(",", 1)[0]  # `image/png;base64`
        mt = meta.split(";", 1)[0].strip()
        if mt:
            return mt
    for t in prop.type_values():
        if t in _PHOTO_TYPE_MIME:
            return _PHOTO_TYPE_MIME[t]
    sniffed = mime.sniff_head(decoded[:512])
    return sniffed if sniffed.startswith("image/") else "image/jpeg"


# ====================================================================== #
# small helpers
# ====================================================================== #


def _append_address(existing: str | list[str], addr: str) -> str | list[str]:
    if isinstance(existing, list):
        return existing if addr in existing else [*existing, addr]
    return existing if existing == addr else [existing, addr]


def _collect(acc: list[str], value: str | None) -> None:
    v = _clean(value)
    if v and v not in acc:
        acc.append(v)


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


def _strip_ws(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _issue(
    description: str, *, severity: str = "info", subtype: str | None = None
) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "id": "partial-content",
        "severity": severity,
        "resolution": "open",
        "detector": _DETECTOR,
        "fields": {"description": description},
    }
    if subtype:
        issue["subtype"] = subtype
    return issue
