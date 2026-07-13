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

from corpus import derive, records, touches
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root
from corpus.derive import DeriveError
from corpus.draft import mbox_manifest
from corpus.store import ArtifactMissing


def reattest_record(
    record_file: Path,
    corpus_root: Path,
    *,
    fingerprint_cli: bool | None = None,
    messages: list[int] | None = None,
) -> str:
    """Re-derive the attested layer of the record at `record_file`, **in memory**; return
    the serialized record (NOT written). Strips + re-derives the attested layer while
    preserving the authored layer (`derive.attest(strip=True)`). `messages` is the mbox
    selective declaration (§12.11, the re-homed `--messages`). Idempotent: when the attested
    facts re-derive identically the original text is returned unchanged — no touch appended,
    no rewrite. Raises `DeriveError` / `ArtifactMissing`."""
    post = records.load(record_file)
    before = records.dumps(post)
    mime_schema_id = derive.attest(
        post, corpus_root, fingerprint_cli=fingerprint_cli, strip=True, messages=messages
    )
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
    parser.add_argument(
        "--messages",
        default=None,
        metavar="SPEC",
        help=(
            "mbox only (single target): declare the 1-indexed messages to manifest as "
            "`message/rfc822` embeds — a comma list of ordinals and `lo-hi` ranges "
            "(e.g. `5,12,90-95`). Cumulative: unions with the already-declared set (§12.11). "
            "The re-homed successor of the 2.x `corpus draft --messages`."
        ),
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

    messages_spec = getattr(args, "messages", None)
    if messages_spec is not None and not args.target:
        sys.exit("--messages requires a single target record (an mbox).")
    ordinals: list[int] | None = None
    if messages_spec:
        from corpus import schemas

        try:
            ordinals = mbox_manifest.parse_message_spec(messages_spec)
        except ValueError as exc:
            sys.exit(str(exc))
        _, rf = paths.resolve_record(corpus_root, args.target)
        mt = schemas.load_mime_schema(corpus_root, records.media_type_for(records.load(rf))) or {}
        if str((mt.get("draft") or {}).get("strategy") or "") != "mbox-manifest":
            sys.exit("--messages is only valid for an mbox record.")

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
            new_text = reattest_record(rf, corpus_root, fingerprint_cli=fp, messages=ordinals)
        except mbox_manifest.MessageHashConflict as exc:
            sys.exit(str(exc))  # stale declaration — a hard error (§12.11), never papered over
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
