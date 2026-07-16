"""Close a claimed normalization pass as complete (spec §8.5).

**The pass gate** (3.1, re-keyed 3.2): the record must be **formed where its overlays
declare a form** (§7.2, §4.4.6 — form-coherence lint covers the conformance half) and lint
clean. The 3.1 gate's authored half dissolves with the layer it named (§4.1) — a formed
span's editorial fields ride its section header under its own contract, and a record
staying formless owes no vouch: its derived title/description are already honest (§4.2.3).
Both remaining halves are derived from the record itself. An unmet form or a blocking lint
finding makes finalize refuse (exit 1) so a dirty pass is never reported done — the loop
should fix it and re-finalize, or `corpus release <id> --failed`. finalize is read-only on
the record.
"""

from __future__ import annotations

import argparse
import sys

from corpus import lint as _lint
from corpus import paths, records, segments
from corpus import queue as _queue
from corpus import shape as _shape
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

    refusals: list[str] = []
    unmet_form = _shape.declared_form_unmet(post, root)
    if unmet_form is not None:
        refusals.append(
            f"not formed — the origin declares form {unmet_form!r} but no section carries it "
            f"(spec §4.4.6)"
        )
    if refusals:
        for r in refusals:
            print(f"refusing to finalize {rid[:12]}: {r}", file=sys.stderr)
        print(
            f"refusing to finalize {rid[:12]}: pass gate not met — the normalizer must "
            f"finish the above before the pass is closed",
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

    try:
        _queue.complete(root, rid, by=args.by)
    except _queue.QueueError as exc:
        print(f"{exc} — the claim was released or reclaimed; re-drain and retry", file=sys.stderr)
        return 1
    print(f"finalized {rid[:12]} (normalization pass complete)")
    return 0
