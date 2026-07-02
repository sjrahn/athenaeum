"""Prune regenerable derived data — the resolver cache, leftover capture/ staging,
orphan artifacts, and export/ bundles (spec is silent; this is CLI hygiene).

Previews by default (counts + bytes reclaimed per category); pass `--yes` to delete.
Age-gated by `--older-than` and idempotent, so it is safe to run on a cron tick. Never
touches a tracked record, a live queue entry, or any artifact that still has a record.
Generalizes `corpus queue --prune` to the other derived dirs.
"""

from __future__ import annotations

import argparse
import json

from corpus import maintenance
from corpus._cli._common import add_corpus_root_arg, human_bytes, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--older-than",
        type=float,
        default=maintenance.DEFAULT_GC_DAYS,
        metavar="DAYS",
        help="grace window in days (default %(default)s; 0 = prune everything now).",
    )
    parser.add_argument(
        "--include",
        default=None,
        metavar="CATS",
        help=(
            "comma-separated subset of "
            f"{','.join(maintenance.GC_CATEGORIES)} to sweep (default: all)."
        ),
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="actually delete (default: preview the plan only).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the structured sweep result as JSON.",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    include = args.include.split(",") if args.include is not None else None
    try:
        result = maintenance.sweep(
            root, older_than_days=args.older_than, include=include, dry_run=not args.yes
        )
    except ValueError as e:
        raise SystemExit(str(e)) from e

    if args.json:
        print(json.dumps(_to_dict(result), ensure_ascii=False, indent=2))
        return 0

    verb = "would reclaim" if result.dry_run else "reclaimed"
    if not result.items:
        print(f"gc: nothing to reclaim (older than {result.older_than_days:g}d)")
        return 0
    by_cat = result.by_category()
    for cat in result.categories:
        items = by_cat.get(cat) or []
        if items:
            size = sum(i.size for i in items)
            print(f"  {cat:<8} {len(items):>5} file(s)  {human_bytes(size)}")
    print(f"gc: {verb} {len(result.items)} file(s), {human_bytes(result.total_size)}")
    if result.dry_run:
        print("  (preview — re-run with --yes to delete)")
    return 0


def _to_dict(result: maintenance.SweepResult) -> dict:
    by_cat = result.by_category()
    return {
        "dry_run": result.dry_run,
        "older_than_days": result.older_than_days,
        "total": {"count": len(result.items), "bytes": result.total_size},
        "categories": {
            cat: {
                "count": len(by_cat.get(cat) or []),
                "bytes": sum(i.size for i in by_cat.get(cat) or []),
                "items": [{"path": i.path, "bytes": i.size} for i in (by_cat.get(cat) or [])],
            }
            for cat in result.categories
        },
    }
