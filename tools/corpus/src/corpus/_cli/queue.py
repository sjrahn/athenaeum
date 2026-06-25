"""List — or prune — the normalization queue (spec §8.5)."""

from __future__ import annotations

import argparse
import json

from corpus import queue as _queue
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Remove settled results (and orphaned write scratch) older than --older-than, "
        "instead of listing. Never touches live requested/claimed entries.",
    )
    parser.add_argument(
        "--older-than",
        type=float,
        default=_queue.DEFAULT_PRUNE_DAYS,
        metavar="DAYS",
        help="With --prune, the grace window in days (default %(default)s; 0 = prune all now).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON — the entries array, or with --prune the {results, temp} removed.",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    if args.prune:
        return _run_prune(root, args.older_than, args.json)
    return _run_list(root, args.json)


def _run_prune(root, older_than: float, as_json: bool) -> int:
    removed = _queue.prune(root, older_than_days=older_than)
    if as_json:
        print(json.dumps(removed, ensure_ascii=False, indent=2))
    else:
        print(f"pruned {len(removed['results'])} result(s), {len(removed['temp'])} temp file(s)")
    return 0


def _run_list(root, as_json: bool) -> int:
    entries = _queue.entries(root)
    if as_json:
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        return 0
    if not entries:
        print("queue empty")
        return 0
    for e in entries:
        who = e.get("claimed_by") or e.get("requested_by") or ""
        when = e.get("claimed_at") or e.get("requested_at") or ""
        print(f"{e['state']:>9}  {e['id'][:12]}  {when}  {who}".rstrip())
    return 0
