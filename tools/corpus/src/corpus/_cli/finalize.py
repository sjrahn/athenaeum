"""Close a claimed normalization pass as complete (spec §8.5).

The gate for "done": the record must be `status: normalized` (the normalizer set
it) AND lint clean. A blocking lint finding makes finalize refuse (exit 1) so a
dirty pass is never reported done — the loop should fix it and re-finalize, or
`corpus release <id> --failed`. finalize is read-only on the record.
"""

from __future__ import annotations

import argparse
import sys

from corpus import lint as _lint
from corpus import paths, records, segments
from corpus import queue as _queue
from corpus._cli._common import add_corpus_root_arg, attach_workflow_note, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Hash, hex prefix, or record file path.")
    parser.add_argument(
        "--by",
        default=None,
        help="Identifier of the finalizing loop session, recorded on the result.",
    )
    add_corpus_root_arg(parser)
    attach_workflow_note(parser, "normalize-loop")


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    rid, record_file = paths.resolve_record(root, args.target)

    if _queue.state(root, rid)["state"] != "claimed":
        print(f"{rid[:12]} is not claimed — finalize only closes a claimed pass", file=sys.stderr)
        return 1

    post = records.load(record_file)
    status = post.metadata.get("status")
    if status != "normalized":
        print(
            f"refusing to finalize {rid[:12]}: status is {status!r}, not 'normalized' "
            f"— the normalizer must set it before the pass is closed",
            file=sys.stderr,
        )
        return 1

    blocks = segments.iter_blocks(post.content or "")
    errors = [f for f in _lint.lint(post, blocks, root) if f.severity == "error"]
    if errors:
        for f in errors:
            loc = f" [{f.address}]" if f.address else ""
            print(f"{rid[:12]}: {f.severity.upper()} {f.rule_id}{loc}: {f.message}", file=sys.stderr)
        print(
            f"refusing to finalize {rid[:12]}: {len(errors)} blocking lint finding(s) — "
            f"fix and re-finalize, or `corpus release {rid[:12]} --failed`",
            file=sys.stderr,
        )
        return 1

    _queue.complete(root, rid, by=args.by)
    print(f"finalized {rid[:12]} (normalization pass complete)")
    return 0
