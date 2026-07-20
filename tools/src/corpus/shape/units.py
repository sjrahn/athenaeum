"""Mapping-driven unit extraction (spec §7.2 `form.mapping`, §6.2 `turn=`).

A form-mapped record's units live in the producer's own format at paths the origin overlay's
`form.mapping` names. This module resolves those paths — shared by the conversation shaper
(§12.5.0) and the resolver's `turn=` unit op (§6.2) — so a new platform is one origin overlay
with a mapping and zero code. The mapping's per-field values are dotted paths into each unit
object (`author.id`); the `messages` value is the dotted path to the unit array (empty = the
JSON root when it is itself an array).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import frontmatter

from corpus import containment, mime, records

#: Versioned op id (spec §6.4 / `ledger.md` §13.2's op-version pin) for the resolver's `turn=`
#: unit op and its `att=` companion (spec §6.2) — the form-mapping unit-array resolution this
#: module implements (`unit`, `attachments`, `field`, `repair_json_strings`). `turn=`/`att=` are
#: RECORD-LEVEL ops (`resolver._resolve_turn`) that bypass `transforms.REGISTRY` entirely — they
#: never ride the generic per-param cache-key ladder `transforms.csv.ENGINE_VERSION` does
#: (`resolver.py`'s own comments explain why) — so `_resolve_turn` folds this constant into its
#: cache key directly. A later change to unit-array indexing, attachment resolution, or the
#: mojibake repair is a NEW id, never a silent reinterpretation of an already-resolved (and
#: potentially already-cited, `ledger.md` §13.2) result.
ENGINE_VERSION = "units-turn@1"


def get_path(obj: Any, path: str) -> Any:
    """Dotted-path get into a nested mapping (`a.b.c`); empty path returns `obj`; a missing key
    or a non-mapping mid-path returns None."""
    if not path:
        return obj
    cur = obj
    for key in str(path).split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur


def load_json_artifact(corpus_root: Path, post: frontmatter.Post) -> Any:
    """Load + parse the record's JSON artifact bytes (containment-aware). Raises on unreadable
    bytes or malformed JSON — a caller shaping a declared-JSON form treats that as a hard error."""
    record_id = str(post.metadata.get("id") or "")
    media_type = records.media_type_for(post)
    binary = containment.ensure_local_bytes(corpus_root, record_id, mime.extension_for(media_type))
    return json.loads(binary.read_text(encoding="utf-8"))


#: The one supported `order` value (named for the producer semantics it declares, exactly as
#: `timestamp_style`'s one supported style is named for Google's takeout format): a source whose
#: own array is newest-message-first (Meta's Facebook/Instagram/Threads `messages[]`). The shaper
#: and the resolver's `turn=` unit op share `unit_array`, so declaring this once here makes
#: `turn=1` the OLDEST message everywhere, with no per-consumer reversal logic.
_NEWEST_FIRST = "newest-first"


def unit_array(data: Any, mapping: dict[str, Any]) -> list[Any]:
    """The unit array per `mapping['messages']` (a dotted path; empty/absent uses the JSON root
    when it is itself a list). Returns [] when the path resolves to a non-list.

    `mapping['order']`: absent means the array is already oldest-first (unchanged). The one
    supported value, `newest-first`, reverses it so `turn=1` is always the OLDEST unit — Meta's
    own export order (Facebook/Instagram/Threads) is newest-first, backwards from every other
    producer this shaper serves."""
    path = str(mapping.get("messages") or "")
    arr = get_path(data, path) if path else data
    arr = arr if isinstance(arr, list) else []
    if str(mapping.get("order") or "") == _NEWEST_FIRST:
        arr = list(reversed(arr))
    return arr


def unit(data: Any, mapping: dict[str, Any], n: int) -> Any:
    """The verbatim 1-indexed n-th unit object, or None when out of range."""
    arr = unit_array(data, mapping)
    return arr[n - 1] if 1 <= n <= len(arr) else None


def field(msg: Any, mapping: dict[str, Any], name: str) -> Any:
    """The value of a mapped per-unit field (`author_id`, `text`, …) for one unit object, or
    None when the mapping doesn't declare it or the path misses."""
    path = mapping.get(name)
    if not path:
        return None
    return get_path(msg, str(path))


def attachments(msg: Any, mapping: dict[str, Any]) -> list[Any]:
    """The unit's attachment array per `mapping['attachments']`, or [].

    `mapping['attachments']` is normally one dotted path (a single array field). When it is
    instead a LIST of dotted paths, each path's array is resolved against the unit and the
    results are concatenated in declaration order into one virtual attachment list — Meta's
    per-kind split (`photos[]`/`videos[]`/`gifs[]`/`audio_files[]`/`files[]`, all sharing the
    same `{uri, creation_timestamp?}` item shape) is the motivating case: a single dotted path
    can express only one of the five arrays, so a list union covers all of them without
    inventing a new attachment shape. `att=<M>` indexing is stable across calls: `unit_array`'s
    result — and hence each unit's own field values — never changes between the shaper's pass
    and the resolver's `turn=<N>&att=<M>` lookup for the same record."""
    paths = mapping.get("attachments")
    if isinstance(paths, list):
        result: list[Any] = []
        for p in paths:
            arr = get_path(msg, str(p))
            if isinstance(arr, list):
                result.extend(arr)
        return result
    arr = field(msg, mapping, "attachments")
    return arr if isinstance(arr, list) else []


#: The one supported `text_encoding` value: Meta's export mojibake bug — the JSON serializer
#: encodes non-ASCII text as if its UTF-8 bytes were Latin-1 codepoints, then escapes those.
#: Reversible by reading the mangled string back as Latin-1 bytes and decoding as UTF-8.
_META_MOJIBAKE = "meta-mojibake"


def text_encoding_repair(value: Any, mapping: dict[str, Any]) -> Any:
    """Apply the mapping's declared `text_encoding` repair to one mapped string field
    (`author_name` / `text`), or return `value` unchanged when no repair is declared, the style
    is unrecognized, or the value isn't a string (non-strings, including None, pass through).

    The one supported style, `meta-mojibake`, reverses Meta's export bug — confirmed
    mechanically reversible across the Facebook/Instagram/Threads census
    (`"Szymon GrabiÅ„ski"` -> `"Szymon Grabiński"`): `value.encode('latin-1').decode('utf-8')`,
    guarded by a try/except that falls back to the original string when the bytes don't
    round-trip — safe to apply uniformly, including to already-correct ASCII/UTF-8 text (a
    disclosed, per-producer mapping key, never a silent global heuristic — spec §7.2's
    `timestamp_style` precedent for a narrowly-named, opt-in text transform)."""
    if str(mapping.get("text_encoding") or "") != _META_MOJIBAKE or not isinstance(value, str):
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def repair_json_strings(value: Any, mapping: dict[str, Any]) -> Any:
    """Recursively apply `text_encoding_repair` to every string in a JSON-shaped structure
    (dict/list/str; any other type passes through unchanged) — the resolver's `turn=` unit op
    (§6.2) uses this to hand back a unit object whose text reads the SAME as the shaper's own
    per-turn envelope segments (`author_name`/`text`, `shape/conversation.py`), rather than the
    mapped fields only. Meta's mojibake export bug corrupts the WHOLE JSON payload uniformly
    (reactions, attachment captions, platform ids — not just the two mapped fields), and the
    repair is a guarded round-trip that is a no-op on already-correct text (`text_encoding_repair`
    docstring), so applying it to every string here is safe. Absent `text_encoding` on the
    mapping, this is a no-op walk (matches `text_encoding_repair`'s own no-repair contract)."""
    if isinstance(value, str):
        return text_encoding_repair(value, mapping)
    if isinstance(value, list):
        return [repair_json_strings(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: repair_json_strings(v, mapping) for k, v in value.items()}
    return value
