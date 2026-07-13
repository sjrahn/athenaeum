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

import sys
from pathlib import Path
from typing import Any

import frontmatter

from corpus import containment, local_code, mime, recordbuild, records, schemas
from corpus import draft as draft_pkg
from corpus.draft import DrafterResult


class DeriveError(RuntimeError):
    """A record cannot be derived (no mime schema / no drafter)."""


def _pkg_version() -> str:
    from corpus import __version__

    return __version__


def apply_drafter_result(
    post: frontmatter.Post,
    result: dict[str, Any],
    mime_schema_id: str,
    corpus_root: Path,
) -> None:
    """Merge a drafter's metadata-zone result (the **attested facts**) onto `post`: the
    artifact-block fields, metadata-zone embeds, source-enrichment origin fields, the
    producer-declared overlay id, origin-alias URLs, and the mechanical issues. Does NOT
    touch the content zone (the body is the drafter's Build / the `body` op) — this is the
    attestation half of the split (§12.4)."""
    # Artifact-block fields (merge drafter-supplied fields; refined title overrides).
    artifact = records.artifact_block(post) or {
        "mime": records.media_type_for(post),
        "fields": {},
    }
    artifact_fields = dict(artifact.get("fields") or {})
    for key, value in (result.get("fields") or {}).items():
        artifact_fields[key] = value
    records.set_artifact_block(post, mime=artifact["mime"], fields=artifact_fields)

    # Frontmatter description: set only when still empty (don't clobber a human edit).
    desc = result.get("description")
    if desc and not str(post.metadata.get("description") or "").strip():
        post.metadata["description"] = str(desc)

    # canonical (from the mime schema's canonical_strategy): intentionally NOT persisted
    # (§7.1 status note — the value corrupts cross-URL dedup on text-empty PDFs; disabled).
    _ = result.get("canonical")  # discarded

    # Metadata-zone embeds (reconciliation #1).
    for emb in result.get("embeds") or []:
        records.append_embed_block(
            post,
            media_type=emb["media_type"],
            address=emb["address"],
            transport=emb["transport"],
            fields=emb.get("fields") or None,
        )

    # Source-provided enrichment fields (e.g. a yt-dlp `ytdlp_*` set) → the origin block, not
    # the artifact block (where-it-came-from metadata, §7.2).
    records.merge_origin_fields(post, result.get("origin_fields") or {})

    # Producer-declared overlay id (an injected `corpus-origin-schema` meta) → stamp the origin
    # block opener (the binding for a uri-less origin, §7.2).
    if schema_id := result.get("origin_schema"):
        records.set_origin_schema_id(post, str(schema_id))

    # Origin-alias URLs the drafter discovered (canonical / post-redirect final) → the origin
    # block's uri: list, not the artifact block (§7.2).
    for alias in result.get("origin_uri_aliases") or []:
        records.add_origin_uri_alias(post, str(alias), corpus_root=corpus_root)

    # Drafter-detected issues (spec-shaped). Skip a malformed dict missing `severity`.
    for issue in result.get("issues") or []:
        severity = issue.get("severity")
        if not severity:
            print(f"  WARN: drafter issue missing `severity`, skipped: {issue!r}", file=sys.stderr)
            continue
        records.append_issue_block(
            post,
            id=str(issue.get("id") or "unknown"),
            subtype=issue.get("subtype"),
            severity=str(severity),
            resolution=str(issue.get("resolution", "open")),
            detector=str(
                issue.get("detector") or f"corpus.draft.{mime_schema_id}@{_pkg_version()}"
            ),
            address=issue.get("address"),
            fields=issue.get("fields") or None,
        )


def _is_drafter_issue(ctx: dict) -> bool:
    """A mechanical drafter-emitted issue — the attested layer's issue half. Identified by
    the `corpus.draft.*` detector family (a capturer's issue detector is preserved)."""
    if (ctx.get("namespace") or "") != "issue":
        return False
    detector = str((ctx.get("fields") or {}).get("detector") or "")
    return detector.startswith("corpus.draft.")


def strip_attested_layer(post: frontmatter.Post) -> dict[str, str]:
    """Clear the attested layer of `post` in place — embeds, the `corpus.draft.*` issues, and
    the artifact block's extended fields (the opener MIME stays; it is byte-intrinsic) — and
    return the authored embed `description:`s keyed by transport hash so a re-attestation can
    carry them forward. Makes re-attestation and the transitional draft idempotent: attesting
    an already-attested record does not double its embeds/issues."""
    authored_desc: dict[str, str] = {}
    for e in records.iter_embed_blocks(post):
        d = (e.get("fields") or {}).get("description")
        if d:
            authored_desc[str(e.get("transport"))] = str(d)
    post.metadata["_embeds"] = []
    post.metadata["_contexts"] = [
        c for c in (post.metadata.get("_contexts") or []) if not _is_drafter_issue(c)
    ]
    art = records.artifact_block(post) or {}
    records.set_artifact_block(post, mime=str(art.get("mime") or ""), fields={})
    return authored_desc


def reattach_descriptions(post: frontmatter.Post, authored_desc: dict[str, str]) -> None:
    """Re-attach authored embed `description:`s (from `strip_attested_layer`) onto the
    re-derived embeds, matched by transport hash."""
    for e in post.metadata.get("_embeds") or []:
        d = authored_desc.get(str(e.get("transport")))
        if d and "description" not in (e.get("fields") or {}):
            e.setdefault("fields", {})["description"] = d


def attest(
    post: frontmatter.Post,
    corpus_root: Path,
    *,
    fingerprint_cli: bool | None = None,
    strip: bool = False,
    messages: list[int] | None = None,
) -> str:
    """Derive + apply the **attested layer** onto `post` in place (§8.1, §12.4): run the mime
    drafter and apply its metadata result (artifact fields, embeds, drafter issues), NEVER
    storing the body (the `body` op derives it on demand) and NEVER changing status. Returns
    the mime schema id.

    `strip=True` (re-attest, §12.4.6) first clears the current attested layer — embeds, the
    `corpus.draft.*` issues, and the artifact block's extended fields — and carries authored
    embed `description:`s forward by transport, so the authored layer survives. `strip=False`
    (a fresh ingest stub) applies onto a record that carries none yet.

    `messages` are the mbox selective declaration (§12.11, the re-homed `--messages`): the
    1-indexed ordinals to manifest as `message/rfc822` embeds; None reads the record's already-
    declared set. The mbox manifest is EXEMPT from the strip — it is cumulative by design (its
    result is the delta over the already-declared embeds), so stripping would drop them.
    Raises `DeriveError` / `ArtifactMissing`."""
    from corpus.draft import mbox_manifest

    media_type = records.media_type_for(post)
    mt = schemas.load_mime_schema(corpus_root, media_type) or {}
    is_mbox = str((mt.get("draft") or {}).get("strategy") or "") == "mbox-manifest"
    eff_messages = (
        messages if messages is not None else (mbox_manifest.declared_ordinals(post) or None)
    )

    authored_desc = strip_attested_layer(post) if (strip and not is_mbox) else {}
    _build, result, _mt, _bin, mime_schema_id = build_content_zone(
        post, corpus_root, fingerprint_cli=fingerprint_cli, messages=eff_messages
    )
    apply_drafter_result(post, result, mime_schema_id, corpus_root)
    reattach_descriptions(post, authored_desc)
    return mime_schema_id or ""


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
