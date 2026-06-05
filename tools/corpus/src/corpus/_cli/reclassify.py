"""Bulk re-evaluate auto-classifications — `corpus reclassify`.

Re-runs the `classify_when` engine (spec §7.4) across the corpus (or a filtered subset),
stripping + regenerating each record's `provenance: auto` classify blocks from the current
overlay rules. The deterministic re-propagation that surfaces — via `git diff records/` —
exactly which records an overlay authoring / edit affects. Idempotent: a record whose auto
membership is unchanged is not rewritten (no churn). `--dry-run` reports the set without writing.

Strips + regenerates **only** `provenance: auto` blocks — it never re-derives the body, fetches
the artifact, or touches hand-/normalizer-asserted classify blocks, so (unlike `redraft`) it is
safe to run on `normalized` records. For a single record use `corpus classify`.
"""

from __future__ import annotations

import argparse
from urllib.parse import urlparse

from corpus import classify_rules, paths, records
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


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
        "--classification",
        default=None,
        help="only records already carrying this derived classification (e.g. source/majority-report).",
    )
    parser.add_argument(
        "--status",
        choices=("stub", "draft", "normalized", "any"),
        default="any",
        help="which record statuses to consider (default: any — reclassify is body-safe).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report which records would change, writing nothing.",
    )
    add_corpus_root_arg(parser)


def _host_matches(post, want: str) -> bool:
    want = want.lower()
    hosts = {
        (urlparse(str(uri)).hostname or "").lower() for uri in records.iter_origin_uris(post)
    }
    return any(h and (h == want or h.endswith("." + want)) for h in hosts)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)

    if args.target:
        _, rf = paths.resolve_record(corpus_root, args.target)
        candidates = [rf]
    else:
        candidates = sorted(records.iter_record_paths(corpus_root))

    changed = unchanged = 0
    for rf in candidates:
        post = records.load(rf)
        status = str(post.metadata.get("status") or "").lower()
        if args.status != "any" and status != args.status:
            continue
        if args.mime and records.media_type_for(post) != args.mime:
            continue
        if args.host and not _host_matches(post, args.host):
            continue
        if args.classification and args.classification not in records.derived_classifications(post):
            continue

        delta = classify_rules.apply_auto_classifications(corpus_root, post)
        if not delta.changed:
            unchanged += 1
            continue

        changed += 1
        if not args.dry_run:
            records.dump(post, rf)
        verb = "would change" if args.dry_run else "changed"
        bits = [f"+{c}" for c in delta.added] + [f"-{c}" for c in delta.removed]
        print(f"  {verb}: {rf.relative_to(corpus_root)}  [{', '.join(bits)}]")

    verb = "would reclassify" if args.dry_run else "reclassified"
    print(f"{verb} {changed + unchanged} record(s); {changed} changed, {unchanged} unchanged")
    return 0
