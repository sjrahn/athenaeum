"""Claim the next queued record for normalization (spec §8.5).

Prints the claimed record's id to stdout and exits 0. An empty queue prints
nothing to stdout and exits 1 — the natural stop signal for a *scheduled* `/loop`
session that drains until dry each tick:

    while id=$(corpus drain --by "$SESSION"); do
        # ...normalize $id in-session (see `corpus guidance $id`)...
        corpus finalize "$id" || corpus release "$id" --failed
    done

`--wait` turns the same claim into a blocking long-poll: it returns the instant a
request is claimable and, on an empty queue, waits instead of exiting 1 (until
`--timeout`, if set). The poll runs here in the subprocess — the free layer — so a
*standing* loop wakes the (expensive) model only when there is genuinely work,
rather than on a clock. Pair it with a persistent runner that re-invokes per claim:

    corpus drain --wait --json --by "$SESSION"   # blocks; emits one id when work arrives

The wait never holds a claim (drain claims atomically only at the instant it
succeeds, then returns), so interrupting it mid-wait leaks nothing.
"""

from __future__ import annotations

import argparse
import json
import time

from corpus import paths
from corpus import queue as _queue
from corpus._cli._common import add_corpus_root_arg, attach_workflow_note, resolved_corpus_root


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
        "--wait",
        action="store_true",
        help="Block (long-poll) until a request is claimable instead of exiting 1 on an "
        "empty queue. The poll runs in this subprocess, not the model.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="With --wait, max seconds to block before giving up (exit 1). "
        "0 = wait indefinitely (default). Ignored without --wait.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        metavar="SECONDS",
        help="With --wait, poll interval in seconds (default %(default)s). Ignored without --wait.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON object {id, record} instead of the bare id.",
    )
    add_corpus_root_arg(parser)
    attach_workflow_note(parser, "normalize-loop")


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    if not args.wait:
        return _emit(_queue.drain(root, by=args.by, lease=args.lease), root, args.json)

    deadline = (time.monotonic() + args.timeout) if args.timeout else None
    try:
        while True:
            rid = _queue.drain(root, by=args.by, lease=args.lease)
            if rid is not None:
                return _emit(rid, root, args.json)
            if deadline is not None and time.monotonic() >= deadline:
                return 1  # waited out the timeout with nothing to claim — an empty result
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 130  # interrupted mid-wait — no claim was held, nothing to release


def _emit(rid: str | None, root, as_json: bool) -> int:
    if rid is None:
        return 1  # empty queue — the loop's stop signal (nothing on stdout)
    if as_json:
        print(json.dumps({"id": rid, "record": str(paths.record_path(root, rid))}))
    else:
        print(rid)
    return 0
