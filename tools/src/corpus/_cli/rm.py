"""Remove one or more records — the `.md`, the content-addressed artifact, and now-empty
shard dirs (spec is silent; this is a curatorial CLI op).

Previews the plan by default (record + artifact paths/sizes, and any records that cite the
target); pass `--yes` to delete. A record cited by another record is refused unless
`--force`. The artifact bytes are gitignored, so removing them is undoable only by
re-capture — `--keep-artifact` drops the `.md` but retains the bytes. The resolver cache is
left alone (it is keyed by URI hash, not the record's hash); `corpus gc` reclaims it.
"""

from __future__ import annotations

import argparse
import json
import sys

from corpus import maintenance, paths
from corpus._cli._common import add_corpus_root_arg, human_bytes, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("ids", nargs="+", help="record id(s) or hash prefix(es) to remove")
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="actually delete (default: preview the plan only).",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="delete even when another record cites the target (implies --yes).",
    )
    parser.add_argument(
        "--keep-artifact",
        action="store_true",
        help="remove the record .md but keep the content-addressed artifact bytes.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the structured removal result as JSON.",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    # resolve_record exits non-zero (no-op) on an unresolvable / ambiguous id — before
    # anything is deleted, so a bad id in the batch fails the whole command cleanly.
    ids = [paths.resolve_record(root, t)[0] for t in args.ids]
    execute = args.yes or args.force

    result = maintenance.remove_records(
        root, ids, keep_artifact=args.keep_artifact, force=args.force, execute=execute
    )

    if args.json:
        print(json.dumps(_to_dict(result), ensure_ascii=False, indent=2))
        return 1 if result.blocked else 0

    _print_plans(result)
    return _print_outcome(result, execute=execute)


def _print_plans(result: maintenance.RemovalResult) -> None:
    warn_repro = False
    for plan in result.plans:
        if not plan.exists:
            print(f"{plan.record_id[:12]}  (no record on disk — skipped)")
            continue
        print(f"{plan.record_id[:12]}  record: {plan.record_path}")
        if plan.artifact_path:
            kept = " (kept)" if result.keep_artifact else ""
            print(f"{'':14}artifact: {plan.artifact_path} ({human_bytes(plan.artifact_size)}){kept}")
            if not result.keep_artifact:
                warn_repro = True
        for ref in plan.referrers:
            print(f"{'':14}cited by: {ref.record_id[:12]} ({ref.via})")
        for member in plan.stranded_promoted:
            print(f"{'':14}contains promoted: {member[:12]} (bytes would be stranded — no other route)")
        for member, route in plan.surviving_routes:
            print(f"{'':14}contains promoted: {member[:12]} (survives via {route})")
    if warn_repro:
        print("  note: artifact bytes are gitignored — removal is undoable only by re-capture.")


def _print_outcome(result: maintenance.RemovalResult, *, execute: bool) -> int:
    if result.blocked:
        names = ", ".join(b[:12] for b in result.blocked)
        print(
            f"refused {len(result.blocked)} record(s): {names} "
            f"— cited by another record, or a container of promoted members. "
            f"Re-run with --force to remove anyway.",
            file=sys.stderr,
        )
    if not execute:
        if result.removed:
            print(f"(dry-run) would remove {len(result.removed)} record(s) — pass --yes to delete.")
        return 1 if result.blocked else 0
    if result.removed:
        print(f"removed {len(result.removed)} record(s).")
    return 1 if result.blocked else 0


def _to_dict(result: maintenance.RemovalResult) -> dict:
    return {
        "dry_run": result.dry_run,
        "keep_artifact": result.keep_artifact,
        "force": result.force,
        "removed": result.removed,
        "blocked": result.blocked,
        "plans": [
            {
                "id": p.record_id,
                "exists": p.exists,
                "record_path": p.record_path,
                "artifact_path": p.artifact_path,
                "artifact_bytes": p.artifact_size,
                "referrers": [
                    {"id": r.record_id, "via": r.via, "pointer": r.pointer} for r in p.referrers
                ],
                "stranded_promoted": p.stranded_promoted,
                "surviving_routes": [
                    {"member": m, "route": r} for m, r in p.surviving_routes
                ],
            }
            for p in result.plans
        ],
    }
