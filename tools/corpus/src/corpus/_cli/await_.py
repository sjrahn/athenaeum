"""Block until a record's requested normalization pass settles (spec §8.5).

Polls the external queue state — read-only on the record. Resolves when the
record has no pending/in-flight request and reports the most recent pass outcome:
exit 0 on a completed pass (or, absent a recorded result, a `status: normalized`
record), non-zero on a failed pass or timeout.
"""

from __future__ import annotations

import argparse
import sys
import time

from corpus import paths, records
from corpus import queue as _queue
from corpus._cli._common import add_corpus_root_arg, attach_workflow_note, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Hash, hex prefix, or record file path.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        metavar="SECONDS",
        help="Max seconds to wait (0 = wait indefinitely). Default %(default)s.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        metavar="SECONDS",
        help="Poll interval in seconds. Default %(default)s.",
    )
    add_corpus_root_arg(parser)
    attach_workflow_note(parser, "normalize-loop")


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    rid, record_file = paths.resolve_record(root, args.target)
    deadline = (time.monotonic() + args.timeout) if args.timeout else None

    while True:
        st = _queue.state(root, rid)
        if not _queue.is_pending(st):
            return _settle(st, record_file, rid)
        if deadline is not None and time.monotonic() >= deadline:
            print(f"await {rid[:12]}: timed out after {args.timeout}s", file=sys.stderr)
            return 1
        time.sleep(args.interval)


def _settle(st: dict, record_file, rid: str) -> int:
    result = st.get("result")
    if result and result.get("outcome") == "completed":
        print(f"{rid[:12]} normalized")
        return 0
    if result and result.get("outcome") == "failed":
        reason = result.get("reason") or "(no reason given)"
        print(f"{rid[:12]} normalization failed: {reason}", file=sys.stderr)
        return 1
    # No recorded pass — fall back to the record's own status.
    post = records.load(record_file)
    if post.metadata.get("status") == "normalized":
        print(f"{rid[:12]} normalized")
        return 0
    print(f"{rid[:12]}: no normalization pass recorded (status: {post.metadata.get('status')!r})", file=sys.stderr)
    return 1
