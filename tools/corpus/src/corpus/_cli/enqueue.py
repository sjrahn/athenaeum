"""Request a (re-)normalization pass for a record (spec §8.5)."""

from __future__ import annotations

import argparse

from corpus import paths
from corpus import queue as _queue
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Hash, hex prefix, or record file path.")
    parser.add_argument(
        "--by",
        default=None,
        help="Identifier of the requester (e.g. a codex agent), recorded on the request.",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    rid, _ = paths.resolve_record(root, args.target)
    outcome = _queue.enqueue(root, rid, by=args.by)
    label = {
        "requested": "enqueued",
        "already-requested": "already queued",
        "in-flight": "already in flight",
    }[outcome]
    print(f"{label}: {rid[:12]}")
    return 0
