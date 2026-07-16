"""The re-stub operation per spec/corpus.md §8.4.

Returns a record to its **attested baseline** (spec §4.1), ready for fresh attestation.
Everything **derived from a schema decision** is discarded. Everything **tied to the bytes
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

- `title`, `description` → empty; `canonical`; `perceptual` (record-scope).
- The artifact block's body fields; all classify blocks; all embed blocks; all
  section/segment blocks; all issue blocks.
- Body content zone → empty. *(3.1)* No `status` to reset — the record's derived state
  (§4.1) falls back to `proxy` on its own once the vouch and any rendering are cleared.

This port supports only the spec-v1.0 → spec-v1.0 re-stub. The reference's
v0.2/v0.3 migration paths (CarbonAi-specific debt) are not carried.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from . import paths, records, touches

_RESTUB_MODULE = "re-stub"


def restub_post(post: frontmatter.Post, *, touch_chain: list[str]) -> frontmatter.Post:
    """Build a fresh stub-shaped Post from `post` (in memory, no write), preserving the
    byte-tied + provenance fields and clearing everything schema-derived. `touch_chain`
    is the new `touch[]` to seed. `restub()` writes the result with the re-stub touch
    appended; `corpus redraft` passes the chain collapsed to the original ingest entry
    so a clean re-derive of an unchanged record is byte-identical (idempotent)."""
    metadata = dict(post.metadata)

    record_id = str(metadata.get("id") or "")
    if not record_id:
        raise ValueError("record has no `id`")

    artifact = metadata.get("_artifact") or {}
    mime = (artifact.get("mime") or "").strip()
    if not mime:
        raise ValueError("record has no `<!--artifact-->` block; cannot re-stub.")

    origin_blocks = list(metadata.get("_origins") or [])
    if not origin_blocks:
        raise ValueError(
            "record has no origin URIs to preserve. Author an origin manually before re-stub."
        )

    visibility = metadata.get("visibility")
    transport_value = metadata.get("transport")

    seed = touch_chain[0] if touch_chain else touches.script_identifier(_RESTUB_MODULE)
    fm = records.stub_frontmatter(
        record_id=record_id,
        transport=transport_value,
        touch_id=seed,
        description="",
    )
    if visibility:
        fm["visibility"] = str(visibility)
    if touch_chain:
        fm["touch"] = list(touch_chain)

    new_post = frontmatter.Post(content="", **fm)
    # The artifact block's body fields are all schema-derived → reset; the next draft
    # re-derives them from the bytes (including any namespaced `*_title` candidate).
    records.set_artifact_block(new_post, mime=mime, fields={})
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
    return new_post


def restub(record_file: Path) -> str:
    """Re-stub the record at `record_file` on disk. Returns the record's id.

    Preserves the byte-tied + provenance fields, writes a fresh stub-shaped record
    (frontmatter + artifact block + origin blocks), and clears the content zone. The
    touch chain collapses to the original ingest entry plus a re-stub touch (spec §8.4).
    """
    post = records.load(record_file)
    chain = touches.touch_list(post)
    restub_touch = touches.script_identifier(_RESTUB_MODULE)
    new_chain = [chain[0], restub_touch] if chain else [restub_touch]
    new_post = restub_post(post, touch_chain=new_chain)
    records.dump(new_post, record_file)
    return str(new_post.metadata.get("id") or "")


def restub_by_id(corpus_root: Path, record_id: str) -> str:
    """Convenience: re-stub the record at `records/<shard>/<id>.md`."""
    record_file = paths.record_path(corpus_root, record_id)
    if not record_file.is_file():
        raise FileNotFoundError(record_file)
    return restub(record_file)
