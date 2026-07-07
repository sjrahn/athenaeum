"""Prove whether one record's content is preserved in another (`corpus.continuity`).

    corpus continuity <A> <B>

Reports, per `path=<member>` address of A, whether B preserves it — identical bytes,
contained (A is a prefix B extends), diverged, or absent — and the bottom line
`contains_a`: the green light for `B supersedes A` and for rewriting citations
`corpus://A?<addr>` → `corpus://B?<addr>`. Read-only.
"""

from __future__ import annotations

import argparse

from corpus import continuity as continuity_lib
from corpus import paths
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("a", help="the OLD record (hash or unique prefix)")
    parser.add_argument("b", help="the NEW record (hash or unique prefix)")
    parser.add_argument("--json", action="store_true", help="emit the result as JSON")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    a_id, _ = paths.resolve_record(corpus_root, args.a)
    b_id, _ = paths.resolve_record(corpus_root, args.b)
    result = continuity_lib.continuity(corpus_root, a_id, b_id)

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "a": a_id,
                    "b": b_id,
                    "contains_a": result.contains_a,
                    "members": [
                        {"address": m.address, "status": m.status} for m in result.members
                    ],
                },
                indent=2,
            )
        )
        return 0 if result.contains_a else 1

    print(f"A {a_id[:12]}…  →  B {b_id[:12]}…")
    for m in result.members:
        label = m.address or "(whole artifact)"
        print(f"  {m.status:<9} {label}")
    print(f"\ncontains_a: {result.contains_a}")
    if not result.contains_a:
        print("  → B does NOT preserve all of A; supersession/rewrite is unsafe.")
    return 0 if result.contains_a else 1
