"""Bulk re-attest — `corpus reattest` (spec §12.4.6, §8.3).

Re-derives the **attested layer** — the byte-facts ingest stamps: the artifact block's
extended fields, the manifest/exposable embeds, and the drafter's mechanical issues — from a
record's retained artifact + the current schemas/tooling, **never touching the authored
layer** (the stored content zone, embed/segment descriptions, editorial fields, asserted
issues). It is the deterministic recompile of just the attested facts: `git diff records/`
surfaces exactly which records a schema / overlay / tooling change affected.

Unlike the 2.x `corpus redraft` (which re-derived the whole record and so refused
`normalized` records), re-attest preserves the authored layer, so it needs no
normalized-refusal guard and sweeps every status by default. **Idempotent**: a record whose
attested facts re-derive byte-for-byte is not rewritten and appends no touch (the pass only
records itself when it actually changed something). `--dry-run` reports the set without
writing.

Distinct from `corpus compile`, which reassembles a record from a decomposed *manifest*
(the normalize edit substrate) rather than from the source *artifact*.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

from corpus import records, touches
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root
from corpus.derive import DeriveError, build_content_zone
from corpus.store import ArtifactMissing


def _is_drafter_issue(ctx: dict) -> bool:
    """A mechanical drafter-emitted issue — the attested layer's issue half. Identified by
    the `corpus.draft.*` detector family (a capturer's issue detector is preserved)."""
    if (ctx.get("namespace") or "") != "issue":
        return False
    detector = str((ctx.get("fields") or {}).get("detector") or "")
    return detector.startswith("corpus.draft.")


def _reattest_in_place(post, corpus_root: Path, *, fingerprint_cli: bool | None = None) -> str:
    """Strip + re-derive the attested layer of `post` in place; return the mime schema id.
    Preserves the authored layer: the content zone (never `finish`-ed here), embed
    descriptions (carried forward by transport), editorial fields, and non-drafter issues."""
    from corpus._cli.draft import _apply_drafter_result
    from corpus.draft import mbox_manifest

    # The mbox manifest's declared ordinals are operator intent, not derivable from the bytes;
    # capture them before the strip and re-declare them (spec §12.11).
    messages = mbox_manifest.declared_ordinals(post) or None

    # Carry-forward authored embed descriptions (authored — normalize owns them, §4.4.7),
    # keyed by the embed's transport hash so they re-attach to the re-derived embeds.
    authored_desc: dict[str, str] = {}
    for e in records.iter_embed_blocks(post):
        d = (e.get("fields") or {}).get("description")
        if d:
            authored_desc[str(e.get("transport"))] = str(d)

    # Strip the attested layer: embeds, drafter issues, and the artifact block's extended
    # fields (the opener MIME stays — it is byte-intrinsic).
    post.metadata["_embeds"] = []
    post.metadata["_contexts"] = [
        c for c in (post.metadata.get("_contexts") or []) if not _is_drafter_issue(c)
    ]
    art = records.artifact_block(post) or {}
    records.set_artifact_block(post, mime=str(art.get("mime") or ""), fields={})

    # Re-derive the attestation from the artifact. The Build's content zone (the body) is
    # DISCARDED — `body` is a derivation op now (§6.2); we never `finish` it into the record.
    _build, result, _mt, _bin, mime_schema_id = build_content_zone(
        post, corpus_root, fingerprint_cli=fingerprint_cli, messages=messages
    )
    _apply_drafter_result(post, result, mime_schema_id, corpus_root)

    # Re-attach authored descriptions to the re-derived embeds.
    for e in post.metadata.get("_embeds") or []:
        d = authored_desc.get(str(e.get("transport")))
        if d and "description" not in (e.get("fields") or {}):
            e.setdefault("fields", {})["description"] = d
    return mime_schema_id or ""


def reattest_record(
    record_file: Path, corpus_root: Path, *, fingerprint_cli: bool | None = None
) -> str:
    """Re-derive the attested layer of the record at `record_file`, **in memory**; return
    the serialized record (NOT written). Idempotent: when the attested facts re-derive
    identically the original text is returned unchanged — no touch appended, no rewrite.
    Raises `DeriveError` / `ArtifactMissing`."""
    post = records.load(record_file)
    before = records.dumps(post)
    mime_schema_id = _reattest_in_place(post, corpus_root, fingerprint_cli=fingerprint_cli)
    after = records.dumps(post)
    if after == before:
        return before  # attested layer unchanged — the pass records nothing
    touches.record_touch(post, touches.script_identifier("attest." + (mime_schema_id or "unknown")))
    return records.dumps(post)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="a single record (hash / hex prefix / path); omit to sweep the whole corpus.",
    )
    parser.add_argument("--mime", default=None, help="only records whose artifact MIME equals this.")
    parser.add_argument(
        "--host", default=None, help="only records with an origin URI on this host (subdomains included)."
    )
    parser.add_argument(
        "--status",
        choices=("stub", "draft", "normalized", "any"),
        default="any",
        help="which record statuses to consider (default: any — the attested layer is status-independent).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report which records would change, writing nothing.",
    )
    parser.add_argument(
        "--fingerprint",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="force perceptual fingerprinting on/off for every re-attested record (else the schema decides).",
    )
    add_corpus_root_arg(parser)


def _origin_hosts(post) -> set[str]:
    hosts: set[str] = set()
    for uri in records.iter_origin_uris(post):
        host = (urlparse(str(uri)).hostname or "").lower()
        if host:
            hosts.add(host)
    return hosts


def _host_matches(post, want: str) -> bool:
    want = want.lower()
    return any(h == want or h.endswith("." + want) for h in _origin_hosts(post))


def run(args: argparse.Namespace) -> int:
    from corpus import paths

    corpus_root = resolved_corpus_root(args)

    if args.target:
        _, rf = paths.resolve_record(corpus_root, args.target)
        candidates = [rf]
    else:
        candidates = sorted(records.iter_record_paths(corpus_root))

    fp = getattr(args, "fingerprint", None)
    changed = unchanged = failed = 0

    for rf in candidates:
        post = records.load(rf)
        status = str(post.metadata.get("status") or "").lower()
        if args.status != "any" and status != args.status:
            continue
        if args.mime and records.media_type_for(post) != args.mime:
            continue
        if args.host and not _host_matches(post, args.host):
            continue

        rid = str(post.metadata.get("id") or "")[:12]
        try:
            new_text = reattest_record(rf, corpus_root, fingerprint_cli=fp)
        except (DeriveError, ArtifactMissing) as exc:
            print(f"  skip {rid}: {exc}", file=sys.stderr)
            failed += 1
            continue

        if new_text == rf.read_text(encoding="utf-8"):
            unchanged += 1
            continue
        changed += 1
        if not args.dry_run:
            rf.write_text(new_text, encoding="utf-8")
        verb = "would change" if args.dry_run else "changed"
        print(f"  {verb}: {rf.relative_to(corpus_root)}")

    verb = "would re-attest" if args.dry_run else "re-attested"
    summary = f"{verb} {changed + unchanged} record(s); {changed} changed, {unchanged} unchanged"
    if failed:
        summary += f", {failed} failed"
    print(summary)
    return 0
