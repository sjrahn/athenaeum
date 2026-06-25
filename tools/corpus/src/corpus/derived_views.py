"""Derived views per spec-corpus.md §9.

Cross-cutting aggregates over a record's body blocks (and the touch chain), computed
on demand. None are persisted.

The views:

- `classifications` (§9.1) — walks artifact + origin + classify blocks.
- `context` (§4.3.3) — walks context blocks across all annotation namespaces.
- `issues` (§9.2) — the `issue`-namespace projection of `context`.
- `uris` (§9.3) — origin URIs + semantic_type:uri-tagged schema fields.
- `timeline` (§9.4) — origin snapshots + semantic_type:timestamp-tagged fields.
- `identifiers` (§9.5) — semantic_type:identifier-tagged fields + the record's id.
- `concepts` (§9.7) — the `concept`-namespace projection of `context`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import frontmatter

from . import records, schemas
from . import urls as urlcanon


def _iter_tagged_fields(
    corpus_root: Path,
    post: frontmatter.Post,
    target_semantic: str,
) -> Iterator[tuple[str, Any]]:
    """Yield `(field_name, value)` for every body-block field declaration tagged
    `semantic_type: <target_semantic>` across the matching mime schema, every origin
    schema, and every classify-block schema (namespace + optional subclass).
    """
    seen_fields: set[str] = set()

    # Mime schema fields — walk the artifact block's fields against the matching
    # mime schema declaration.
    mime = records.media_type_for(post)
    if mime:
        mt_schema = schemas.load_mime_schema(corpus_root, mime)
        if mt_schema:
            artifact = records.artifact_block(post) or {}
            artifact_fields = artifact.get("fields") or {}
            yield from _walk_schema_fields(
                mt_schema, artifact_fields, target_semantic, seen_fields
            )

    # Origin schemas — walk each qualified origin block.
    for origin in records.iter_origin_blocks(post):
        id_ = origin.get("id")
        if not id_:
            continue
        origin_schema = schemas.load_origin_overlay_by_id(corpus_root, id_)
        if origin_schema is None:
            continue
        block_fields = origin.get("fields") or {}
        yield from _walk_schema_fields(
            origin_schema, block_fields, target_semantic, seen_fields
        )

    # Classify schemas — walk each classify block. Schema sits at one file
    # (namespace) or two (namespace + subclass when `id != namespace`).
    for classify in records.iter_classify_blocks(post):
        namespace = classify.get("namespace") or ""
        cid = classify.get("id") or ""
        ns_schema = schemas.load_classification_schema(corpus_root, namespace)
        if ns_schema is None:
            continue
        block_fields = classify.get("fields") or {}
        yield from _walk_schema_fields(
            ns_schema, block_fields, target_semantic, seen_fields
        )
        if cid and cid != namespace:
            sub_schema = schemas.load_classification_subclass(corpus_root, namespace, cid)
            if isinstance(sub_schema, dict):
                yield from _walk_schema_fields(
                    sub_schema, block_fields, target_semantic, seen_fields
                )


def _walk_schema_fields(
    schema: dict[str, Any],
    block_fields: dict[str, Any],
    target_semantic: str,
    seen_fields: set[str],
) -> Iterator[tuple[str, Any]]:
    """Yield matching tagged fields whose values appear in the block's body fields."""
    ext = schema.get("extended_fields") or {}
    for field_name, decl in ext.items():
        if field_name in seen_fields:
            continue
        if not isinstance(decl, dict):
            continue
        if str(decl.get("semantic_type", "")).lower() != target_semantic.lower():
            continue
        if field_name not in block_fields:
            # Declared with the target semantic but not populated in THIS block — don't
            # mark it seen, or a later block (origin/classify) that does populate the same
            # field name would be silently suppressed.
            continue
        seen_fields.add(field_name)
        yield field_name, block_fields[field_name]


def _flatten(value: Any) -> list[Any]:
    """Treat a list as itself, anything else as a one-element list."""
    if isinstance(value, list):
        return list(value)
    if value is None:
        return []
    return [value]


def _canonicalize(uri: str) -> str:
    try:
        return urlcanon.normalize(uri)
    except Exception:
        return uri


# ---------- the five views ---------- #


def classifications(post: frontmatter.Post) -> list[str]:
    """§9.1 — derive `classifications[]` from body blocks. Pure post-walk."""
    return records.derived_classifications(post)


def context(post: frontmatter.Post) -> list[dict[str, Any]]:
    """§4.3.3 — derive the `context[]` view from `<!--context-->` blocks.

    Returns structured records `{namespace, id, subtype?, ...fields}` across every
    annotation namespace (issue, reference, note, …). `issues()` is the `issue`-namespace
    projection of this view.
    """
    out: list[dict[str, Any]] = []
    for ctx in records.iter_context_blocks(post):
        entry: dict[str, Any] = {
            "namespace": ctx.get("namespace"),
            "id": ctx.get("id"),
        }
        if ctx.get("subtype"):
            entry["subtype"] = ctx["subtype"]
        for k, v in (ctx.get("fields") or {}).items():
            entry[k] = v
        out.append(entry)
    return out


def issues(post: frontmatter.Post) -> list[dict[str, Any]]:
    """§9.2 — derive `issues[]`: the `issue`-namespace projection of the context view.

    Returns a list of structured records `{id, subtype?, ...fields}` (fields include
    severity, resolution, detector, optional address + id-specific extras).
    """
    out: list[dict[str, Any]] = []
    for issue in records.iter_issue_blocks(post):
        entry: dict[str, Any] = {"id": issue.get("id")}
        if issue.get("subtype"):
            entry["subtype"] = issue["subtype"]
        for k, v in (issue.get("fields") or {}).items():
            entry[k] = v
        out.append(entry)
    return out


def concepts(post: frontmatter.Post) -> list[dict[str, Any]]:
    """§9.7 — derive `concepts[]`: the `concept`-namespace projection of the context view.

    Each entry is the concept block's fields — the identity ladder (`label`, `url`, `concept`)
    plus the optional anchor (`address`, `quote`, `occurrence`). Concepts reference an external
    local knowledge base (Wikipedia/Wikidata) by id/URL, not a corpus record (spec §4.3.3.4):
    a segment-scoped entry (with `address`) is a mention; a record-scoped entry is aboutness.
    """
    out: list[dict[str, Any]] = []
    for concept in records.iter_concept_blocks(post):
        entry: dict[str, Any] = {}
        if concept.get("subtype"):
            entry["subtype"] = concept["subtype"]
        for k, v in (concept.get("fields") or {}).items():
            entry[k] = v
        out.append(entry)
    return out


def references(post: frontmatter.Post) -> list[dict[str, Any]]:
    """§9.9 — derive `references[]`: the `reference`-namespace projection of the context
    view (§4.3.3.3) — the sibling of `issues` (§9.2) and `concepts` (§9.7).

    Each entry is the reference block's fields — the citation ladder (`attribution_text`,
    `source_url`, `source_uri`), the optional anchor (`address`, `quote`, `occurrence`),
    `provenance`, and (on mechanical, overlay-declared references) `role`. The resolved
    `source_uri` is the directional edge to the cited/depended-on record; the reverse is a
    corpus-wide read, not indexed here (spec §9.9 / §11).
    """
    out: list[dict[str, Any]] = []
    for reference in records.iter_reference_blocks(post):
        entry: dict[str, Any] = {}
        if reference.get("subtype"):
            entry["subtype"] = reference["subtype"]
        for k, v in (reference.get("fields") or {}).items():
            entry[k] = v
        out.append(entry)
    return out


def uris(corpus_root: Path, post: frontmatter.Post) -> list[str]:
    """§9.3 — every origin block's uri + every semantic_type:uri-tagged field,
    deduplicated by URL canonicalization."""
    seen: set[str] = set()
    out: list[str] = []

    for origin in records.iter_origin_blocks(post):
        fields = origin.get("fields") or {}
        for u in _flatten(fields.get("uri")):
            s = str(u).strip()
            if not s:
                continue
            key = _canonicalize(s)
            if key not in seen:
                seen.add(key)
                out.append(s)

    for _, value in _iter_tagged_fields(corpus_root, post, "uri"):
        for v in _flatten(value):
            s = str(v).strip()
            if not s:
                continue
            key = _canonicalize(s)
            if key not in seen:
                seen.add(key)
                out.append(s)
    return out


def timeline(
    corpus_root: Path, post: frontmatter.Post
) -> list[tuple[str, str, Any]]:
    """§9.4 — every origin block's `snapshot:` + every semantic_type:timestamp-tagged
    field. Returns `(timestamp, source_field, value)` tuples sorted ascending.
    """
    rows: list[tuple[str, str, Any]] = []

    for origin in records.iter_origin_blocks(post):
        fields = origin.get("fields") or {}
        snapshot = fields.get("snapshot")
        if not snapshot:
            continue
        rows.append((str(snapshot), "origin.snapshot", snapshot))

    for field_name, value in _iter_tagged_fields(corpus_root, post, "timestamp"):
        for v in _flatten(value):
            if v is None or str(v).strip() == "":
                continue
            rows.append((str(v), field_name, v))

    rows.sort(key=lambda r: r[0])
    return rows


def identifiers(
    corpus_root: Path, post: frontmatter.Post
) -> list[tuple[str, Any]]:
    """§9.5 — every semantic_type:identifier-tagged field plus the record's `id`.

    Returns `(source_field, value)` tuples (`id` first, then schema walk order).
    """
    out: list[tuple[str, Any]] = []
    record_id = post.metadata.get("id")
    if record_id:
        out.append(("id", record_id))
    for field_name, value in _iter_tagged_fields(corpus_root, post, "identifier"):
        for v in _flatten(value):
            if v is None or str(v).strip() == "":
                continue
            out.append((field_name, v))
    return out
