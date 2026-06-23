"""Claim the next queued record for normalization (spec §8.5).

Prints the claimed record's id to stdout and exits 0. An empty queue prints
nothing to stdout and exits 1 — the natural stop signal for a `/loop` session:

    while id=$(corpus drain --by "$SESSION"); do
        # ...normalize $id in-session (see `corpus guidance $id`)...
        corpus finalize "$id" || corpus release "$id" --failed
    done
"""

from __future__ import annotations

import argparse
import json

from corpus import paths
from corpus import queue as _queue
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--by",
        default=None,
        help="Identifier of the claiming loop session, recorded on the claim.",
    )
    parser.add_argument(
        "--lease",
        type=int,
        default=_queue.DEFAULT_LEASE_SECONDS,
        metavar="SECONDS",
        help="Seconds before a stale claim (dead session) is reclaimable (default %(default)s).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON object {id, record} instead of the bare id.",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    rid = _queue.drain(root, by=args.by, lease=args.lease)
    if rid is None:
        return 1  # empty queue — the loop's stop signal (nothing on stdout)
    if args.json:
        print(json.dumps({"id": rid, "record": str(paths.record_path(root, rid))}))
    else:
        print(rid)
    return 0
