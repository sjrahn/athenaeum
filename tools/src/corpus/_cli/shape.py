"""Shape records — `corpus shape` (spec §12.5.0, §8.1).

Drives `corpus.shape.shape_record` over one or more records: the **deterministic half of the
normalize pass**. For each target it loads the record, finds its declared form (the origin
overlay's `form:` mapping, §7.2), and — when a registered shaper applies — builds the authored
content zone through `recordbuild` (grammar-validated), writing the record back in place.

`shape_record` appends the `shape.<form-id>` touch and does **NOT** flip status: the interpretive
normalize pass owns the `stub → normalized` transition once the editorial work (title,
description, per-asset descriptions) is done (§12.5). A record whose origin declares no form, or
whose form has no registered shaper, is **skipped** — not an error.

Accepts multiple record ids (hash / hex prefix / path), and `-` to read whitespace/newline-
separated ids from stdin (fleet driving). Exits nonzero only on a hard error — a missing record
or a shaper exception — never for a plain skip.
"""

from __future__ import annotations

import argparse
import sys

from corpus import paths, records
from corpus import shape as shape_pkg
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "targets",
        nargs="+",
        help="record ids (hash / hex prefix / path); `-` reads ids from stdin (one per line).",
    )
    add_corpus_root_arg(parser)


def _expand_targets(targets: list[str]) -> list[str]:
    """Expand a `-` placeholder into whitespace/newline-separated ids read from stdin, keeping
    every explicit id in order."""
    out: list[str] = []
    for t in targets:
        if t == "-":
            out.extend(tok for tok in sys.stdin.read().split() if tok)
        else:
            out.append(t)
    return out


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)

    shaped = skipped = failed = 0
    for target in _expand_targets(args.targets):
        try:
            _rid, rf = paths.resolve_record(corpus_root, target)
        except SystemExit as exc:  # resolve_record exits on no-match / ambiguity / bad input
            print(f"error {target}: {exc.code}", file=sys.stderr)
            failed += 1
            continue

        post = records.load(rf)
        rid = str(post.metadata.get("id") or rf.stem)[:12]
        resolved = shape_pkg.form_for_record(post, corpus_root)
        try:
            did_shape = shape_pkg.shape_record(post, corpus_root)
        except Exception as exc:  # a shaper blew up — a hard error, surfaced per-record
            print(f"error {rid}: shaper failed: {exc}", file=sys.stderr)
            failed += 1
            continue

        if did_shape:
            records.dump(post, rf)
            form_id = resolved[1] if resolved else "?"
            print(f"shaped {rid} ({form_id})")
            shaped += 1
        elif resolved is not None:
            # A form is declared but no shaper is registered for it (form or origin id).
            print(f"skipped {rid} (form {resolved[1]}: no registered shaper)")
            skipped += 1
        else:
            print(f"skipped {rid} (no declared form)")
            skipped += 1

    summary = f"shaped {shaped} record(s); {skipped} skipped"
    if failed:
        summary += f", {failed} failed"
    print(summary)
    return 1 if failed else 0
