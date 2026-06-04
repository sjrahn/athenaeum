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

from corpus import content_hash, mime, paths, recordbuild, records, schemas, touches
from corpus import draft as draft_pkg
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root
from corpus.store import ArtifactMissing, get_store


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Hash, hex prefix, or record file path.")
    parser.add_argument(
        "--fingerprint",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "force perceptual fingerprinting on (--fingerprint) or off "
            "(--no-fingerprint), overriding the schema `fingerprint` knob. Default "
            "(unset): the schema decides — off unless a mime/composite schema opts in. "
            "Algorithm selection is schema-only (e.g. `fingerprint: dhash`)."
        ),
    )
    add_corpus_root_arg(parser)


class DraftError(RuntimeError):
    """A record cannot be drafted (no mime schema / no drafter)."""


def derive_record(
    post,
    corpus_root,
    *,
    fingerprint_cli: bool | None = None,
) -> None:
    """Re-derive `post`'s draft content from its retained artifact, **in place**: resolve
    the mime schema + drafter, build the content zone through the recordbuild ops, apply
    the metadata-zone result, emit + grammar-validate, apply the per-host canonical
    content-scoping override, append the draft touch, and flip status to `draft`. No
    dedup and no write — the caller owns those. `post` must be a stub. The shared draft
    core of `corpus draft` and `corpus redraft`. Raises `DraftError` (missing schema /
    drafter) or `ArtifactMissing` (artifact not local)."""
    record_id = str(post.metadata.get("id") or "")
    media_type = records.media_type_for(post)
    if not media_type:
        raise DraftError("record has no `<!--artifact <mime>-->` block (re-stub first?).")
    mt_schema = schemas.load_mime_schema(corpus_root, media_type)
    if not mt_schema:
        raise DraftError(f"no mime schema for {media_type!r}.")
    mime_schema_id = schemas.mime_schema_id_for(corpus_root, media_type)
    if not mime_schema_id:
        raise DraftError(f"could not resolve mime schema id for {media_type!r}.")
    drafter = draft_pkg.get_drafter(mime_schema_id)
    if drafter is None:
        raise DraftError(f"no drafter registered for mime schema id {mime_schema_id!r}.")

    binary_file = get_store(corpus_root).ensure_local(record_id, mime.extension_for(media_type))

    # The mime schema owns the canonical-hash strategy; pass its algo to the drafter so a
    # corpus that overrides `canonical_strategy.algo` is honoured (drafters fall back to
    # their built-in default when this is None).
    canonical_algo = (mt_schema.get("canonical_strategy") or {}).get("algo")
    # One construction path: the drafter populates a `Build` (content zone via the
    # recordbuild ops — the same path `compile` replays from a manifest), and we apply
    # the metadata-zone result + `finish` emits/validates.
    build = recordbuild.begin_from_post(post, corpus_root)
    # Whether (and with which algorithm) to compute perceptual fingerprints: CLI
    # override > composite classification > mime schema > off (spec §7.2). The drafter
    # resolves the per-atom algorithms from this knob via `fingerprint.algos_for_atom`.
    fingerprint = schemas.resolve_fingerprint(corpus_root, media_type, post, fingerprint_cli)
    result = drafter(
        binary_file,
        build=build,
        corpus_root=corpus_root,
        record_id=record_id,
        record_metadata=post.metadata,
        canonical_algo=canonical_algo,
        fingerprint=fingerprint,
    )

    _apply_drafter_result(post, result, mime_schema_id, corpus_root)

    # Emit the content zone the drafter built on the Build — body-draft schemas only
    # (spec §7.1). `finish` re-parses to surface grammar errors before any write.
    if str(mt_schema.get("mode", "body-draft")).lower() == "body-draft":
        recordbuild.finish(build)

    # Opt-in per-host canonical content-scoping: if the record's origin host declares a
    # `canonical.content_selector` in its overlay, recompute the canonical hash over just
    # that content region, overriding the drafter's whole-document hash. This makes the
    # same article reached by different links (different title/breadcrumb framing) share a
    # canonical → collapse via content-dedup. Absent the overlay section, the drafter's
    # whole-document canonical stands (no behaviour change for other corpora).
    if canonical_algo and post.metadata.get("canonical"):
        from corpus.capture import recipes

        selector = recipes.canonical_content_selector_for_url(
            corpus_root, records.primary_origin_uri(post)
        )
        if selector:
            post.metadata["canonical"] = records.format_hash(
                canonical_algo.split("-", 1)[0],
                content_hash.compute(canonical_algo, binary_file, content_selector=selector),
            )

    # Append draft touch + flip status.
    touches.record_touch(post, touches.script_identifier("draft." + mime_schema_id))
    post.metadata["status"] = "draft"


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

    try:
        derive_record(post, corpus_root, fingerprint_cli=getattr(args, "fingerprint", None))
    except (DraftError, ArtifactMissing) as exc:
        sys.exit(str(exc))

    extension = mime.extension_for(records.media_type_for(post))

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
            records.add_origin_uri_alias(original, uri, corpus_root=corpus_root)
            for uri in records.iter_origin_uris(post)
        )
        records.dump(original, original_path)
        _discard_duplicate(corpus_root, record_id, record_file, extension)
        _cleanup_enrichment(corpus_root, record_id)
        print(
            f"content-duplicate of {original_id[:12]}: merged {added} url(s) into it; "
            f"removed this record ({record_id[:12]})."
        )
        return 0

    records.dump(post, record_file)
    _cleanup_enrichment(corpus_root, record_id)

    print(f"drafted: {record_file.relative_to(corpus_root)}")
    print(f"  status: {post.metadata['status']}")
    derived = records.derived_classifications(post)
    if derived:
        print(f"  derived classifications: {derived}")
    return 0


def _apply_drafter_result(
    post,
    result: dict[str, Any],
    mime_schema_id: str,
    corpus_root,
) -> None:
    """Merge a drafter's metadata-zone result onto `post` (the content zone is built
    on the Build via `recordbuild.add_blocks` + `finish`)."""
    # Artifact-block fields (merge drafter-supplied fields; refined title overrides).
    artifact = records.artifact_block(post) or {
        "mime": records.media_type_for(post),
        "fields": {},
    }
    artifact_fields = dict(artifact.get("fields") or {})
    for key, value in (result.get("fields") or {}).items():
        artifact_fields[key] = value
    # A drafter-extracted title rides on the artifact block as a format-namespaced field
    # (html_title / pdf_title / docx_title / workbook_title) inside `fields` above — there
    # is no generic `title`. The normalizer picks among those `*_title` candidates (and the
    # origin's `ytdlp_title`) to author the frontmatter `title`.
    records.set_artifact_block(post, mime=artifact["mime"], fields=artifact_fields)

    # Frontmatter description: set only when still empty (don't clobber a human edit).
    if (desc := result.get("description")) and not str(post.metadata.get("description") or "").strip():
        post.metadata["description"] = str(desc)

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

    # Source-provided enrichment fields (e.g. a yt-dlp capture's `ytdlp_*` metadata) →
    # the origin block, not the artifact block (the artifact block is for facts about the
    # primary-artifact bytes; this is where-it-came-from metadata — spec §7.2).
    records.merge_origin_fields(post, result.get("origin_fields") or {})

    # Origin-alias URLs the drafter discovered (canonical / post-redirect final) — fold
    # into the origin block's uri: list, not the artifact block (spec §7.2).
    for alias in result.get("origin_uri_aliases") or []:
        records.add_origin_uri_alias(post, str(alias), corpus_root=corpus_root)

    # The content zone is built by the drafter on the Build (via `recordbuild.add_blocks`)
    # and emitted by `recordbuild.finish` in `run()` — not here.

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


def _cleanup_enrichment(corpus_root, record_id: str) -> None:
    """Delete the record's draft-time enrichment sidecars from `capture/` once the draft
    has consumed them (the yt-dlp `.info.json`, and any `<hash>.*` enrichment a capturer
    staged). Enrichment is one-shot — not persisted past draft; the extracted fields and
    segments already live in the record. Best-effort; `capture/` is staging-only."""
    capture_dir = corpus_root / "capture"
    if not capture_dir.is_dir():
        return
    for p in capture_dir.glob(f"{record_id}.*"):
        p.unlink(missing_ok=True)


def _pkg_version() -> str:
    from corpus import __version__

    return __version__
