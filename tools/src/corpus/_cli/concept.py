"""Link a concept to a record — the manual authoring path for `concept` context blocks (§4.3.3.4).

    corpus concept link <record> --query "<text>"   [--address A --quote Q --occurrence N]
    corpus concept link <record> --concept <id>       [--address A --quote Q --occurrence N]

Resolves a concept against the local Wikipedia KB + the corpus-local registry, then writes a
`<!--context concept-->` block onto the record. With `--address` the block is a span-level *mention*;
without it, record-level *aboutness*. This is the deliberate, hand-driven path — the automatic
content-scanning annotation pass is future work.
"""

from __future__ import annotations

import argparse
import sys

from corpus import concepts, paths, records, wiki
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="action", required=True)

    parent = argparse.ArgumentParser(add_help=False)
    add_corpus_root_arg(parent)
    parent.add_argument("--zim", default=None, help="Path to the Wikipedia ZIM (else env / config).")

    link = sub.add_parser(
        "link", parents=[parent], help="Resolve a concept and write a concept block onto a record."
    )
    link.add_argument("target", help="Record hash, hex prefix, or record file path.")
    pick = link.add_mutually_exclusive_group(required=True)
    pick.add_argument("--query", help="Search the KB + local registry; use the top hit.")
    pick.add_argument(
        "--concept", help="An explicit canonical id (wikidata:Q…, enwiki:<Title>, or local:<slug>)."
    )
    link.add_argument("--address", default=None, help="Segment address of the mention (omit = aboutness).")
    link.add_argument("--quote", default=None, help="Verbatim span of the mention.")
    link.add_argument("--occurrence", type=int, default=None, help="Which match, if the quote repeats.")
    link.add_argument("--dry-run", action="store_true", help="Show the block without writing it.")


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    record_id, record_file = paths.resolve_record(root, args.target)
    post = records.load(record_file)

    try:
        kb: wiki.WikiKB | None = wiki.open_kb(zim=args.zim, corpus_root=root)
    except wiki.WikiUnavailable:
        kb = None  # local-only resolution still works
    resolver = concepts.ConceptResolver(corpus_root=root, kb=kb)

    if args.query:
        hits = resolver.search(args.query, limit=1)
        if not hits:
            print(f"no concept matches {args.query!r}", file=sys.stderr)
            return 1
        cid = hits[0].id
    else:
        cid = args.concept

    resolved = resolver.get(cid)
    if resolved is None:
        print(
            f"could not resolve concept {cid!r}"
            + ("" if kb else " (no ZIM configured — Wikipedia ids need the KB)"),
            file=sys.stderr,
        )
        return 1

    fields: dict[str, object] = {}
    if args.address:
        fields["address"] = args.address
    if args.quote:
        fields["quote"] = args.quote
    if args.occurrence is not None:
        fields["occurrence"] = args.occurrence
    if resolved.label:
        fields["label"] = resolved.label
    if resolved.url:
        fields["url"] = resolved.url
    fields["concept"] = resolved.id

    scope = "mention" if args.address else "aboutness"
    if args.dry_run:
        print(f"[dry-run] would add a {scope} concept block to {record_id}:")
        for k, v in fields.items():
            print(f"    {k}: {v}")
        return 0

    records.append_context_block(post, namespace="concept", id="concept", fields=fields)
    records.dump(post, record_file)
    print(f"linked {scope} concept {resolved.id} ({resolved.label}) → {record_id}")
    return 0
