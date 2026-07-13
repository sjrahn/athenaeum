"""Bulk re-derive — `corpus redraft`.

Re-derives records from their retained `artifacts/<hash>` bytes (the per-record draft
core, `_cli.draft.derive_record`, applied across the corpus). The deterministic
recompile that surfaces — via `git diff records/` — exactly which records a schema /
overlay / tooling change affects. In 3.0 the re-derived mechanical body leaves the record
at `status: stub` — a stub carrying a grandfathered materialized derivation (§12.18 step 3),
superseded by its next pass; nothing writes `status: draft` after the 2026-07-13 fleet sweep.
**Idempotent**: a clean re-stub (touch collapsed to the original ingest entry, no re-stub
touch) means an unchanged record re-derives byte-for-byte, so it isn't rewritten and produces
no git churn; only records whose drafted content actually changed are touched. `--dry-run`
reports the set without writing.

Leaves `draft` (single-record re-derive), `re-stub` (single reset), and `compile` unchanged.
`compile` reassembles a record from a decomposed *manifest* (the normalization edit
substrate); `redraft` re-derives from the source *artifact* via the mime drafter —
different inputs, different jobs. redraft **refuses `normalized` records unless
`--force`**, since re-deriving discards any normalization work.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

from corpus import paths, records, restub, touches
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root
from corpus._cli.draft import DraftError, derive_record
from corpus.store import ArtifactMissing


def redraft_record(
    record_file: Path, corpus_root: Path, *, fingerprint_cli: bool | None = None
) -> str:
    """Re-derive the record at `record_file` from its artifact, **in memory**; return
    the serialized re-derived record text (NOT written — the caller persists it when not
    a dry run). Idempotent: the in-memory re-stub collapses `touch[]` to the original
    ingest entry (no re-stub touch), so re-deriving an unchanged record reproduces a
    fresh-draft record byte-for-byte. Raises `DraftError` / `ArtifactMissing` when the
    record can't be re-derived."""
    from corpus.draft import mbox_manifest

    post = records.load(record_file)
    chain = touches.touch_list(post)
    # The mbox manifest's declared ordinals are user intent, not derivable from the bytes, and
    # re-stub clears embeds — so capture them before the reset and re-declare them (spec §12.11).
    messages = mbox_manifest.declared_ordinals(post) or None
    stub = restub.restub_post(post, touch_chain=[chain[0]] if chain else [])
    derive_record(stub, corpus_root, fingerprint_cli=fingerprint_cli, messages=messages)
    return records.dumps(stub)


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
        choices=("draft", "normalized", "any"),
        default="draft",
        help="which record statuses to consider (default: draft).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-derive `normalized` records too (discards their normalization — off by default).",
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
        help="force perceptual fingerprinting on/off for every re-derived record (else the schema decides).",
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
    corpus_root = resolved_corpus_root(args)

    if args.target:
        _, rf = paths.resolve_record(corpus_root, args.target)
        candidates = [rf]
    else:
        candidates = sorted(records.iter_record_paths(corpus_root))

    fp = getattr(args, "fingerprint", None)
    changed = unchanged = skipped = failed = 0

    for rf in candidates:
        post = records.load(rf)
        status = str(post.metadata.get("status") or "").lower()

        if args.status != "any" and status != args.status:
            continue
        if status == "normalized" and not args.force:
            skipped += 1  # protect normalization — re-derive would discard it
            continue
        if args.mime and records.media_type_for(post) != args.mime:
            continue
        if args.host and not _host_matches(post, args.host):
            continue

        rid = str(post.metadata.get("id") or "")[:12]
        try:
            new_text = redraft_record(rf, corpus_root, fingerprint_cli=fp)
        except (DraftError, ArtifactMissing) as exc:
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

    verb = "would re-derive" if args.dry_run else "re-derived"
    summary = (
        f"{verb} {changed + unchanged} record(s); {changed} changed, "
        f"{unchanged} unchanged, {skipped} normalized-skipped"
    )
    if failed:
        summary += f", {failed} failed"
    print(summary)
    return 0
