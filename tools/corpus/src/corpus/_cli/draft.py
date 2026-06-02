"""Draft a single record from `stub` to `draft`.

Schema-driven routing:

1. Read the record's MIME from the `<!--artifact <mime>-->` opener and look up the
   matching mime schema.
2. Invoke the matching drafter (via the `corpus.draft.REGISTRY`, keyed on mime
   schema id).
3. Apply the drafter result: merge artifact-block fields, replace the content zone
   (when `mode: body-draft`), append metadata-zone embeds (reconciliation #1),
   append drafter-detected issues (spec-shaped, reconciliation #2), set `canonical:`
   if the mime schema declared a `canonical_strategy`.
4. Append a draft touch and flip status to `draft`.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from corpus import draft as draft_pkg
from corpus import mime, paths, records, schemas, segments, touches
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root
from corpus.store import ArtifactMissing, get_store


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Hash, hex prefix, or record file path.")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    record_id, record_file = paths.resolve_record(corpus_root, args.target)
    post = records.load(record_file)

    # `draft` is a stub→draft transition. Re-running it would append duplicate embed/issue
    # blocks (the metadata zone isn't reset here), so refuse a non-stub record and point at
    # the clean re-run path: `re-stub` (which collapses the body) then `draft`.
    status = str(post.metadata.get("status") or "").lower()
    if status and status != "stub":
        sys.exit(
            f"record status is {status!r}, not 'stub'; `corpus draft` only runs on a stub. "
            f"Run `corpus re-stub {args.target}` first to re-draft."
        )

    media_type = records.media_type_for(post)
    if not media_type:
        sys.exit(
            "record has no `<!--artifact <mime>-->` block (re-stub first?)."
        )
    mt_schema = schemas.load_mime_schema(corpus_root, media_type)
    if not mt_schema:
        sys.exit(f"no mime schema for {media_type!r}.")
    mime_schema_id = schemas.mime_schema_id_for(corpus_root, media_type)
    if not mime_schema_id:
        sys.exit(f"could not resolve mime schema id for {media_type!r}.")

    drafter = draft_pkg.get_drafter(mime_schema_id)
    if drafter is None:
        sys.exit(
            f"no drafter registered for mime schema id {mime_schema_id!r}. "
            f"P2 ships drafters for application/application_pdf and image/*. "
            f"HTML drafter lands in P2.7; others in later phases."
        )

    extension = mime.extension_for(media_type)
    store = get_store(corpus_root)
    try:
        binary_file = store.ensure_local(record_id, extension)
    except ArtifactMissing as exc:
        sys.exit(str(exc))

    # The mime schema owns the canonical-hash strategy; pass its algo to the drafter so a
    # corpus that overrides `canonical_strategy.algo` is honoured (drafters fall back to
    # their built-in default when this is None).
    canonical_algo = (mt_schema.get("canonical_strategy") or {}).get("algo")
    result = drafter(
        binary_file,
        corpus_root=corpus_root,
        record_id=record_id,
        record_metadata=post.metadata,
        canonical_algo=canonical_algo,
    )

    _apply_drafter_result(post, result, mt_schema, mime_schema_id)

    # Append draft touch + flip status.
    touch_module = "draft." + mime_schema_id  # e.g. draft.application/application_pdf
    touches.record_touch(post, touches.script_identifier(touch_module))
    post.metadata["status"] = "draft"

    # Cross-URL content dedup: if another record already holds this exact content (same
    # `canonical:` hash AND same embed set), fold THIS capture's URL(s) into that record
    # and drop this duplicate instead of keeping a second record (spec §7.2 — canonical /
    # alias URLs are one logical origin). This is what makes "the same aggregate page
    # reached by N different links" collapse to one record with N URLs. It depends on
    # capture-time chrome stripping: without it, per-page chrome perturbs the canonical
    # hash and the duplicates never match.
    dup = records.find_content_duplicate(post, record_id=record_id, corpus_root=corpus_root)
    if dup is not None:
        original_id, original_path = dup
        original = records.load(original_path)
        added = sum(
            records.add_origin_uri_alias(original, uri) for uri in records.iter_origin_uris(post)
        )
        records.dump(original, original_path)
        _discard_duplicate(corpus_root, record_id, record_file, extension)
        print(
            f"content-duplicate of {original_id[:12]}: merged {added} url(s) into it; "
            f"removed this record ({record_id[:12]})."
        )
        return 0

    records.dump(post, record_file)

    print(f"drafted: {record_file.relative_to(corpus_root)}")
    print(f"  status: {post.metadata['status']}")
    derived = records.derived_classifications(post)
    if derived:
        print(f"  derived classifications: {derived}")
    return 0


def _apply_drafter_result(
    post,
    result: dict[str, Any],
    mt_schema: dict[str, Any],
    mime_schema_id: str,
) -> None:
    """Merge a drafter's result onto `post`."""
    # Artifact-block fields (merge drafter-supplied fields; refined title overrides).
    artifact = records.artifact_block(post) or {
        "mime": records.media_type_for(post),
        "fields": {},
    }
    artifact_fields = dict(artifact.get("fields") or {})
    for key, value in (result.get("fields") or {}).items():
        artifact_fields[key] = value
    if title := result.get("title"):
        artifact_fields["title"] = title
    records.set_artifact_block(post, mime=artifact["mime"], fields=artifact_fields)

    # canonical (from mime schema's canonical_strategy).
    if canonical := result.get("canonical"):
        post.metadata["canonical"] = canonical

    # Metadata-zone embeds (reconciliation #1).
    for emb in result.get("embeds") or []:
        records.append_embed_block(
            post,
            media_type=emb["media_type"],
            address=emb["address"],
            transport=emb["transport"],
            fields=emb.get("fields") or None,
        )

    # Origin-alias URLs the drafter discovered (canonical / post-redirect final) — fold
    # into the origin block's uri: list, not the artifact block (spec §7.2).
    for alias in result.get("origin_uri_aliases") or []:
        records.add_origin_uri_alias(post, str(alias))

    # Content-zone body — body-draft schemas REPLACE the content zone (spec §7.1).
    mode = str(mt_schema.get("mode", "body-draft")).lower()
    if mode == "body-draft" and (segs := result.get("segments")) is not None:
        post.content = segments.emit(segs)

    # Drafter-detected issues (spec-shaped, reconciliation #2). Skip a malformed dict
    # missing the required `severity` rather than crashing the whole draft — parity with
    # the ingest replay path's guard.
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
                issue.get("detector")
                or f"corpus.draft.{mime_schema_id}@{_pkg_version()}"
            ),
            address=issue.get("address"),
            fields=issue.get("fields") or None,
        )


def _discard_duplicate(corpus_root, record_id: str, record_file, extension: str) -> None:
    """Remove a content-duplicate record's `.md` + its local artifact after its URL was
    folded into the original. Best-effort on the artifact (a remote store keeps its own
    copy; the local capture is the orphan we clean). The artifacts dir is regenerable."""
    record_file.unlink(missing_ok=True)
    artifact = corpus_root / "artifacts" / paths.shard(record_id) / f"{record_id}.{extension}"
    artifact.unlink(missing_ok=True)


def _pkg_version() -> str:
    from corpus import __version__

    return __version__
