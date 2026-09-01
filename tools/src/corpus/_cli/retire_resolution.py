"""The v42 lifecycle sweep — `corpus retire-resolution` (spec §4.3.3.2, CHANGELOG v42).

Strips the retired `resolution:` field from every `issue`-namespace context block: an
issue is a lifecycle-free fidelity attestation — dropped by its emitting pass when the
fact it attests stops being true, never edited toward a resolved state. Blocks whose
`resolution` was `fixed` or `superseded` are DROPPED outright — the fix already landed
in the record (the touch chain proves it) and git history holds what was attested;
`open`/`wontfix` blocks stand, minus the field. An unknown corpus-local resolution
value is treated conservatively: the field is stripped, the block kept, and the value
reported — the sweep never deletes on a value it does not understand.

Dry-run by default: `--apply` writes. Mechanical and idempotent — a record with no
`resolution:` anywhere is skipped untouched; a changed record gains a
`corpus.retire-resolution@<v>` touch.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from corpus import records, touches
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root

TOUCH_ID = "retire-resolution"

#: `resolution` values whose blocks drop outright: the attested problem was already
#: addressed (or obsoleted), so under lifecycle-free law the block simply isn't true
#: any more. Everything else keeps its block and loses the field.
_DROP_VALUES = frozenset({"fixed", "superseded"})


def sweep_post(post) -> Counter[str]:
    """Mutate `post` in place; return counts (`stripped` / `dropped` / `kept-unknown:<v>`).

    Empty counter ⇒ the record carried no `resolution:` and is untouched.
    """
    counts: Counter[str] = Counter()
    contexts = post.metadata.get("_contexts") or []
    kept = []
    for ctx in contexts:
        fields = ctx.get("fields") or {}
        if ctx.get("namespace") != "issue" or "resolution" not in fields:
            kept.append(ctx)
            continue
        value = str(fields.pop("resolution")).lower()
        if value in _DROP_VALUES:
            counts["dropped"] += 1
            continue
        if value not in ("open", "wontfix"):
            counts[f"kept-unknown:{value}"] += 1
        counts["stripped"] += 1
        kept.append(ctx)
    if counts:
        post.metadata["_contexts"] = kept
    return counts


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "target",
        nargs="*",
        default=None,
        help="record ids (hash / hex prefix / path); omit to sweep the whole corpus.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the rewrites (default is a dry-run that reports and writes nothing).",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    from corpus import paths

    corpus_root = resolved_corpus_root(args)
    if args.target:
        candidates = [paths.resolve_record(corpus_root, t)[1] for t in args.target]
    else:
        candidates = sorted(records.iter_record_paths(corpus_root))

    changed = held = 0
    totals: Counter[str] = Counter()
    for rf in candidates:
        try:
            post = records.load(rf)
            counts = sweep_post(post)
        except Exception as exc:  # tolerant sweep: one bad record never stops the fleet
            print(f"  ERROR {rf.stem[:12]}: {exc}", file=sys.stderr)
            held += 1
            continue
        if not counts:
            continue
        changed += 1
        totals.update(counts)
        if args.apply:
            touches.record_touch(post, touches.script_identifier(TOUCH_ID))
            records.dump(post, rf)

    verb = "swept" if args.apply else "would sweep"
    detail = ", ".join(f"{k}={v}" for k, v in sorted(totals.items())) or "none"
    print(f"{verb} {changed} record(s); {held} held")
    print(f"  resolution fields: {detail}")
    return 1 if held else 0
