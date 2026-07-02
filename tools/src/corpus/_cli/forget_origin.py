"""Drop a single origin alias from a record without removing the record (the many-to-one
provenance case — a wrong URL alias on an otherwise good record).

Matches the alias by identity key, so a query-noise / `/page-1` spelling still matches.
Refuses if the alias is the record's only origin (that's a `corpus rm`). Edits the tracked
`.md` (git-recoverable); `--dry-run` previews without writing.
"""

from __future__ import annotations

import argparse
import sys

from corpus import maintenance, paths
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("id", help="record id or hash prefix")
    parser.add_argument("uri", help="the origin URI / alias to drop")
    parser.add_argument(
        "--dry-run", action="store_true", help="report the outcome without writing."
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    record_id, _ = paths.resolve_record(root, args.id)
    result = maintenance.forget_origin(root, record_id, args.uri, execute=not args.dry_run)

    if result.reason == "not_present":
        print(
            f"{record_id[:12]}: {args.uri!r} is not among its origin URIs", file=sys.stderr
        )
        return 1
    if result.reason == "last_origin":
        print(
            f"{record_id[:12]}: {args.uri!r} is the record's only origin — "
            f"use `corpus rm {record_id[:12]}` to remove the record instead.",
            file=sys.stderr,
        )
        return 1

    verb = "would drop" if result.dry_run else "dropped"
    print(f"{verb} origin alias from {record_id[:12]} ({result.remaining} origin URI(s) remain)")
    return 0
