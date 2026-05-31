"""The re-stub operation per spec-corpus.md §8.4.

Returns a record to `status: stub`, ready for a fresh draft pass. Everything
**derived from a schema decision** is discarded. Everything **tied to the bytes
themselves or to provenance** is preserved.

What survives:

- `id`, `transport` — byte-intrinsic hashes.
- The artifact block's opener (the MIME).
- All `<!--origin-->` blocks VERBATIM — overlay qualifier (id/subtype), the
  universal `uri:` / `snapshot:`, and any overlay-declared extended fields. Origin
  is provenance; re-stub never discards provenance.
- `visibility`.
- `touch[]` collapses to its first entry (the original ingest touch) plus the
  re-stub touch appended.

What is reset:

- `description` → empty; `canonical`; `perceptual` (record-scope).
- The artifact block's body fields; all classify blocks; all embed blocks; all
  section/segment blocks; all issue blocks.
- `status` → `stub`; body content zone → empty.

This port supports only the spec-v1.0 → spec-v1.0 re-stub. The reference's
v0.2/v0.3 migration paths (CarbonAi-specific debt) are not carried.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import frontmatter

from . import paths, records, touches

_RESTUB_MODULE = "re-stub"


def restub(record_file: Path) -> str:
    """Re-stub the record at `record_file`. Returns the record's id.

    Reads the existing record via `records.load`, preserves the byte-tied and
    provenance fields, writes a fresh stub-shaped record (frontmatter + minimal
    body: artifact block + origin blocks), and clears the content zone.
    """
    post = records.load(record_file)
    metadata = dict(post.metadata)

    record_id = str(metadata.get("id") or "")
    if not record_id:
        raise ValueError(f"record at {record_file} has no `id`")

    artifact = metadata.get("_artifact") or {}
    mime = (artifact.get("mime") or "").strip()
    if not mime:
        raise ValueError(
            f"record at {record_file} has no `<!--artifact-->` block; cannot re-stub."
        )
    title = (artifact.get("fields") or {}).get("title") or ""

    origin_blocks = list(metadata.get("_origins") or [])
    if not origin_blocks:
        raise ValueError(
            f"record at {record_file} has no origin URIs to preserve. "
            f"Author an origin manually before re-stub."
        )

    visibility = metadata.get("visibility")
    transport_value = metadata.get("transport")

    existing_touch_chain = touches.touch_list(post)

    # Build the fresh stub.
    touch_id = touches.script_identifier(_RESTUB_MODULE)
    fm = records.stub_frontmatter(
        record_id=record_id,
        transport=transport_value,
        touch_id=touch_id,
        description="",
    )
    if visibility:
        fm["visibility"] = str(visibility)

    # Touch chain: keep the first existing entry (the original ingest touch),
    # plus the re-stub touch (spec §8.4).
    if existing_touch_chain:
        fm["touch"] = [existing_touch_chain[0], touch_id]

    new_post = frontmatter.Post(content="", **fm)
    artifact_fields: dict[str, Any] = {}
    if title:
        artifact_fields["title"] = str(title)
    records.set_artifact_block(new_post, mime=mime, fields=artifact_fields)
    for ob in origin_blocks:
        fields = ob.get("fields") or {}
        uri = fields.get("uri", "")
        snapshot = str(fields.get("snapshot", ""))
        extras = {k: v for k, v in fields.items() if k not in ("uri", "snapshot")}
        records.append_origin_block(
            new_post,
            uri=uri,
            snapshot=snapshot,
            schema_id=ob.get("id"),
            subtype=ob.get("subtype"),
            fields=extras or None,
        )

    records.dump(new_post, record_file)
    return record_id


def restub_by_id(corpus_root: Path, record_id: str) -> str:
    """Convenience: re-stub the record at `records/<shard>/<id>.md`."""
    record_file = paths.record_path(corpus_root, record_id)
    if not record_file.is_file():
        raise FileNotFoundError(record_file)
    return restub(record_file)
