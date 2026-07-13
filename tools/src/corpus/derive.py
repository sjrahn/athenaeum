"""Body derivation — the 3.0 `body` op (§6.2) and the shared drafter-run core.

The 2.x draft stage's content extraction is now a **derivation op**: a pure function of
(artifact x schemas x op version) that produces the faithful mechanical body markdown the
drafter used to store. `build_content_zone` runs the matching mime drafter into a fresh
`recordbuild.Build` (the SAME construction path draft / compile use), returning both the
Build (whose content zone is the derived body) and the drafter's metadata result (the
attested facts — artifact fields, manifest embeds, issues, sidecar enrichment). Two
consumers split off it:

- **ingest attestation** (§8.1) applies the metadata result to the stub and discards the
  body (derived on demand);
- **the `body` op** (`corpus body` / `corpus://<hash>?body`) emits the Build's content zone;
- **`derive_record`** (the transitional `corpus draft`) applies the metadata AND stores the
  body, as 2.x did.

Keeping one run means all three see byte-identical extraction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import frontmatter

from corpus import containment, local_code, mime, recordbuild, records, schemas
from corpus import draft as draft_pkg
from corpus.draft import DrafterResult


class DeriveError(RuntimeError):
    """A record cannot be derived (no mime schema / no drafter)."""


def resolve_drafter(corpus_root: Path, media_type: str):
    """Return `(drafter, strategy, mime_schema_id, mt_schema)` for `media_type`, loading the
    corpus's own local drafter modules first. Raises `DeriveError` when no schema/drafter
    resolves. A mime schema MAY name a general draft `strategy` (overlay-driven — e.g.
    `zip-manifest`), which decouples drafter choice from the schema id; absent one, dispatch
    by schema id."""
    if not media_type:
        raise DeriveError("record has no `<!--artifact <mime>-->` block (re-stub first?).")
    mt_schema = schemas.load_mime_schema(corpus_root, media_type)
    if not mt_schema:
        raise DeriveError(f"no mime schema for {media_type!r}.")
    mime_schema_id = schemas.mime_schema_id_for(corpus_root, media_type)
    if not mime_schema_id:
        raise DeriveError(f"could not resolve mime schema id for {media_type!r}.")
    # Import the corpus's own local drafter modules so they self-register before dispatch.
    local_code.load_corpus_modules(corpus_root, "drafters")
    strategy = str((mt_schema.get("draft") or {}).get("strategy") or "").strip()
    if strategy:
        drafter = draft_pkg.get_strategy_drafter(strategy)
        if drafter is None:
            raise DeriveError(
                f"mime schema {mime_schema_id!r} declares draft strategy {strategy!r}, "
                f"but no drafter is registered for it."
            )
    else:
        drafter = draft_pkg.get_drafter(mime_schema_id)
        if drafter is None:
            raise DeriveError(f"no drafter registered for mime schema id {mime_schema_id!r}.")
    return drafter, strategy, mime_schema_id, mt_schema


def build_content_zone(
    post: frontmatter.Post,
    corpus_root: Path,
    *,
    fingerprint_cli: bool | None = None,
    messages: list[int] | None = None,
) -> tuple[recordbuild.Build, DrafterResult, dict[str, Any], Path, str]:
    """Run the matching mime drafter against `post`'s retained artifact into a fresh Build.

    Returns `(build, result, mt_schema, binary_file, mime_schema_id)`:
    - `build` — a `recordbuild.Build` seeded from `post`; its content zone (`build.blocks`)
      is the derived body (empty for a `manifest`/non-`body-draft` schema).
    - `result` — the drafter's metadata-zone `DrafterResult` (the attested facts).

    Pure over the artifact bytes + schemas; does NOT emit, apply, persist, or change status.
    Raises `DeriveError` / `ArtifactMissing`."""
    media_type = records.media_type_for(post)
    drafter, strategy, mime_schema_id, mt_schema = resolve_drafter(corpus_root, media_type)
    record_id = str(post.metadata.get("id") or "")

    # Containment-aware byte access (§2/§12.9): a promoted member drafts from the bytes
    # streamed out of its container just as a standalone record drafts from `artifacts/`.
    binary_file = containment.ensure_local_bytes(
        corpus_root, record_id, mime.extension_for(media_type)
    )

    canonical_algo = (mt_schema.get("canonical_strategy") or {}).get("algo")
    build = recordbuild.begin_from_post(post, corpus_root)
    fingerprint = schemas.resolve_fingerprint(corpus_root, media_type, post, fingerprint_cli)
    drafter_kwargs: dict[str, Any] = dict(
        build=build,
        corpus_root=corpus_root,
        record_id=record_id,
        record_metadata=post.metadata,
        canonical_algo=canonical_algo,
        fingerprint=fingerprint,
    )
    if strategy:
        drafter_kwargs["mime_schema"] = mt_schema
        if strategy == "mbox-manifest":
            drafter_kwargs["messages"] = messages
    result = drafter(binary_file, **drafter_kwargs)
    return build, result, mt_schema, binary_file, mime_schema_id


def produces_body(mt_schema: dict[str, Any]) -> bool:
    """Whether this schema's drafter builds a content-zone body (a `body-draft`/`work`
    schema) as opposed to a manifest whose members are embeds (empty content zone)."""
    return str(mt_schema.get("mode", "body-draft")).lower() == "body-draft"


def derive_body(
    post: frontmatter.Post,
    corpus_root: Path,
    *,
    fingerprint_cli: bool | None = None,
    messages: list[int] | None = None,
) -> str:
    """The `body` derivation op (§6.2): the record's faithful mechanical body markdown —
    what the 2.x drafter stored — derived on demand from the artifact. Empty for a manifest
    record (its members are embeds, not a body). Runs on a scratch copy of `post` so the
    live record is never mutated. Raises `DeriveError` / `ArtifactMissing`."""
    from corpus import segments

    scratch = frontmatter.Post(post.content or "", **dict(post.metadata))
    scratch.metadata["_embeds"] = []
    scratch.metadata["_contexts"] = []
    build, _result, mt_schema, _bin, _id = build_content_zone(
        scratch, corpus_root, fingerprint_cli=fingerprint_cli, messages=messages
    )
    if not produces_body(mt_schema):
        return ""
    return segments.emit(build.blocks)
