"""Return a claimed record to the normalization queue (spec §8.5).

Bare `release` re-queues the record (e.g. a loop session shutting down cleanly,
leaving the work for the next drain). `release --failed [reason]` records a failed
outcome instead — the pass gave up; an awaiting requester resolves to failure.
"""

from __future__ import annotations

import argparse
import sys

from corpus import paths
from corpus import queue as _queue
from corpus._cli._common import add_corpus_root_arg, attach_workflow_note, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Hash, hex prefix, or record file path.")
    parser.add_argument(
        "--failed",
        nargs="?",
        const="",
        default=None,
        metavar="REASON",
        help="Record the pass as failed (optionally with a reason) instead of re-queueing.",
    )
    parser.add_argument(
        "--by",
        default=None,
        help="Identifier of the releasing loop session, recorded on a failed result.",
    )
    add_corpus_root_arg(parser)
    attach_workflow_note(parser, "normalize-loop")


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    rid, _ = paths.resolve_record(root, args.target)

    if _queue.state(root, rid)["state"] != "claimed":
        print(f"{rid[:12]} is not claimed", file=sys.stderr)
        return 1

    try:
        if args.failed is not None:
            _queue.fail(root, rid, reason=args.failed or None, by=args.by)
            suffix = f": {args.failed}" if args.failed else ""
            print(f"released {rid[:12]} as FAILED{suffix}")
        else:
            _queue.requeue(root, rid)
            print(f"released {rid[:12]} back to the queue")
    except _queue.QueueError as exc:
        print(f"{exc} — the claim was released or reclaimed; re-drain and retry", file=sys.stderr)
        return 1
    return 0
