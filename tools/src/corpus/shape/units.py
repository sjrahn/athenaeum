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


def unit_array(data: Any, mapping: dict[str, Any]) -> list[Any]:
    """The unit array per `mapping['messages']` (a dotted path; empty/absent uses the JSON root
    when it is itself a list). Returns [] when the path resolves to a non-list."""
    path = str(mapping.get("messages") or "")
    arr = get_path(data, path) if path else data
    return arr if isinstance(arr, list) else []


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
    """The unit's attachment array per `mapping['attachments']`, or []."""
    arr = field(msg, mapping, "attachments")
    return arr if isinstance(arr, list) else []
