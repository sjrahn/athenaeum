"""Record I/O — frontmatter + zone-aware block parse/emit (spec §4).

A record is a markdown file with YAML frontmatter (spec §4.2) plus a body with three
zones (spec §4.3): metadata (artifact + origin + embed, plus legacy classify), content
(section + segment), and annotations (issue).

This module owns the **metadata** and **annotation** zones — including embeds
(reconciliation #1 vs the reference, which routed `<!--embed--><br>` through `segments.py` as a
content-zone block). The content zone is parsed/emitted by `segments.py`.

Exposes:

- `load(path)` — parse a record into a `frontmatter.Post` with a unified `post.metadata`
  view that merges all block fields into the top-level dict under namespaced keys
  (`_artifact`, `_origins`, `_classifies`, `_embeds`, `_contexts`). The remaining
  `post.content` carries the content zone only.
- `dump(post, path)` — write `post` back to disk in canonical layout: frontmatter →
  metadata-zone blocks (artifact, origins, classifies, embeds) → content body →
  annotation-zone blocks (context; `issue` is one namespace of it).
- Accessors: `media_type_for`, `title_for`, `description_for`, `derived_editorial`,
  `artifact_block`, `iter_origin_blocks`, `iter_classify_blocks`, `iter_embed_blocks`,
  `iter_context_blocks`, `iter_issue_blocks`, `primary_origin_uri`.
- Mutators: `set_artifact_block`, `append_origin_block`,
  `append_embed_block`, `append_context_block`, `append_issue_block`.
- Hash helpers: `format_hash(algo, hex_value)`.
- Stub creation: `stub_frontmatter(...)` returns the minimal frontmatter dict; the
  caller emits the artifact + origin blocks via the mutators.

Frontmatter core fields (spec §4.2 — the only fields, in spec order):
    id, title, description, transport, canonical, perceptual, touch, visibility

*(3.1)* `status` is retired from the frontmatter (spec §4.1, §12.19): a record's state is
derived, never stored. `load()` still reads a legacy `status:` key tolerantly (it survives
in `post.metadata` for lint to see — the `frontmatter-legacy-status` rule) but `dumps()`
never emits it — any write drops it. See `is_formed` / `has_stored_rendering` /
`derived_state` below for the derived-state predicates.

*(3.2)* `title`/`description` are retired as STORED fields — the display pair is
**derived** from role-marked schema fields (spec §4.2.3), computed by `derived_editorial`
/ `title_for` / `description_for`. Frontmatter `title:`/`description:` survive only as an
optional deliberate **override**: `load()` reads a stored pair tolerantly (empty-string
values are 3.1-era placeholders, not overrides) and `dumps()` drops an empty-string value
on write while preserving a non-empty one verbatim. `is_authored` is retired with the
stored-vouch state it named — see spec §4.1's "the vouch rides the form."

Block grammar (spec §4.3):
    Metadata zone:    <!--artifact <mime-type>-->     (exactly 1)
                      <!--origin [<id>[/<subtype>]]--> (1..N)
                      <!--classify <ns>/<id>[/<sub>]-->    (legacy 1.0; tolerated, lint-flagged)
                      <!--members-->                   (0..1)  — YAML list of member rows
                      <!--embed <mime-type>-->         (0..N)  (legacy pre-3.4; read, never written)
    Content zone:     <!--section [<ns>/<id>]-->       (0..N)  or
                      <!--segment <atom>[/<id>]-->     (0..N) sectionless
    Annotations zone: <!--issue <id>[/<subtype>]-->    (0..N)

The members block (3.4, spec §4.3.1.4) is the record's unabridged roster of embedded
assets: ONE block, a YAML list of rows closed to `address` / `media_type` / `transport` /
`bytes`. It is wholly attested — re-derived from the artifact, never authored — so it holds
no `description` and no `alt`; those descriptors come from the `members` derivation op, and
an asset's narration rides the section/segment that places it.

**The in-memory shape is unchanged from the retired per-asset block** — each row is still
`{media_type, address, transport, fields}` — so every reader that walked embeds keeps
working through `iter_members` (of which `iter_embed_blocks` is an alias). What narrowed is
what may appear in `fields`: `bytes` and nothing else.

Reading is dual-form and writing is form-preserving: a record parsed from legacy
`<!--embed-->` blocks keeps its full legacy `fields` in memory and is re-emitted as legacy
blocks, so no unrelated write path converts a record as a side effect of touching it.
Conversion happens exactly where the attested layer is rebuilt from the artifact
(`derive.attest`), and it DROPS the retired per-asset `description` — the field is abolished,
so there is nothing to migrate it to (§12.26). `pending_member_descriptions` reports what a
conversion will shed, so `corpus reattest` can say it out loud.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import frontmatter
import yaml

from . import paths

# Spec §4.2 core-fields order. `status` retired 3.1 (§4.1, §12.19) — a legacy `status:` key
# on input parses tolerantly into `post.metadata` (lint sees it) but is never written back;
# `dumps()` builds frontmatter from exactly this order, so omission here IS the drop.
_CORE_FIELD_ORDER = [
    "id",
    "title",
    "description",
    "transport",
    "canonical",
    "perceptual",
    "touch",
    "visibility",
]

# *(3.2)* The two frontmatter fields that are no longer stored facts but OPTIONAL
# overrides of the derived editorial pair (spec §4.2.1, §4.2.3) — `dumps()` drops an
# empty-string value for these on write (a 3.1-era placeholder) while preserving a
# non-empty one (the override).
_EDITORIAL_OVERRIDE_KEYS = frozenset({"title", "description"})

# Block opener prefixes.
_ARTIFACT_OPENER = "<!--artifact"
_ORIGIN_OPENER = "<!--origin"
_CLASSIFY_OPENER = "<!--classify"
_EMBED_OPENER = "<!--embed"
_MEMBERS_OPENER = "<!--members"

# PyYAML's C loader when the build provides it (it usually does), else the pure-Python one.
# Block payloads are the hottest parse in the system — `load_all` walks every record — and the
# C loader is ~5-8x faster on them. It matters most where the 3.4 members block concentrates a
# record's whole roster into ONE document: on the 22,293-member container, one big list under
# the pure-Python loader parsed SLOWER than 22,293 small ones (3.0s vs 2.1s), which would have
# made the new grammar a regression on exactly the records it helps most; under the C loader the
# same list parses in 0.40s. Measured, not assumed.
_Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

# The members row is a CLOSED shape (spec §4.3.1.4). A closed shape needs a closed check, or
# the block silently re-accumulates the descriptive payload 3.4 moved out of it — which is
# exactly how the retired per-asset block came to carry an authored `description` beside its
# byte-facts in the first place.
_MEMBER_ROW_KEYS = frozenset({"address", "media_type", "transport", "bytes"})
_SECTION_OPENER = "<!--section"
_SEGMENT_OPENER = "<!--segment"
_CONTEXT_OPENER = "<!--context"
# Legacy annotations-zone opener. `issue` is now the `issue` namespace of the unified
# `context` block (`<!--context issue/<id>-->`, spec §4.3.3). The reader still accepts the
# old `<!--issue <id>-->` form (parse-tolerantly) and upgrades it on the next write; only
# `<!--context-->` is ever emitted.
_ISSUE_OPENER = "<!--issue"
_ANNOTATION_OPENERS = (_CONTEXT_OPENER, _ISSUE_OPENER)
_BLOCK_CLOSER = "-->"

# Metadata-zone block openers (the openers that live before the content zone).
# Reconciliation #1: embed is here, NOT in the content zone (spec §4.3 4/2/1).
_METADATA_OPENERS = (
    _ARTIFACT_OPENER,
    _ORIGIN_OPENER,
    _CLASSIFY_OPENER,
    _MEMBERS_OPENER,
    _EMBED_OPENER,
)


# ---------- hash helpers ---------- #


def format_hash(algo: str, hex_value: str) -> str:
    """Build an `<algo>:<hex>` hash string."""
    return f"{algo}:{hex_value}"


# ---------- read / write ---------- #


def load(path: Path) -> frontmatter.Post:
    """Read a record from `path` and return a Post with a unified metadata view.

    Parses YAML frontmatter, then walks the body's three zones:

    - Metadata zone (artifact + origin + embed blocks, plus legacy 1.0 classify). Block fields are
      merged into `post.metadata` under namespaced keys (`_artifact`, `_origins`,
      `_classifies`, `_embeds`).
    - Content zone (section/segment blocks). Left in `post.content` verbatim for
      `segments.iter_blocks` to consume.
    - Annotations zone (context blocks). Merged into `post.metadata["_contexts"]` as a
      list of dicts (the legacy `<!--issue-->` form reads as the `issue` namespace).

    After load, `post.content` carries the content zone only.
    """
    post = frontmatter.load(path)
    body = post.content or ""
    metadata_blocks, after_metadata = _extract_metadata_blocks(body)
    content_body, annotations_body = _split_annotations(after_metadata)
    context_blocks = _extract_context_blocks(annotations_body)

    post.metadata["_artifact"] = metadata_blocks.get("artifact")
    post.metadata["_origins"] = metadata_blocks.get("origins", [])
    post.metadata["_classifies"] = metadata_blocks.get("classifies", [])
    post.metadata["_embeds"] = metadata_blocks.get("embeds", [])
    # Which roster form this record was read from, so `dumps()` round-trips it (3.4, §12.26).
    # Form-preserving on write is the safety property: a record still carrying legacy
    # per-asset blocks holds authored `description`s that only the re-homing pass may move,
    # so no unrelated read-modify-write may convert it and drop them in passing.
    post.metadata["_members_block"] = metadata_blocks.get("members_block", True)
    post.metadata["_contexts"] = context_blocks

    post.content = content_body
    return post


def dump(post: frontmatter.Post, path: Path) -> None:
    """Write `post` to `path` in canonical zone order (see `dumps`)."""
    paths.ensure_parent(path)
    path.write_text(dumps(post), encoding="utf-8")


def dumps(post: frontmatter.Post) -> str:
    """Serialize `post` to the canonical record text — the exact bytes `dump` writes.

    Order:
        frontmatter (core fields only, in spec order)
        metadata zone:     <!--artifact-->, <!--origin-->*, <!--classify-->* (legacy), <!--embed-->*
        content zone:      post.content verbatim (section/segment)
        annotations zone:  <!--context-->*

    Returned (not written) so callers like `corpus redraft` can compare a re-derived
    record against disk and write only when it changed.
    """
    artifact = post.metadata.get("_artifact")
    origins = post.metadata.get("_origins") or []
    classifies = post.metadata.get("_classifies") or []
    embeds = post.metadata.get("_embeds") or []
    contexts = post.metadata.get("_contexts") or []

    # Build core frontmatter — only spec-defined fields, in spec order.
    core: dict[str, Any] = {}
    for key in _CORE_FIELD_ORDER:
        if key not in post.metadata:
            continue
        value = post.metadata[key]
        # *(3.2)* `title`/`description` are OPTIONAL overrides of the derived editorial
        # pair (spec §4.2.1, §4.2.3) — an empty-string value is a 3.1-era placeholder
        # (the old required-vouch shape), never a deliberate assertion, so it is dropped
        # on write; a non-empty value is the override and is preserved verbatim (only the
        # §12.21 migration sweep may drop a non-empty value, never the emitter).
        if key in _EDITORIAL_OVERRIDE_KEYS and isinstance(value, str) and value == "":
            continue
        core[key] = value
    fm_text = _dump_yaml_block(core)

    # Build the metadata zone — artifact, origins, classifies, the roster.
    metadata_parts: list[str] = []
    if artifact:
        metadata_parts.append(_emit_artifact_block(artifact))
    for origin in origins:
        metadata_parts.append(_emit_origin_block(origin))
    for classify in classifies:
        metadata_parts.append(_emit_classify_block(classify))
    if embeds:
        if post.metadata.get("_members_block", True):
            metadata_parts.append(_emit_members_block(embeds))
        else:
            # Legacy per-asset blocks round-trip verbatim until the re-homing pass converts
            # the record (3.4, §12.26) — see `_members_block` in `load()`.
            for embed in embeds:
                metadata_parts.append(_emit_embed_block(embed))
    metadata_zone = "\n\n".join(metadata_parts)

    # Content zone — verbatim from post.content (segments.py owns this).
    content = (post.content or "").strip("\n")

    # Annotations zone — context blocks.
    annotation_parts = [_emit_context_block(ctx) for ctx in contexts]
    annotations_zone = "\n\n".join(annotation_parts)

    body_parts: list[str] = []
    if metadata_zone:
        body_parts.append(metadata_zone)
    if content:
        body_parts.append(content)
    if annotations_zone:
        body_parts.append(annotations_zone)
    body = "\n\n".join(body_parts)

    return (
        f"---\n{fm_text}---\n\n{body}\n"
        if body
        else f"---\n{fm_text}---\n"
    )


# ---------- block emit ---------- #


def _emit_block(opener: str, fields: dict[str, Any]) -> str:
    """Render a header-only block (artifact / origin / classify / issue): the opener line,
    the optional YAML body, and the closing `-->`. The single home for the block-tail
    serialization convention. (Embed differs — it always carries a payload — and emits its
    own form.)"""
    body_yaml = _dump_yaml_block(fields).rstrip("\n") if fields else ""
    if body_yaml:
        return f"{opener}\n{body_yaml}\n-->"
    return f"{opener}\n-->"


def _emit_artifact_block(artifact: dict[str, Any]) -> str:
    """Emit `<!--artifact <mime-type>\n<yaml>\n-->`.

    `artifact` carries `{mime: <type>, fields: {...}}`.
    """
    mime = artifact.get("mime", "")
    fields = artifact.get("fields") or {}
    return _emit_block(f"<!--artifact {mime}", fields)


def _emit_origin_block(origin: dict[str, Any]) -> str:
    """Emit `<!--origin [<id>[/<subtype>]]\n<yaml>\n-->`.

    `origin` carries `{id: <id-or-None>, subtype: <sub-or-None>, fields: {...}}`.
    """
    id_ = origin.get("id")
    subtype = origin.get("subtype")
    fields = origin.get("fields") or {}
    if id_ and subtype:
        opener = f"<!--origin {id_}/{subtype}"
    elif id_:
        opener = f"<!--origin {id_}"
    else:
        opener = "<!--origin"
    return _emit_block(opener, fields)


def _emit_classify_block(classify: dict[str, Any]) -> str:
    """Emit `<!--classify <namespace>[/<id>[/<subtype>]]\n<yaml>\n-->`.

    `classify` carries `{namespace, id, subtype, fields}`. When the id equals the
    namespace AND there is no subtype, the bare namespace is emitted
    (`<!--classify youtube-->`) rather than the redundant `<!--classify youtube/youtube-->`;
    the parser normalizes that to `(namespace, namespace, None)`. When a subtype IS present
    the redundant id is kept (`<!--classify ns/ns/subtype-->`) so the three-part identity
    survives the round-trip through `_split_namespaced` (collapsing to `ns/subtype` would
    re-parse the subtype as the id).
    """
    namespace = classify.get("namespace", "")
    id_ = classify.get("id", "")
    subtype = classify.get("subtype")
    fields = classify.get("fields") or {}
    qualified = (
        namespace if (not id_ or (id_ == namespace and not subtype)) else f"{namespace}/{id_}"
    )
    if subtype:
        qualified = f"{qualified}/{subtype}"
    return _emit_block(f"<!--classify {qualified}", fields)


def _emit_embed_block(embed: dict[str, Any]) -> str:
    """Emit `<!--embed <mime-type>\n<yaml>\n-->` (reconciliation #1: metadata zone).

    `embed` carries `{media_type: <mime>, address, transport, fields: {...}}`.
    `address` and `transport` are required; `fields` carries optional per-MIME
    extended fields (alt, description, width/height, etc.).
    """
    media_type = embed.get("media_type", "")
    address = embed.get("address")
    transport = embed.get("transport", "")
    fields = embed.get("fields") or {}
    payload: dict[str, Any] = {"address": address, "transport": transport}
    payload.update(fields)
    body_yaml = _dump_yaml_block(payload).rstrip("\n")
    return f"<!--embed {media_type}\n{body_yaml}\n-->"


def _emit_members_block(rows: list[dict[str, Any]]) -> str:
    """Emit the single `<!--members-->` block: a YAML list of closed four-key rows (§4.3.1.4).

    Only the four admitted keys are written, in a fixed order, and `bytes` is the one thing
    `fields` may contribute. Any other field a caller hands over is DROPPED here rather than
    carried: a descriptor belongs to the `members` derivation, and dropping at the one emitter
    is what keeps the on-disk roster closed no matter which producer filled it.
    """
    payload: list[dict[str, Any]] = []
    for row in rows:
        fields = row.get("fields") or {}
        entry: dict[str, Any] = {
            "address": row.get("address"),
            "media_type": row.get("media_type", ""),
            "transport": row.get("transport", ""),
        }
        if fields.get("bytes") is not None:
            entry["bytes"] = fields["bytes"]
        payload.append(entry)
    body_yaml = _dump_yaml_block(payload).rstrip("\n")
    return f"<!--members\n{body_yaml}\n-->"


def _emit_context_block(ctx: dict[str, Any]) -> str:
    """Emit `<!--context <namespace>/<id>[/<subtype>]\n<yaml>\n-->`.

    `ctx` carries `{namespace, id, subtype, fields}` — the same shape as a classify block,
    in the annotations zone (spec §4.3.3). The `issue` namespace's blocks carry the §4.3.3.1
    severity/resolution/detector fields; `reference` carries the citation-ladder fields; etc.
    Collapse mirrors `_emit_classify_block`: a bare namespace is emitted when `id == namespace`
    and there is no subtype.
    """
    namespace = ctx.get("namespace", "")
    id_ = ctx.get("id", "")
    subtype = ctx.get("subtype")
    fields = ctx.get("fields") or {}
    qualified = (
        namespace if (not id_ or (id_ == namespace and not subtype)) else f"{namespace}/{id_}"
    )
    if subtype:
        qualified = f"{qualified}/{subtype}"
    return _emit_block(f"<!--context {qualified}", fields)


def _dump_yaml_block(block: dict[str, Any] | list[Any]) -> str:
    """Render `block` as YAML using the dump conventions (block-style sequences, no
    key sorting, full-width). A LIST payload is the members block (3.4, §4.3.1.4)."""
    if not block:
        return ""
    return yaml.dump(
        block,
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
        width=10**9,
        default_flow_style=False,
    )


# ---------- block parse ---------- #


def _parse_block(
    lines: list[str], start: int
) -> tuple[str, dict[str, Any] | list[Any] | None, int]:
    """Parse a single HTML-comment block starting at `lines[start]`.

    Returns `(opener_line, body, next_index)`. `opener_line` is the full opener
    (e.g. `<!--artifact application/pdf`); `body` is the parsed YAML payload (or None for
    empty blocks); `next_index` is the line index after the closer.

    A payload is a mapping for every block but `<!--members-->` (3.4), whose payload is a
    LIST of member rows. The mapping requirement therefore moved to the callers that need
    it — `_require_mapping` below — rather than being enforced here, so a list payload is a
    grammar error only where a list is not the grammar.
    """
    opener = lines[start].rstrip()
    j = start + 1
    while j < len(lines) and lines[j].rstrip() != _BLOCK_CLOSER:
        j += 1
    if j >= len(lines):
        raise ValueError(f"unterminated block at line {start + 1}: {opener!r}")
    yaml_text = "\n".join(lines[start + 1 : j]).strip()
    body: dict[str, Any] | list[Any] | None
    if yaml_text:
        try:
            data = yaml.load(yaml_text, Loader=_Loader)
        except yaml.YAMLError as e:
            raise ValueError(f"malformed YAML in block at line {start + 1}: {e}") from e
        if data is not None and not isinstance(data, (dict, list)):
            raise ValueError(f"block at line {start + 1} body is neither a mapping nor a list")
        body = data if data is not None else {}
    else:
        body = None
    return opener, body, j + 1


def _require_mapping(body: Any, *, line_no: int, opener: str) -> dict[str, Any]:
    """The payload of every block but `<!--members-->` is a YAML mapping."""
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise ValueError(f"block at line {line_no} ({opener}) body is not a mapping")
    return body


def _extract_metadata_blocks(
    body: str,
) -> tuple[dict[str, Any], str]:
    """Parse leading metadata-zone blocks from `body`.

    Returns:
        ({artifact: {mime, fields} | None,
          origins: [{id, subtype, fields}, ...],
          classifies: [{namespace, id, subtype, fields}, ...],
          embeds: [{media_type, address, transport, fields}, ...],
          members_block: bool},
         remaining_body)

    Recognizes the spec-§4.3.1 openers: <!--artifact, <!--origin, <!--classify, <!--members,
    and the legacy <!--embed. Within the metadata zone, only blank lines may separate blocks.

    Both roster forms land in `embeds` — the one in-memory shape (§4.3.1.4) — with
    `members_block` recording WHICH form the record was read from, so `dumps()` can round-trip
    it. It is True unless legacy per-asset blocks were actually read, so a record with no
    roster at all (and any record built fresh) writes the current grammar. A record carrying
    both forms is a grammar error: the roster is single by construction, and two rosters cannot
    be reconciled without guessing which one is current.
    """
    result: dict[str, Any] = {
        "artifact": None,
        "origins": [],
        "classifies": [],
        "embeds": [],
        "members_block": True,
    }
    saw_members_block = False
    saw_legacy_embed = False
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].rstrip()
        if stripped == "":
            i += 1
            continue
        if not _is_metadata_opener(stripped):
            break
        opener, block_body, next_i = _parse_block(lines, i)
        if opener.startswith(_MEMBERS_OPENER):
            if saw_members_block:
                raise ValueError(f"second members block at line {i + 1}: the roster is one block")
            if saw_legacy_embed:
                raise ValueError(
                    f"record carries both a members block (line {i + 1}) and legacy embed "
                    f"blocks; the roster is single — one form or the other, never both"
                )
            saw_members_block = True
            result["embeds"].extend(_structure_member_rows(block_body, line_no=i + 1))
            i = next_i
            continue
        fields = _require_mapping(block_body, line_no=i + 1, opener=opener)

        if opener.startswith(_ARTIFACT_OPENER):
            mime = opener.removeprefix(_ARTIFACT_OPENER).strip()
            result["artifact"] = {"mime": mime, "fields": fields}
        elif opener.startswith(_ORIGIN_OPENER):
            arg = opener.removeprefix(_ORIGIN_OPENER).strip()
            id_, subtype = _split_qualifier(arg)
            result["origins"].append({"id": id_, "subtype": subtype, "fields": fields})
        elif opener.startswith(_CLASSIFY_OPENER):
            arg = opener.removeprefix(_CLASSIFY_OPENER).strip()
            namespace, id_, subtype = _split_namespaced(arg)
            result["classifies"].append(
                {"namespace": namespace, "id": id_, "subtype": subtype, "fields": fields}
            )
        elif opener.startswith(_EMBED_OPENER):
            if saw_members_block:
                raise ValueError(
                    f"legacy embed block at line {i + 1} follows a members block; the roster "
                    f"is single — one form or the other, never both"
                )
            saw_legacy_embed = True
            media_type = opener.removeprefix(_EMBED_OPENER).strip()
            embed = _structure_embed_fields(media_type, fields, line_no=i + 1)
            result["embeds"].append(embed)
        i = next_i

    result["members_block"] = not saw_legacy_embed

    while i < len(lines) and lines[i].strip() == "":
        i += 1
    return result, "\n".join(lines[i:])


def _structure_member_rows(
    payload: dict[str, Any] | list[Any] | None, *, line_no: int
) -> list[dict[str, Any]]:
    """Structure a `<!--members-->` payload into the in-memory row shape (spec §4.3.1.4).

    The payload is a YAML list of rows; each row is validated against the CLOSED four-key
    shape and returned as `{media_type, address, transport, fields}` — the same shape the
    retired per-asset block produced, so every existing reader is unaffected. `bytes` is the
    only key that may ride `fields`.
    """
    if payload is None or payload == {}:
        return []
    if not isinstance(payload, list):
        raise ValueError(
            f"members block at line {line_no}: payload is a YAML list of member rows, "
            f"got {type(payload).__name__}"
        )
    rows: list[dict[str, Any]] = []
    for n, raw in enumerate(payload, 1):
        if not isinstance(raw, dict):
            raise ValueError(
                f"members block at line {line_no}, row {n}: each row is a mapping, "
                f"got {type(raw).__name__}"
            )
        unknown = sorted(set(raw) - _MEMBER_ROW_KEYS)
        if unknown:
            raise ValueError(
                f"members block at line {line_no}, row {n}: unknown key(s) {unknown} — the "
                f"row is closed to {sorted(_MEMBER_ROW_KEYS)} (spec §4.3.1.4). A descriptive "
                f"field belongs to the `members` derivation; an asset's description belongs "
                f"to the block that places it."
            )
        media_type = str(raw.get("media_type") or "").strip()
        if not media_type:
            raise ValueError(f"members block at line {line_no}, row {n} missing media_type")
        rows.append(
            _structure_embed_fields(
                media_type,
                {k: v for k, v in raw.items() if k != "media_type"},
                line_no=line_no,
                what=f"members block at line {line_no}, row {n}",
            )
        )
    return rows


def _structure_embed_fields(
    media_type: str,
    fields: dict[str, Any],
    *,
    line_no: int,
    what: str | None = None,
) -> dict[str, Any]:
    """Pop address+transport off a roster row's YAML payload and return the structured
    dict `{media_type, address, transport, fields}`.

    Shared by the 3.4 members block and the legacy per-asset block, so the address/transport
    validation both forms must satisfy has exactly one implementation. `what` names the site
    in errors; it defaults to the legacy phrasing so existing messages are unchanged.
    """
    what = what or f"embed at line {line_no}"
    if "/" not in media_type:
        raise ValueError(
            f"{what}: media_type {media_type!r} is not a "
            f"`type/subtype` MIME (e.g. `image/png`)"
        )
    body_fields = dict(fields)
    address_raw = body_fields.pop("address", None)
    if address_raw is None:
        raise ValueError(f"{what}: missing required address")
    if isinstance(address_raw, list):
        address: str | list[str] = [str(x).strip() for x in address_raw if str(x).strip()]
        if not address:
            raise ValueError(f"{what}: empty address list")
    elif isinstance(address_raw, str):
        address = address_raw.strip()
        if not address:
            raise ValueError(f"{what}: missing required address")
    else:
        raise ValueError(
            f"{what}: invalid address type: {type(address_raw).__name__}"
        )
    # Prefer v1.0 `transport:` (str); accept v0.3 `byte_hash:` (dict) for back-compat read.
    transport_raw = body_fields.pop("transport", None)
    byte_hash_raw = body_fields.pop("byte_hash", None)
    if isinstance(transport_raw, str) and transport_raw.strip():
        transport = transport_raw.strip()
        if ":" not in transport:
            raise ValueError(
                f"{what}: transport {transport!r} missing `<algo>:` prefix"
            )
    elif isinstance(byte_hash_raw, dict):
        algo = str(byte_hash_raw.get("algo") or "").strip()
        value = str(byte_hash_raw.get("value") or "").strip()
        if not algo or not value:
            raise ValueError(f"{what}: byte_hash missing algo or value")
        transport = f"{algo}:{value}"
    else:
        raise ValueError(
            f"{what}: missing transport (expected `transport: <algo>:<hex>`)"
        )
    return {
        "media_type": media_type,
        "address": address,
        "transport": transport,
        "fields": body_fields,
    }


def _split_annotations(body: str) -> tuple[str, str]:
    """Split body into (content_zone, annotations_zone).

    Walks blocks from the end. Trailing annotation blocks (`<!--context-->`, or the legacy
    `<!--issue-->`) form the annotations zone; everything before is the content zone.
    """
    lines = body.splitlines()
    n = len(lines)
    i = n
    while i > 0:
        while i > 0 and lines[i - 1].strip() == "":
            i -= 1
        if i > 0 and lines[i - 1].rstrip() == _BLOCK_CLOSER:
            j = i - 2
            while j >= 0 and not lines[j].lstrip().startswith("<!--"):
                j -= 1
            if j >= 0 and lines[j].lstrip().startswith(_ANNOTATION_OPENERS):
                i = j
                continue
        break
    content_body = "\n".join(lines[:i]).rstrip("\n")
    annotations_body = "\n".join(lines[i:]).strip("\n")
    return content_body, annotations_body


def _extract_context_blocks(annotations_body: str) -> list[dict[str, Any]]:
    """Parse annotation blocks from the annotations zone into `{namespace, id, subtype,
    fields}`. Accepts both the `<!--context <ns>/<id>-->` form and (parse-tolerantly) the
    legacy `<!--issue <id>-->` form, which reads as the `issue` namespace."""
    if not annotations_body.strip():
        return []
    contexts: list[dict[str, Any]] = []
    lines = annotations_body.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].rstrip()
        if stripped == "":
            i += 1
            continue
        if not stripped.startswith(_ANNOTATION_OPENERS):
            i += 1
            continue
        opener, block_body, next_i = _parse_block(lines, i)
        fields = block_body or {}
        if opener.lstrip().startswith(_CONTEXT_OPENER):
            arg = opener.removeprefix(_CONTEXT_OPENER).strip()
            namespace, id_, subtype = _split_namespaced(arg)
        else:  # legacy <!--issue <id>[/<subtype>]-->
            arg = opener.removeprefix(_ISSUE_OPENER).strip()
            id_, subtype = _split_qualifier(arg)
            namespace = "issue"
        contexts.append(
            {"namespace": namespace, "id": id_, "subtype": subtype, "fields": fields}
        )
        i = next_i
    return contexts


def _is_metadata_opener(line: str) -> bool:
    """Check if a line opens a metadata-zone block."""
    return any(line.startswith(o) for o in _METADATA_OPENERS)


def _split_qualifier(arg: str) -> tuple[str | None, str | None]:
    """Parse `<id>[/<subtype>]` into `(id, subtype)`. Empty → (None, None)."""
    if not arg:
        return None, None
    if "/" in arg:
        id_, subtype = arg.split("/", 1)
        return id_.strip(), subtype.strip()
    return arg.strip(), None


def _split_namespaced(arg: str) -> tuple[str, str, str | None]:
    """Parse `<namespace>/<id>[/<subtype>]` into `(namespace, id, subtype)`.

    Single-segment input (no slash) becomes `(arg, arg, None)` — used for
    namespace-level class-ids whose namespace = the id (e.g. `youtube`, `document`).
    """
    if "/" not in arg:
        return arg, arg, None
    parts = arg.split("/", 2)
    if len(parts) == 2:
        return parts[0], parts[1], None
    return parts[0], parts[1], parts[2]


class _Dumper(yaml.SafeDumper):
    """SafeDumper with block-style sequences for readable lists."""

    def represent_sequence(self, tag, sequence, flow_style=None):  # type: ignore[override]
        return super().represent_sequence(tag, sequence, flow_style=False)


# ---------- accessors ---------- #


def artifact_block(post: frontmatter.Post) -> dict[str, Any] | None:
    """Return the record's `<!--artifact-->` block as `{mime, fields}`, or None."""
    return post.metadata.get("_artifact")


def media_type_for(post: frontmatter.Post) -> str:
    """Return the record's media-type (MIME). Reads from the artifact block."""
    artifact = artifact_block(post)
    if not artifact:
        return ""
    return str(artifact.get("mime") or "")


def title_for(post: frontmatter.Post, corpus_root: Path) -> str:
    """Return the record's derived display title (spec §4.2.3). See `derived_editorial`."""
    return derived_editorial_field(post, corpus_root, "title").value


def description_for(post: frontmatter.Post, corpus_root: Path) -> str:
    """Return the record's derived display description (spec §4.2.3). See
    `derived_editorial`."""
    return derived_editorial_field(post, corpus_root, "description").value


def iter_origin_blocks(post: frontmatter.Post) -> Iterator[dict[str, Any]]:
    """Yield each `<!--origin-->` block as `{id, subtype, fields}`."""
    yield from (post.metadata.get("_origins") or [])


def iter_classify_blocks(post: frontmatter.Post) -> Iterator[dict[str, Any]]:
    """Yield each legacy `<!--classify-->` block as `{namespace, id, subtype, fields}`.

    The classify block was removed in ATH-CORPUS 2.0 (spec §4.3.1.3 tombstone) — nothing
    consumes it; the grammar is kept parse/emit-tolerant so a 1.0-era record round-trips
    without data loss, and lint flags the block for migration (`classify-block-retired`)."""
    yield from (post.metadata.get("_classifies") or [])


def iter_members(post: frontmatter.Post) -> Iterator[dict[str, Any]]:
    """Yield each member row as `{media_type, address, transport, fields}` (spec §4.3.1.4).

    **The dual reader.** Rows come from the 3.4 `<!--members-->` block or from legacy
    per-asset `<!--embed-->` blocks, in one shape either way, so a caller never asks which
    form the record is in. The roster lives in the metadata zone — parsed by `load()`,
    emitted by `dumps()` in whichever form the record arrived in (§12.26).

    On a 3.4 record `fields` carries `bytes` and nothing else. On a legacy record it still
    carries whatever that record stored (`width`/`height`/`alt`/`description`/…), because
    reading must not lose what the re-homing pass has yet to move — see
    `pending_member_descriptions`.
    """
    yield from (post.metadata.get("_embeds") or [])


# The pre-3.4 name. Kept as an alias rather than swept: the reader's contract did not change
# (same shape, same ordering), so ~20 call sites across containment / resolver / promote /
# health / lint / tokens need no edit, and a rename would churn them for nothing.
iter_embed_blocks = iter_members


def pending_member_descriptions(post: frontmatter.Post) -> list[tuple[str, str]]:
    """Legacy per-asset `description`s this record still carries, as `(address, description)`.

    Non-empty means the record predates 3.4 and still carries prose in the retired per-asset
    `description` field (§4.3.1.4). Conversion **drops** it: the old blocks are deleted and the
    members block replaces them, and an abolished field has no successor to migrate into. This
    function exists so the drop can be REPORTED — `corpus reattest` prints what each record
    sheds, because a record silently losing 52 descriptions is the kind of thing an operator
    should watch happen (§12.26).
    """
    if post.metadata.get("_members_block", True):
        return []  # already 3.4 — the block cannot carry a description
    pending: list[tuple[str, str]] = []
    for row in post.metadata.get("_embeds") or []:
        description = str((row.get("fields") or {}).get("description") or "").strip()
        if not description:
            continue
        address = row.get("address")
        first = address[0] if isinstance(address, list) else address
        pending.append((str(first or ""), description))
    return pending


def iter_context_blocks(post: frontmatter.Post) -> Iterator[dict[str, Any]]:
    """Yield each `<!--context-->` block as `{namespace, id, subtype, fields}` (spec §4.3.3)."""
    yield from (post.metadata.get("_contexts") or [])


def iter_issue_blocks(post: frontmatter.Post) -> Iterator[dict[str, Any]]:
    """Yield each `issue`-namespace context block as `{id, subtype, fields}`.

    Back-compat projection of `iter_context_blocks` (issue is now the `issue` namespace of
    the unified context block, spec §4.3.3) — the shape health / lint / `show` expect."""
    for ctx in iter_context_blocks(post):
        if (ctx.get("namespace") or "") == "issue":
            yield {
                "id": ctx.get("id"),
                "subtype": ctx.get("subtype"),
                "fields": ctx.get("fields") or {},
            }


def iter_reference_blocks(post: frontmatter.Post) -> Iterator[dict[str, Any]]:
    """Yield each `reference`-namespace context block as `{id, subtype, fields}`.

    The `reference` namespace projection of `iter_context_blocks` (spec §4.3.3.3); the
    shape the `references` derived view (§9.9) consumes. Covers both emission paths — a
    mechanical (overlay-declared, `provenance: auto`, `role`) reference and a normalizer-
    /human-asserted citation share the namespace and differ only by their fields."""
    for ctx in iter_context_blocks(post):
        if (ctx.get("namespace") or "") == "reference":
            yield {
                "id": ctx.get("id"),
                "subtype": ctx.get("subtype"),
                "fields": ctx.get("fields") or {},
            }


def primary_origin_uri(post: frontmatter.Post) -> str:
    """Return the first URI from the first origin block, or `""`."""
    for origin in iter_origin_blocks(post):
        fields = origin.get("fields") or {}
        uri = fields.get("uri")
        if isinstance(uri, list) and uri:
            return str(uri[0])
        if uri:
            return str(uri)
    return ""


def iter_origin_uris(post: frontmatter.Post) -> Iterator[str]:
    """Yield every URI across all origin blocks (string and list forms flattened).

    The corpus-wide complement to `primary_origin_uri`: used to build the
    URI → record-id index that capture/crawl/links consult for dedup.
    """
    for origin in iter_origin_blocks(post):
        fields = origin.get("fields") or {}
        uri = fields.get("uri")
        if isinstance(uri, list):
            yield from (str(u) for u in uri if u)
        elif uri:
            yield str(uri)


# ---------- corpus-wide URI index (spec §9.3 `uris` view, consumer side) ---------- #


def iter_record_paths(corpus_root: Path) -> Iterator[Path]:
    """Yield every record markdown path under `records/<shard>/*.md`, sorted. The single
    source of the on-disk record layout — every command + health iterates through here, so
    the shard convention lives in one place."""
    yield from sorted((corpus_root / "records").glob("*/*.md"))


def load_all(corpus_root: Path) -> Iterator[tuple[Path, frontmatter.Post]]:
    """Yield `(path, post)` for every parseable record; unparseable records are silently
    skipped (parse-tolerant, per the project principle), never crashing the whole sweep.
    A caller that needs to report load failures should iterate `iter_record_paths` and
    `load` each itself."""
    for md in iter_record_paths(corpus_root):
        try:
            yield md, load(md)
        except Exception:  # tolerant parse — skip unloadable records
            continue


def identity_keyer(corpus_root: Path) -> Callable[[str], str]:
    """Return a `uri → identity key` function that memoizes the per-host capture recipe.

    The recipe (the origin-overlay read) depends only on the URI's host, so resolving it
    once per host — not once per URI — keeps a corpus-wide scan from re-parsing overlays on
    every URI. The key itself is `urls.identity_key` with the host's `url_equivalent` /
    `url_rewrite` rules (spec §7.2), exactly what `recipes.identity_key_for_url` computes per
    URL. Shared by `build_uri_index` and the maintenance scans (`records_holding_url`,
    `forget_origin`) — the bulk-site pattern `identity_key_for_url`'s docstring points at.
    """
    from . import urls as _urls
    from .capture import recipes as _recipes

    recipe_by_host: dict[str, dict] = {}

    def _key(uri: str) -> str:
        host = _urls.host_of(uri)
        if host not in recipe_by_host:
            recipe_by_host[host] = _recipes.capture_recipe_for_url(corpus_root, uri) or {}
        recipe = recipe_by_host[host]
        return _urls.identity_key(
            uri, recipe.get("url_equivalent"), url_rewrite=recipe.get("url_rewrite")
        )

    return _key


def build_uri_index(corpus_root: Path) -> dict[str, str]:
    """Map every record's origin URI → that record's id, keyed by **identity key**.

    One pass over `records/` via `load_all`. Each URI's key is `urls.identity_key` — the
    conservative `normalize` plus the URI host's opt-in `url_equivalent` rules (spec §7.2),
    so equivalent spellings (e.g. `…/page-1` ≡ `…/` , `?nested_view=1` noise) collapse to one
    key and an inbound variant matches the record. The host's `capture` recipe is resolved
    once per host (via `identity_keyer`) — the overlay lookup is not repeated per URI. Absent
    any `url_equivalent`, the key is exactly `normalize(uri)` (today's behavior). When two
    records claim the same key the later one (sorted by path) wins — a corpus-health concern
    surfaced elsewhere. The lightweight index `corpus links` / `corpus crawl` need.
    """
    _key = identity_keyer(corpus_root)
    index: dict[str, str] = {}
    for md, post in load_all(corpus_root):
        record_id = str(post.metadata.get("id") or md.stem)
        for uri in iter_origin_uris(post):
            try:
                key = _key(uri)
            except Exception:
                continue
            if key:
                index[key] = record_id
    return index


def find_by_uri(
    url: str,
    *,
    corpus_root: Path,
    index: dict[str, str] | None = None,
    _prekeyed: bool = False,
) -> str | None:
    """Return the id of the record whose origin URIs include `url`, else None.

    `url` is reduced to its **identity key** (`urls.identity_key` via the host's
    `url_equivalent` rules — spec §7.2) before lookup, so trailing-slash / query-order / case
    differences and host-declared equivalences (`/page-1` ≡ bare, query noise) don't cause a
    miss. The key matches `build_uri_index`'s keying. Pass a prebuilt `index`
    (`build_uri_index`) when making many lookups — e.g. a crawl frontier — to avoid rebuilding
    it per call.

    `_prekeyed=True` means `url` IS already an identity key (e.g. the redirect-resolved key
    from `recipes.resolve_identity_for_url`, where following a short link to its final URL
    happened before keying); the per-host re-keying is then skipped so the redirect resolution
    is not undone.
    """
    from .capture import recipes as _recipes

    if _prekeyed:
        target = url
    else:
        try:
            target = _recipes.identity_key_for_url(corpus_root, url)
        except Exception:
            target = url
    if index is None:
        index = build_uri_index(corpus_root)
    return index.get(target)


# ---------- content-identity dedup (cross-URL) ---------- #


def content_key(post: frontmatter.Post) -> tuple[str, tuple[str, ...]] | None:
    """Content-identity key for cross-URL dedup: the `canonical:` content hash PLUS
    the sorted set of embed transport hashes. Returns None when the record has no
    `canonical:` yet (an undrafted stub can't be content-deduped).

    The embed set guards against a false merge: `blake3-canonical-html` hashes the
    page's *visible text* only (it ignores `<img>` bytes), so two genuinely different
    image pages with identical sparse captions would share a canonical hash but not the
    same images. Requiring the embed set to match too keeps distinct diagrams distinct
    while still collapsing true duplicates (the same article reached by two URLs).

    NB: meaningful only when capture strips page chrome — otherwise per-page chrome
    text (breadcrumbs, personalized headers) perturbs the canonical hash so two
    same-content pages never match. See the `remove:` capture interaction.
    """
    canonical = str(post.metadata.get("canonical") or "").strip()
    if not canonical:
        return None
    transports = tuple(
        sorted(str(e.get("transport") or "") for e in (post.metadata.get("_embeds") or []))
    )
    return (canonical, transports)


def find_content_duplicate(
    post: frontmatter.Post, *, record_id: str, corpus_root: Path
) -> tuple[str, Path] | None:
    """Return `(id, path)` of an existing OTHER record whose `content_key` equals
    `post`'s, else None. Lets the draft step fold a same-content / different-URL capture
    into the record that already holds that content (the original keeps its id; the
    duplicate's URL is appended to the original's origin uri list). O(N) over the corpus
    — fine at draft cadence; build an index if it ever needs to scale."""
    key = content_key(post)
    if key is None:
        return None
    for md, other in load_all(corpus_root):
        if str(other.metadata.get("id") or md.stem) == record_id:
            continue
        if content_key(other) == key:
            return str(other.metadata.get("id") or md.stem), md
    return None


# ---------- mutators ---------- #


def set_artifact_block(
    post: frontmatter.Post, *, mime: str, fields: dict[str, Any] | None = None
) -> None:
    """Set the record's `<!--artifact-->` block."""
    post.metadata["_artifact"] = {"mime": mime, "fields": fields or {}}


def append_origin_block(
    post: frontmatter.Post,
    *,
    uri: str | list[str] | None = None,
    snapshot: str,
    schema_id: str | None = None,
    subtype: str | None = None,
    fields: dict[str, Any] | None = None,
) -> None:
    """Append a new `<!--origin-->` block to the record.

    `uri` may be a string, list[string], or None. A *retrieval* origin carries a uri; a
    dropped-in *local-file* origin omits it — the staging path the bytes sat at is unlinked
    at ingest, so there is nothing to re-fetch — and carries `filename`/`source_modified`
    in `fields` instead (spec §7.2). `snapshot` is ISO-8601. `schema_id` and `subtype`
    qualify the block opener (None → bare): `schema_id` is split on the FIRST `/` when it
    carries one (spec §4.3.1's `<id>[/<subtype>]` origin-opener grammar) — e.g. an ingest
    sidecar's `origin_schema: google-takeout/gmail` names `gmail` as a SUBTYPE of the
    `google-takeout` producer, not a distinct overlay id. A caller may instead pass an
    already-split `subtype=` explicitly (e.g. `restub`, replaying a parsed block's own
    `id`/`subtype`) — that wins over any slash embedded in `schema_id`. `fields` carries
    any additional schema-declared extended fields beyond the universal uri:/snapshot:.
    """
    block_fields: dict[str, Any] = {}
    if uri:
        block_fields["uri"] = uri
    block_fields["snapshot"] = snapshot
    if fields:
        block_fields.update(fields)
    id_, inferred_subtype = _split_qualifier(schema_id) if schema_id else (None, None)
    origins = post.metadata.setdefault("_origins", [])
    origins.append(
        {
            "id": id_,
            "subtype": subtype if subtype is not None else inferred_subtype,
            "fields": block_fields,
        }
    )


def _alias_already_present(alias: str, existing: list[str], corpus_root: Path | None) -> bool:
    """True when `alias` is already among `existing` origin URIs. Exact-string when
    `corpus_root` is None; by identity key (host `url_equivalent`) otherwise — degrading to
    exact-string if identity resolution raises."""
    if corpus_root is None:
        return alias in existing
    from .capture import recipes as _recipes

    try:
        alias_key = _recipes.identity_key_for_url(corpus_root, alias)
        return any(_recipes.identity_key_for_url(corpus_root, u) == alias_key for u in existing)
    except Exception:
        return alias in existing


def add_origin_uri_alias(
    post: frontmatter.Post, alias: str, *, corpus_root: Path | None = None
) -> bool:
    """Fold `alias` into the most-recent origin block's `uri:` list, unless it already
    appears on some origin block. Returns True when added.

    Drafters that discover a canonical (`<link rel=canonical>`) or post-redirect URL of
    the captured page use this to collapse those forms into the origin's uri list (spec
    §7.2 — canonical / shortlink / final URLs are one logical origin), rather than
    stranding them on the artifact block. The most-recent origin block is the one the
    current capture seeded, so its uri list is where the current page's aliases belong.

    With `corpus_root`, the already-present check is by **identity key** (`urls.identity_key`
    via the host's `url_equivalent` rules — spec §7.2): an `alias` that denotes the same
    resource as an existing uri (a query-noise / `/page-1` variant) is **not** appended,
    keeping the origin block minimal. Without `corpus_root`, the check is exact-string
    (back-compat).
    """
    alias = (alias or "").strip()
    if not alias:
        return False
    origins = post.metadata.get("_origins") or []
    if not origins:
        return False
    existing: list[str] = []
    for origin in origins:
        uri = (origin.get("fields") or {}).get("uri")
        existing.extend(str(u).strip() for u in (uri if isinstance(uri, list) else [uri]) if u)
    if _alias_already_present(alias, existing, corpus_root):
        return False
    target = origins[-1].setdefault("fields", {})
    uri = target.get("uri")
    if isinstance(uri, list):
        uri.append(alias)
    elif uri:
        target["uri"] = [str(uri).strip(), alias]
    else:
        target["uri"] = alias
    return True


def merge_origin_fields(post: frontmatter.Post, fields: dict[str, Any]) -> None:
    """Merge extra fields into the most-recent origin block (the one the current capture
    seeded), beside `uri:`/`snapshot:`.

    Drafters attach source-provided enrichment here — e.g. a yt-dlp capture's `ytdlp_*`
    fields (title/description/uploader/counts/`ytdlp_comments`). This is where-it-came-from
    metadata, NOT facts about the artifact bytes, so it belongs on the origin block, never
    the artifact block or the body (spec §7.2)."""
    if not fields:
        return
    origins = post.metadata.get("_origins") or []
    if not origins:
        return
    target = origins[-1].setdefault("fields", {})
    for key, value in fields.items():
        target[key] = value


def set_origin_schema_id(post: frontmatter.Post, schema_id: str) -> bool:
    """Stamp `schema_id` as the most-recent origin block's overlay id[/subtype] —
    promoting its opener to `<!--origin <id>[/<subtype>]-->`. Returns True when set.

    Producer-declared overlay binding (spec §7.2): a uri-less origin (e.g. an `imessage-export`
    local file) has no `uri:` to match, so the producer names the overlay directly — a capture
    sidecar's `origin_schema:` at ingest, or an injected `corpus-origin-schema` meta the drafter
    folds in. A compound `schema_id` (`<id>/<subtype>`, e.g. `google-takeout/gmail`) splits on
    the FIRST `/` (spec §4.3.1's origin-opener grammar) — `gmail` is a SUBTYPE of the
    `google-takeout` producer, not a distinct overlay id; the split replaces BOTH the block's
    `id` and `subtype`, so re-stamping with a bare id also clears a stale subtype. Block-side
    overlay resolution then ladders subtype-qualified overlay first, id overlay fallback (see
    `_origin_overlay_ladder`). The bound id drives the derived `origin/<id>[/<subtype>]`
    classification, overlay guidance, and ledger harvest rules matching on `origin.id`
    (`ledger.md` §10) with no uri."""
    schema_id = (schema_id or "").strip()
    if not schema_id:
        return False
    origins = post.metadata.get("_origins") or []
    if not origins:
        return False
    id_, subtype = _split_qualifier(schema_id)
    origins[-1]["id"] = id_
    origins[-1]["subtype"] = subtype
    return True


def qualify_origin_blocks(post: frontmatter.Post, corpus_root: Path) -> list[str]:
    """Stamp the matching origin-overlay id onto every bare (id-less) `<!--origin-->`
    block whose `uri:` matches an overlay's host pattern / scheme cue — the §7.2 upgrade
    from a bare opener to `<!--origin <id>-->` for a URL-retrieved origin (the sibling of
    `set_origin_schema_id`'s producer-declared, uri-less binding path).

    Iterates EVERY origin block (a re-capture may carry more than one), never just the
    most-recent. **Never touches a block that already carries an id** — a producer-
    declared id (this function's own prior stamp, or `set_origin_schema_id`'s) is
    sacrosanct: never re-stamped, never downgraded — and, since a `subtype` never rides
    without an `id` (spec §4.3.1's `<id>[/<subtype>]` grammar), a block already carrying a
    subtype is always skipped too, by the same id check. A bare block with no `uri:`, or
    whose `uri:` matches no overlay, is correctly left bare (no overlay, no id — spec §7.2).
    This function stamps a bare (host-matched) `id` only — it never sets `subtype`.
    Deterministic (`schemas.best_origin_overlay_for_uris` resolves ties) and idempotent —
    a second call finds nothing left unqualified to stamp.

    Returns the list of overlay ids stamped, one entry per newly-qualified block (empty
    when nothing changed)."""
    from . import schemas as _schemas

    stamped: list[str] = []
    for origin in post.metadata.get("_origins") or []:
        if origin.get("id"):
            continue
        fields = origin.get("fields") or {}
        uri = fields.get("uri")
        uris = uri if isinstance(uri, list) else ([uri] if uri else [])
        uris = [str(u).strip() for u in uris if u]
        if not uris:
            continue
        winner = _schemas.best_origin_overlay_for_uris(corpus_root, uris)
        if not winner:
            continue
        origin["id"] = winner
        stamped.append(winner)
    return stamped


def append_member(
    post: frontmatter.Post,
    *,
    media_type: str,
    address: str | list[str],
    transport: str,
    fields: dict[str, Any] | None = None,
) -> None:
    """Append a member row to the record's roster (spec §4.3.1.4).

    Callers are the attesting drafters, which compute the FULL descriptor set for the
    `members` derivation. Only `bytes` is retained here; every other field is dropped, because
    the stored roster is closed to four keys and the descriptors are re-derived on demand.
    Dropping at this seam (and again at the emitter) means no producer can widen the block by
    handing over extra fields — the closed shape holds without every drafter having to know it.
    """
    given = fields or {}
    kept = {"bytes": given["bytes"]} if given.get("bytes") is not None else {}
    rows = post.metadata.setdefault("_embeds", [])
    rows.append(
        {
            "media_type": media_type,
            "address": address,
            "transport": transport,
            "fields": kept,
        }
    )


# The pre-3.4 name, kept for the drafters and compile ops that call it. Same behaviour: the
# descriptive fields they pass are now dropped rather than stored.
append_embed_block = append_member


def append_context_block(
    post: frontmatter.Post,
    *,
    namespace: str,
    id: str,
    subtype: str | None = None,
    fields: dict[str, Any] | None = None,
) -> None:
    """Append a `<!--context <namespace>/<id>-->` block to the annotations zone (spec
    §4.3.3). `fields` carries the namespace's overlay fields (caller controls order);
    `provenance: auto` marks an engine-stamped block, its absence a hand-asserted one."""
    contexts = post.metadata.setdefault("_contexts", [])
    contexts.append(
        {"namespace": namespace, "id": id, "subtype": subtype, "fields": fields or {}}
    )


def append_issue_block(
    post: frontmatter.Post,
    *,
    id: str,
    subtype: str | None = None,
    severity: str,
    resolution: str = "open",
    detector: str,
    address: str | None = None,
    fields: dict[str, Any] | None = None,
) -> None:
    """Append an `issue`-namespace context block (spec §4.3.3.1 shape).

    Convenience over `append_context_block(namespace="issue", …)`: assembles the universal
    issue fields (severity, resolution, detector, optional address) plus any id-specific
    `fields`. If `address` is provided the issue is segment-scoped, otherwise record-scoped.
    """
    block_fields: dict[str, Any] = {
        "severity": severity,
        "resolution": resolution,
        "detector": detector,
    }
    if address:
        block_fields["address"] = address
    if fields:
        block_fields.update(fields)
    append_context_block(post, namespace="issue", id=id, subtype=subtype, fields=block_fields)


# ---------- derived classifications view (spec §9.1) ---------- #


def derived_classifications(post: frontmatter.Post) -> list[str]:
    """Compute the derived `classifications[]` view by walking the body (spec §9.1).

    Structural-derived only: the artifact contributes `mime/<mime-type>`; each qualified
    origin block contributes `origin/<id>[/<subtype>]`; each **qualified section opener**
    contributes `form/<form-id>` (3.0). Dedupe preserving body order. Embeds and context
    blocks do not contribute (embeds are assets, context records observations), and legacy
    classify blocks no longer do (interpretive classification is ledger knowledge, 2.0).
    """
    from . import segments as _segments

    result: list[str] = []
    seen: set[str] = set()

    def _add(entry: str) -> None:
        if entry not in seen:
            result.append(entry)
            seen.add(entry)

    artifact = artifact_block(post)
    if artifact and artifact.get("mime"):
        _add(f"mime/{artifact['mime']}")

    for origin in iter_origin_blocks(post):
        id_ = origin.get("id")
        if not id_:
            continue
        subtype = origin.get("subtype")
        _add(f"origin/{id_}/{subtype}" if subtype else f"origin/{id_}")

    # Qualified section openers contribute `form/<form-id>` (§9.1, §4.4.1). A bare 2.x TOC
    # section (form=None) contributes nothing. Parse-tolerant: an unparseable content zone
    # simply yields no form rows.
    try:
        for blk in _segments.iter_blocks(post.content or ""):
            if isinstance(blk, _segments.Section) and blk.form:
                _add(f"form/{blk.form}")
    except Exception:
        pass

    return result


# ---------- derived editorial fields (spec §4.2.3) ---------- #

_EDITORIAL_ROLES = ("title", "description")


@dataclass(frozen=True)
class EditorialField:
    """One resolved display-editorial field (spec §4.2.3): its value and which layer
    produced it.

    `layer` is one of `"override"` (the frontmatter pair, §4.2.1), `"form"`, `"origin"`,
    `"artifact"` (role-marked candidates, precedence artifact → origin → form), or `None`
    when every layer's candidate is empty — an honest empty result, not a defect."""

    value: str
    layer: str | None = None


def _role_marked_fields(schema: dict[str, Any] | None, role: str) -> list[str]:
    """Field names in `schema`'s `extended_fields` declared `role: <role>` (spec §4.2.3),
    in YAML declaration order. Tolerant of a missing/malformed `extended_fields` (unknown
    `role:` values, and non-dict declarations, are silently ignored)."""
    if not isinstance(schema, dict):
        return []
    ext = schema.get("extended_fields")
    if not isinstance(ext, dict):
        return []
    return [
        name
        for name, decl in ext.items()
        if isinstance(decl, dict) and decl.get("role") == role
    ]


def _first_non_empty(fields: dict[str, Any] | None, names: list[str]) -> str:
    """The first non-empty value among `names`, read from `fields` in the order given —
    the within-layer resolution rule (spec §4.2.3: "the schema's declaration order, first
    non-empty winning"). A list-valued field (`string_or_list` — e.g. an iMessage group's
    names across a rename window) joins its non-empty items with ", " rather than
    stringifying to a Python repr."""
    if not fields:
        return ""
    for name in names:
        value = fields.get(name)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            text = ", ".join(t for v in value if (t := str(v).strip()))
        else:
            text = str(value).strip()
        if text:
            return text
    return ""


def _artifact_editorial_candidate(post: frontmatter.Post, corpus_root: Path, role: str) -> str:
    """The artifact layer's role-marked candidate (spec §4.2.3, weakest in precedence):
    the artifact block's mime schema `extended_fields` marked `role: <role>`."""
    from . import schemas as _schemas

    artifact = artifact_block(post)
    if not artifact:
        return ""
    mime = str(artifact.get("mime") or "")
    if not mime:
        return ""
    schema = _schemas.load_mime_schema(corpus_root, mime)
    names = _role_marked_fields(schema, role)
    if not names:
        return ""
    return _first_non_empty(artifact.get("fields"), names)


def _origin_overlay_ladder(origin: dict[str, Any]) -> list[str]:
    """The overlay lookup ladder for one origin block (spec §4.3.1, §7.2): a subtype-
    qualified block (`id`/`subtype` both set) tries its full `<id>/<subtype>` overlay
    FIRST, falling back to the bare `<id>` producer overlay — `gmail` is a SUBTYPE of the
    `google-takeout` producer, and an authored subtype overlay is more specific than the
    producer's. An id-less block contributes no rungs; a subtype-less block is a
    one-rung ladder."""
    id_ = origin.get("id")
    if not id_:
        return []
    subtype = origin.get("subtype")
    if subtype:
        return [f"{id_}/{subtype}", str(id_)]
    return [str(id_)]


def _origin_editorial_candidate(post: frontmatter.Post, corpus_root: Path, role: str) -> str:
    """The origin layer's candidate (spec §4.2.3): the LATEST qualified origin block whose
    overlay ladder yields a non-empty value wins — origin blocks append in capture order,
    so a re-capture's fields supersede. Per block, each ladder rung (subtype-qualified
    overlay first, id overlay fallback — `_origin_overlay_ladder`) tries its declared
    `editorial.<role>_template` first (a mechanical composition over the block's fields,
    all-or-nothing), then its role-marked fields, before the ladder moves to the next
    (less specific) rung — the origin layer has no implicit authored value, so the order
    is just template → marks. A bare (unqualified) origin block matches no overlay and
    contributes nothing (spec §7.2)."""
    from . import schemas as _schemas

    for origin in reversed(list(iter_origin_blocks(post))):
        fields = origin.get("fields")
        for overlay_id in _origin_overlay_ladder(origin):
            schema = _schemas.load_origin_overlay_by_id(corpus_root, overlay_id)
            if not isinstance(schema, dict):
                continue
            editorial = schema.get("editorial")
            template = editorial.get(f"{role}_template") if isinstance(editorial, dict) else None
            if template:
                templated = _resolve_editorial_template_value(template, fields)
                if templated:
                    return templated
            names = _role_marked_fields(schema, role)
            if names:
                value = _first_non_empty(fields, names)
                if value:
                    return value
    return ""


def _whole_record_section(post: frontmatter.Post) -> Any:
    """The record's whole-record form section (spec §4.3.2.1: a qualified section with no
    `address`), or None. At most one exists per the grammar (a whole-record section admits
    no sibling sections). Parse-tolerant, like the derived-state predicates below."""
    from . import segments as _segments

    try:
        blocks = _segments.iter_blocks(post.content or "")
    except Exception:
        return None
    for blk in blocks:
        if isinstance(blk, _segments.Section) and blk.form and blk.address is None:
            return blk
    return None


_TEMPLATE_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _resolve_editorial_template(template: str, fields: dict[str, Any] | None) -> str:
    """Resolve a form's `editorial.<role>_template` (spec §4.2.3) against the whole-record
    form section's own header field values (`fields` — the section's `extra`).

    `{name}` placeholders substitute a named field's value, read exactly as
    `_first_non_empty` reads a role-marked field (a list joins its non-empty items with
    `, ` rather than stringifying to a Python repr); static text passes through unchanged.
    Resolution is **all or nothing**: the template resolves only when EVERY placeholder
    names a field holding a non-empty value — one unresolved placeholder falls the whole
    template through (returned here as `""`), never a partial composition."""
    if not template:
        return ""
    names = _TEMPLATE_PLACEHOLDER.findall(template)
    if not names:
        return template.strip()
    values: dict[str, str] = {}
    for name in names:
        text = _first_non_empty(fields, [name])
        if not text:
            return ""
        values[name] = text
    return template.format(**values).strip()


def _resolve_editorial_template_value(value: Any, fields: dict[str, Any] | None) -> str:
    """Resolve an `editorial.<role>_template` value that may be a single template string
    OR an ordered LIST of template strings (the cascade form): try each entry in order,
    returning the first whose `_resolve_editorial_template` resolution is non-empty
    (still all-or-nothing PER entry — a partial composition never wins). A non-string
    list entry is tolerantly skipped, like any other malformed overlay data. A plain
    string behaves exactly as before."""
    if isinstance(value, (list, tuple)):
        for entry in value:
            if not isinstance(entry, str):
                continue
            resolved = _resolve_editorial_template(entry, fields)
            if resolved:
                return resolved
        return ""
    return _resolve_editorial_template(str(value), fields)


def _form_editorial_candidate(post: frontmatter.Post, corpus_root: Path, role: str) -> str:
    """The form layer's candidate (spec §4.2.3, strongest of the three schema-driven
    layers): only the WHOLE-RECORD form section contributes — a span-scope section
    describes its span, never the record. Three candidate kinds, checked in order until
    one is non-empty: the universal `title:`/`description:` header fields — implicitly
    role-marked on every form, the interpretive vouch, always checked first; the
    contract's declared `editorial.<role>_template` (a mechanical composition over more
    than one header field, resolved all-or-nothing — see `_resolve_editorial_template`);
    and any additional field the form contract explicitly marks `role: <role>`, in the
    schema's declaration order."""
    from . import schemas as _schemas

    section = _whole_record_section(post)
    if section is None:
        return ""
    if role == "description":
        implicit = str(section.description or "").strip()
    else:
        implicit = str((section.extra or {}).get(role) or "").strip()
    if implicit:
        return implicit
    schema = _schemas.load_form_overlay(corpus_root, section.form)
    editorial = schema.get("editorial") if isinstance(schema, dict) else None
    template = editorial.get(f"{role}_template") if isinstance(editorial, dict) else None
    if template:
        templated = _resolve_editorial_template_value(template, section.extra)
        if templated:
            return templated
    names = [n for n in _role_marked_fields(schema, role) if n not in _EDITORIAL_ROLES]
    if not names:
        return ""
    return _first_non_empty(section.extra, names)


def derived_editorial_field(
    post: frontmatter.Post,
    corpus_root: Path,
    role: str,
    *,
    include_override: bool = True,
) -> EditorialField:
    """Resolve one display-editorial field — the shared implementation behind
    `title_for` / `description_for` / `derived_editorial` (spec §4.2.3).

    `role` is `"title"` or `"description"`. Precedence, strongest first: the frontmatter
    override (§4.2.1) when `include_override` — pass `include_override=False` to resolve
    what an override would be redundant AGAINST (the `editorial-override-redundant` lint
    rule, §12.21 step 1) — then the form layer (whole-record section only), then origin
    (latest qualified block wins), then artifact; each layer's own within-layer resolution
    is first-non-empty by schema declaration order. An empty/absent layer candidate falls
    through to the next, and an all-empty chain resolves to an honest empty result (spec
    §4.2.3) — not a defect, a role-marking or forming opportunity health surfaces.

    *(3.2 phase 2, §12.21 step 2)* The transitional pre-role-mark fallback (the artifact
    block's bare `title` field, then the first origin block's `ytdlp_title`, unconditional
    on schema declaration or origin qualification) is retired now that the mime/origin
    schemas carry real `role:` marks. The origin layer only resolves through a QUALIFIED
    origin block (`schema_id` set) — `qualify_origin_blocks` is what sets it for a
    URL-retrieved origin (host-pattern / scheme match, §7.2), wired into both ingest and
    `corpus reattest` via `derive.apply_drafter_result`, so a video/web record's
    `ytdlp_title` resolves as soon as its host has a matching origin overlay. A record
    whose host carries NO overlay stays bare and its title candidate stays unreachable —
    correct (no overlay, no id), not a gap.
    """
    if include_override:
        override = str(post.metadata.get(role) or "").strip()
        if override:
            return EditorialField(value=override, layer="override")

    form_value = _form_editorial_candidate(post, corpus_root, role)
    if form_value:
        return EditorialField(value=form_value, layer="form")

    origin_value = _origin_editorial_candidate(post, corpus_root, role)
    if origin_value:
        return EditorialField(value=origin_value, layer="origin")

    artifact_value = _artifact_editorial_candidate(post, corpus_root, role)
    if artifact_value:
        return EditorialField(value=artifact_value, layer="artifact")

    return EditorialField(value="", layer=None)


def derived_editorial(post: frontmatter.Post, corpus_root: Path) -> tuple[str, str]:
    """`(title, description)` — spec §4.2.3's derived editorial pair, computed at read
    time exactly like the classifications view. The one shared resolution every consumer
    (the derived body, search indexing, export, health, `title_for`/`description_for`)
    reads. See `derived_editorial_fields` for the winning-layer diagnostic."""
    return (
        derived_editorial_field(post, corpus_root, "title").value,
        derived_editorial_field(post, corpus_root, "description").value,
    )


def derived_editorial_fields(
    post: frontmatter.Post, corpus_root: Path
) -> dict[str, EditorialField]:
    """`{"title": EditorialField, "description": EditorialField}` — the diagnostic variant
    of `derived_editorial`, reporting which layer won each field (`show`/`diagnose`/`find`
    want this over the bare value)."""
    return {
        role: derived_editorial_field(post, corpus_root, role) for role in _EDITORIAL_ROLES
    }


def has_editorial_override(post: frontmatter.Post) -> bool:
    """True when the frontmatter carries a non-empty `title` or `description` override
    (spec §4.2.1). The closest 3.2 analog of the retired `is_authored` vouch-presence
    signal for a record whose content zone carries no form section to hold the interpretive
    vouch (§4.2.3's "the vouch rides the form") — used where a lint rule's old `is_authored`
    gate was really asking "has anyone deliberately asserted an editorial claim on this
    record," not "is this record formed.\""""
    return bool(str(post.metadata.get("title") or "").strip()) or bool(
        str(post.metadata.get("description") or "").strip()
    )


# ---------- derived-state predicates (spec §4.1) ---------- #


def is_formed(post: frontmatter.Post) -> bool:
    """True when a **form section** governs the record's content zone (spec §4.1,
    §4.3.2.1): at least one qualified `<!--section <form-id>-->` block — a bare 2.x TOC
    section (form=None) does not count, exactly as it contributes no `form/*` row to the
    derived classifications view (§9.1). Parse-tolerant: an unparseable content zone reads
    as not-formed rather than raising."""
    from . import segments as _segments

    try:
        blocks = _segments.iter_blocks(post.content or "")
    except Exception:
        return False
    return any(isinstance(b, _segments.Section) and b.form for b in blocks)


def has_stored_rendering(post: frontmatter.Post) -> bool:
    """True when the record's content zone carries at least one **content-atom** segment
    (text/image/audio/video) — structural byte-marks (§4.3.2.3) do NOT count, since they
    carry no rendering of their own, only a boundary mark. Segments count whether top-level
    (formless) or nested inside a form section. Parse-tolerant, like `is_formed`."""
    from . import segments as _segments

    try:
        blocks = _segments.iter_blocks(post.content or "")
    except Exception:
        return False
    for b in blocks:
        if isinstance(b, _segments.Section):
            if any(not s.is_structural for s in b.segments):
                return True
        elif isinstance(b, _segments.Segment) and not b.is_structural:
            return True
    return False


def derived_state(post: frontmatter.Post, corpus_root: Path | None = None) -> str:
    """The record's derived layer state (spec §4.1) — one of:

    - `"terminal"` *(3.3)* — a TERMINAL contract governs the record
      (`shape.governing_form`, §7.8) and it stores no rendering: an opener-only whole-record
      terminal section is still `terminal`, never `formed` — a terminal contract is not a
      rendering contract, so it can't satisfy the `formed` row even when stamped. Requires
      `corpus_root` (schema context) to resolve; see below.
    - `"formed"` — a form section governs the content zone (`is_formed`); wins even when
      the record ALSO carries top-level formless segments (the mixed-artifact case, §4.3.2.1).
    - `"rendered"` — a stored rendering with no governing form: the grandfathered population
      (§12.18 step 3 / §12.19) — `has_stored_rendering` true, `is_formed` false.
    - `"proxy"` — none of the above: the artifact's proxy under the identity contract (§4.1,
      §7.8), complete and honest, not a backlog. *(3.3: narrows to mean genuinely
      unassessed-or-awaiting now that formless-permanently is the `terminal` value above.)*

    `corpus_root` is OPTIONAL schema context (3.3): terminal detection needs the overlay
    grain (`shape.governing_form` walks origin/mime declarations and the disposition
    derivation, §7.8) that a bare record can't supply. Omit it and the call degrades
    gracefully to the pre-3.3 three-way read (formed/rendered/proxy only) — every existing
    caller keeps working unchanged. Pass it to get the full four-way split (health, the
    pass gate, and any caller with a corpus root in hand should).

    *(3.2)* The authored state retired with the layer it named — the vouch dissolves into
    the form layer (§4.1: "the vouch rides the form"), so this enum (now four-valued) is
    the whole picture; the derived-editorial pair (`derived_editorial`) is orthogonal
    display data, not a state."""
    if corpus_root is not None:
        from . import shape as _shape

        resolved = _shape.governing_form(post, corpus_root)
        if resolved is not None and resolved[1] and not has_stored_rendering(post):
            return "terminal"
    if is_formed(post):
        return "formed"
    if has_stored_rendering(post):
        return "rendered"
    return "proxy"


# ---------- stub creation ---------- #


def stub_frontmatter(
    *,
    record_id: str,
    transport: str | list[str] | None = None,
    touch_id: str,
) -> dict[str, Any]:
    """Build a fresh stub-record frontmatter dict.

    `record_id` is the bare blake3 hex (becomes `id`). `transport` is alternative
    byte hashes (`<algo>:<hex>` or list); the primary blake3 lives on `id` and is NOT
    duplicated here. `touch_id` bootstraps the touch chain.

    *(3.1)* No `status` field — the record is born the artifact's proxy (§4.1), not a
    `stub` awaiting one; its state is derived, never stored.

    *(3.2)* No `title`/`description` either (spec §12.3.4) — the display pair is
    **derived** from role-marked attested and sidecar-lifted fields the same ingest just
    stamped (§4.2.3), so the proxy is presentable the moment it exists. The frontmatter
    pair survives only as an optional deliberate override, written later by an authoring
    pass — never at birth.

    The caller is responsible for emitting the artifact + first origin blocks via
    `set_artifact_block()` and `append_origin_block()`.
    """
    fm: dict[str, Any] = {"id": record_id}
    if transport:
        fm["transport"] = transport
    fm["touch"] = touch_id
    return fm
