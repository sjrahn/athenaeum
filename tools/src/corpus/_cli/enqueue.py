"""Request a (re-)normalization pass for a record (spec §8.5)."""

from __future__ import annotations

import argparse

from corpus import paths
from corpus import queue as _queue
from corpus._cli._common import add_corpus_root_arg, attach_workflow_note, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Hash, hex prefix, or record file path.")
    parser.add_argument(
        "--by",
        default=None,
        help="Identifier of the requester (e.g. a consumer's build agent), recorded on the request.",
    )
    parser.add_argument(
        "--hint",
        default=None,
        metavar="TEXT",
        help="Free-text requester context stored on the request, surfaced to the drain "
        "side (spec §8.5) — e.g. a proposed form or shape observation. The proposes/"
        "disposes seam: a reader may propose without authoring; the normalizer disposes "
        "against the bytes. A joining request's hint appends, never overwrites.",
    )
    add_corpus_root_arg(parser)
    attach_workflow_note(parser, "normalize-loop")


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    rid, _ = paths.resolve_record(root, args.target)
    outcome = _queue.enqueue(root, rid, by=args.by, hint=args.hint)
    label = {
        "requested": "enqueued",
        "already-requested": "already queued",
        "in-flight": "already in flight",
    }[outcome]
    print(f"{label}: {rid[:12]}")
    return 0
