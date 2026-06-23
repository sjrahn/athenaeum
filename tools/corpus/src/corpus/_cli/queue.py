"""List the normalization queue — requested + claimed entries (spec §8.5)."""

from __future__ import annotations

import argparse
import json

from corpus import queue as _queue
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the entries as a JSON array.",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    entries = _queue.entries(root)
    if args.json:
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
