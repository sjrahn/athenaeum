"""The `contact-card` shaper (spec §7.8, §12.5.0, §12.19 step 6): one vCard's decomposition
into quotable, single-line property facts.

Registered under the FORM id `contact-card` (not an origin id) — unlike the conversation
mapping-driven shaper, vCard is one universal interchange format (RFC 6350), so no per-origin
JSON-path mapping is needed: the shaper parses the record's OWN vCard bytes directly, the same
way `adopt_flat` wraps an already-rendered flat zone. Any origin overlay that declares
`form: {id: contact-card}` (an iCloud contacts export's promoted card, a future Google Contacts
promoted card, …) dispatches here with zero code of its own (spec §7.2's "one origin overlay,
zero code" principle applied to a non-JSON producer family).

A promoted card record is BODILESS at promotion (`corpus promote`, spec §8.1) — its bytes stay
resident in the parent `.vcf` container, resolved through the member index (§12.9) exactly like
`units.load_json_artifact` resolves a promoted conversation's JSON. `vcardfile.parse_cards`
(the shared byte-exact-scan module, §12.11) already does the RFC 6350 unfolding — this module
adds the one further transform a consumer, not the parser, owns: QUOTED-PRINTABLE hex-escape
decoding (vcardfile's docstring: "RFC 6350 line-unfolding is a READ-time concern of a
consumer" — decoding is the same kind of consumer-side concern, one level up).

**PHOTO/LOGO/SOUND/KEY exclusion** (spec §4.3.1.4, the already-preserved-bytes rule): a
`b`/`BASE64`-encoded property's value is never transcribed — the segment renders header-only
(name/group/params, no body). The bytes are not lost: they are the record's own artifact,
resolvable on demand as a self-slice. Real iCloud/Google exports observed so far carry zero
embedded-bytes PHOTOs (external `X-IMAGEHASH` refs instead, per the 2026-07-07 vcard arc), so
this path is tested-but-currently-dormant against real cargo, exactly as the parent manifest
schema's own PHOTO handling was.
"""

from __future__ import annotations

import quopri
import re
from pathlib import Path
from typing import Any

import frontmatter

from corpus import containment, mime, recordbuild, records, vcardfile
from corpus.shape import register_shaper

# vCard 2.1/3.0 spellings for the two control-parameter values this module acts on.
_QP_VALUES = {"QUOTED-PRINTABLE", "Q"}
_BINARY_VALUES = {"B", "BASE64"}

# RFC 6350 §3.4 TEXT-value escaping: `\\`, `\,`, `\;` are the escaped literal, `\n`/`\N`
# an embedded newline. Applies uniformly to every property's value regardless of ENCODING
# (a distinct, always-on layer from QUOTED-PRINTABLE's octet-level transfer encoding) — a
# bare, unescaped `;`/`,` is a real structural separator (N's/ADR's components, a
# multi-valued NICKNAME/CATEGORIES list) and is left alone; only a BACKSLASH-prefixed one
# is a literal character. An unrecognized escape (a stray trailing backslash, a vendor
# quirk) is left verbatim rather than guessed at (parse-tolerant).
_ESCAPE_RE = re.compile(r"\\(.)", re.DOTALL)
_ESCAPE_MAP = {"n": "\n", "N": "\n", ",": ",", ";": ";", "\\": "\\"}


def _unescape_text(value: str) -> str:
    return _ESCAPE_RE.sub(lambda m: _ESCAPE_MAP.get(m.group(1), m.group(0)), value)


def _param_value(prop: vcardfile.Property, key: str) -> str | None:
    """The value of a KEYED parameter named `key` (case-insensitive), or None."""
    for k, v in prop.params:
        if k and k.upper() == key:
            return v
    return None


def _has_bare_token(prop: vcardfile.Property, token: str) -> bool:
    """True when an UNKEYED parameter (vCard 2.1's bare-type style, e.g. `;BASE64`)
    equals `token`, case-insensitive."""
    return any(k is None and v.upper() == token for k, v in prop.params)


def _is_quoted_printable(prop: vcardfile.Property) -> bool:
    enc = _param_value(prop, "ENCODING")
    return bool(enc) and enc.upper() in _QP_VALUES


def _is_binary(prop: vcardfile.Property) -> bool:
    enc = _param_value(prop, "ENCODING")
    if enc and enc.upper() in _BINARY_VALUES:
        return True
    return any(_has_bare_token(prop, tok) for tok in _BINARY_VALUES)


def _decoded_value(prop: vcardfile.Property) -> str:
    """The property's rendered value. `vcardfile.parse_cards` already unfolded RFC 6350
    continuation lines (incl. the vCard 2.1 QUOTED-PRINTABLE soft break); this layers two
    further consumer-side decodes on top, always in this order: (1) where the property
    declares `ENCODING=QUOTED-PRINTABLE`, the actual hex-escape byte decode, honoring an
    explicit `CHARSET` param (old vCard 2.1 style) and falling back to UTF-8; (2) RFC 6350
    §3.4's TEXT-value backslash-escape decode (`\\n`→ a real newline, `\\,`/`\\;`→ a
    literal comma/semicolon), which applies UNCONDITIONALLY — independent of `ENCODING` — to
    every text-valued property (a compound field's own bare `;`/`,` separators, e.g. `N` or
    `ADR`, are untouched; only a backslash-escaped one is unescaped). Never called for a
    binary-encoded property (`_is_binary`) — see the shaper."""
    value = prop.value
    if _is_quoted_printable(prop):
        charset = _param_value(prop, "CHARSET") or "utf-8"
        raw = value.encode("ascii", errors="replace")
        decoded = quopri.decodestring(raw)
        try:
            value = decoded.decode(charset, errors="strict")
        except (LookupError, UnicodeDecodeError):
            value = decoded.decode("utf-8", errors="replace")
    return _unescape_text(value)


def _rendered_params(prop: vcardfile.Property) -> list[str]:
    """Every parameter, verbatim, in source order — `KEY=value` for a keyed parameter, the
    bare token alone for an unkeyed one (spec: `text/field`'s `params` field)."""
    return [f"{k}={v}" if k else v for k, v in prop.params]


def _load_card(corpus_root: Path, post: frontmatter.Post) -> vcardfile.Card:
    """The record's own single vCard, resolved containment-aware (§12.9) exactly like
    `units.load_json_artifact` — a promoted card's bytes stay resident in its parent `.vcf`
    until now. Raises `ValueError` when the record's bytes hold no parseable
    `BEGIN:VCARD…END:VCARD` span (parse-tolerant at the fleet level: the caller — `corpus
    shape` — reports this per-record rather than aborting a batch)."""
    record_id = str(post.metadata.get("id") or "")
    media_type = records.media_type_for(post)
    path = containment.ensure_local_bytes(corpus_root, record_id, mime.extension_for(media_type))
    cards, _skipped = vcardfile.parse_cards(path.read_bytes())
    if not cards:
        raise ValueError(
            "contact-card: no parseable BEGIN:VCARD…END:VCARD span in this record's bytes"
        )
    return cards[0]


@register_shaper("contact-card")
def shape_contact_card(
    build: recordbuild.Build,
    post: frontmatter.Post,
    corpus_root: Path,
    mapping: dict[str, Any],
) -> None:
    """Build the `contact-card` content zone on `build` from the record's own vCard bytes.
    `mapping` is unused (spec §7.2: an origin overlay may declare `form: {id: …}` with no
    `mapping` when the shape needs none) — vCard parsing is format-driven, not per-origin."""
    card = _load_card(corpus_root, post)
    display_name = card.display_name(1)

    recordbuild.open_section(build, form="contact-card", fields={"display_name": display_name})
    for n, prop in enumerate(card.properties, start=1):
        header: dict[str, Any] = {"name": prop.name}
        if prop.group:
            header["group"] = prop.group
        params = _rendered_params(prop)
        if params:
            header["params"] = params
        body = None if _is_binary(prop) else (_decoded_value(prop) or None)
        recordbuild.add_segment(
            build,
            atom="text",
            overlay="text/field",
            address=f"prop={n}",
            body=body,
            extra=header,
        )
