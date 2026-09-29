"""Emit form-triage packets (spec §8.5, v50) — read-only; the triage agent proposes.

    corpus triage                  packets for REQUESTED records that are formless and ungoverned
    corpus triage --all            packets for the whole proxy population (a report: never enqueue)
    corpus triage --forms          the form catalog the proposals choose from

One JSON object per line. The verb never writes a record and never enqueues: a proposal made
from a `--requested` packet reaches the normalizer as `corpus enqueue <id> --hint
"form/<id> candidate …"` on the request already standing, and a proposal made from an `--all`
packet is report material only — normalization runs only under demand (§8.5).
"""

from __future__ import annotations

import argparse
import json
import sys

from corpus import queue as _queue
from corpus import records, triage
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--requested",
        action="store_true",
        help="(default) records with a pending normalize request that are formless and "
        "governed by no contract — the only records a triage hint may be attached to",
    )
    scope.add_argument(
        "--all",
        action="store_true",
        help="every proxy record (formless, ungoverned, no stored rendering) — a read-only "
        "report; its proposals are never enqueued",
    )
    scope.add_argument(
        "--forms", action="store_true", help="print the form catalog instead of packets"
    )
    parser.add_argument("--limit", type=int, default=None, help="stop after N packets")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    from corpus import paths

    root = resolved_corpus_root(args)
    out = sys.stdout
    if args.forms:
        for row in triage.form_catalog(root):
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
        return 0
    emitted = 0
    if args.all:
        candidates = (post for _, post in records.load_all(root))
    else:
        candidates = (
            records.load(paths.record_path(root, e["id"]))
            for e in _queue.entries(root)
            if e["state"] == "requested" and paths.record_path(root, e["id"]).is_file()
        )
    for post in candidates:
        if not triage.eligible(post, root, proxy_only=args.all):
            continue
        out.write(json.dumps(triage.packet(post, root), ensure_ascii=False, default=str) + "\n")
        emitted += 1
        if args.limit is not None and emitted >= args.limit:
            break
    print(f"{emitted} packet(s)", file=sys.stderr)
    return 0
