"""Apply deterministic auto-classifications to one stored record — `corpus classify`.

Evaluates the composite overlays' `classify_when` predicates (spec §7.4) against the record's
fact base and stamps a `<!--classify <ns>/<id>-->` block with `provenance: auto` for each
match. Idempotent: strips the record's existing `provenance: auto` blocks and regenerates from
the current rules, leaving hand-/normalizer-asserted blocks (no provenance) untouched.
`--dry-run` reports the adds/removes without writing.

Unlike `corpus draft` / `redraft` this never re-derives the body or fetches the artifact — it
only re-evaluates membership, so it is safe to run on a `normalized` record. For a bulk sweep
after authoring or editing an overlay, use `corpus reclassify`.
"""

from __future__ import annotations

import argparse
import json
import sys

from corpus import classify_rules, paths, records
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="record to classify (hash / hex prefix / path).")
    parser.add_argument(
        "--dry-run", action="store_true", help="report the adds/removes without writing."
    )
    parser.add_argument("--json", action="store_true", help="emit a single JSON object.")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    record_id, record_file = paths.resolve_record(corpus_root, args.target)
    post = records.load(record_file)

    delta = classify_rules.apply_auto_classifications(corpus_root, post)
    if delta.changed and not args.dry_run:
        records.dump(post, record_file)

    if args.json:
        json.dump(
            {
                "record": record_id,
                "added": delta.added,
                "removed": delta.removed,
                "kept": delta.kept,
                "changed": delta.changed,
                "dry_run": bool(args.dry_run),
                "why": {m.class_id: m.why for m in delta.matches},
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0

    if not delta.changed:
        n = len(delta.matches)
        print(f"{record_id[:12]}: no change ({n} auto classification(s) already current).")
        return 0

    verb = "would update" if args.dry_run else "updated"
    print(f"{verb} {record_id[:12]}:")
    why = {m.class_id: m.why for m in delta.matches}
    for class_id in delta.added:
        print(f"  + {class_id}  ({why.get(class_id, '')})")
    for class_id in delta.removed:
        print(f"  - {class_id}")
    return 0
