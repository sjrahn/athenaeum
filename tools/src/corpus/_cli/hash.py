"""`corpus hash` — verbs over the derived hash index / record `hash:` field (spec §2,
§7.9, §12.9.1).

Subcommands:

- `flush <ids…|--all> [--recipes id,…]` — THE one deliberate write of index-only
  identity-class values into records' frontmatter `hash:` field (§12.9.1's flush
  bullet). Never automatic, never touches bytes. Similarity-class values (§7.9) and
  index rows under an unregistered recipe id are skipped and reported, never
  silently dropped or silently written.
"""

from __future__ import annotations

import argparse
import sys

from corpus import hashindex, hashing, paths, records, touches
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="action", required=True, metavar="ACTION")

    p_flush = sub.add_parser(
        "flush",
        help="Write index-only identity-class hash values into records' `hash:` field.",
    )
    p_flush.add_argument(
        "targets",
        nargs="*",
        default=(),
        help="record(s) to flush (hash / hex prefix / path); omit with --all.",
    )
    p_flush.add_argument(
        "--all", action="store_true", help="flush every record in the corpus."
    )
    p_flush.add_argument(
        "--recipes",
        default=None,
        metavar="ID,...",
        help=(
            "comma-separated recipe ids to restrict the flush to (default: every "
            "identity-class recipe indexed for the record)."
        ),
    )
    add_corpus_root_arg(p_flush)


def run(args: argparse.Namespace) -> int:
    if args.action == "flush":
        return _flush(args)
    print(f"unknown action: {args.action}", file=sys.stderr)
    return 2


def _flush(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    if not args.all and not args.targets:
        sys.exit("hash flush: give one or more targets, or --all")
    if args.all and args.targets:
        sys.exit("hash flush: --all and explicit targets are mutually exclusive")

    want_recipes: set[str] | None = None
    if args.recipes:
        want_recipes = {r.strip() for r in args.recipes.split(",") if r.strip()}

    if args.all:
        record_ids = [md.stem for md in records.iter_record_paths(corpus_root)]
    else:
        record_ids = []
        for target in args.targets:
            rid, _ = paths.resolve_record(corpus_root, target)
            record_ids.append(rid)

    flushed_values = 0
    flushed_records = 0
    skipped_similarity = 0
    skipped_unknown = 0
    missing_records = 0

    with hashindex.open_index(corpus_root) as conn:
        for rid in record_ids:
            record_file = paths.record_path(corpus_root, rid)
            if not record_file.is_file():
                print(f"  skip {rid[:12]}: no such record", file=sys.stderr)
                missing_records += 1
                continue

            post = records.load(record_file)
            existing = records.record_hashes(post)
            rows = hashindex.rows_for(conn, rid)

            to_write: dict[str, str] = {}
            skipped_sim: list[str] = []
            skipped_unk: list[str] = []
            for row in rows:
                if want_recipes is not None and row.recipe not in want_recipes:
                    continue
                if row.algo in existing:
                    continue  # already on the record — zero-churn re-run
                recipe = hashing.get_recipe(row.recipe)
                if recipe is None:
                    skipped_unk.append(row.algo)
                    continue
                if recipe.comparison != "identity":
                    skipped_sim.append(row.algo)  # similarity never flushes (§7.9)
                    continue
                to_write[row.algo] = row.value

            skipped_similarity += len(skipped_sim)
            skipped_unknown += len(skipped_unk)

            if not to_write:
                if skipped_sim or skipped_unk:
                    print(
                        f"  {rid[:12]}: nothing flushed"
                        + (f" (similarity, not flushable: {', '.join(sorted(skipped_sim))})" if skipped_sim else "")
                        + (f" (unknown recipe, skipped: {', '.join(sorted(skipped_unk))})" if skipped_unk else "")
                    )
                continue  # untouched file — zero churn

            records.set_record_hashes(post, to_write)
            touches.record_touch(post, touches.script_identifier("hash.flush"))
            records.dump(post, record_file)
            flushed_records += 1
            flushed_values += len(to_write)
            print(
                f"  flushed {rid[:12]}: {', '.join(sorted(to_write))}"
                + (f" (skipped similarity: {', '.join(sorted(skipped_sim))})" if skipped_sim else "")
                + (f" (skipped unknown recipe: {', '.join(sorted(skipped_unk))})" if skipped_unk else "")
            )

    summary = (
        f"hash flush: {flushed_values} value(s) written to {flushed_records} record(s) "
        f"of {len(record_ids)} considered"
    )
    if skipped_similarity:
        summary += f"; {skipped_similarity} similarity-class value(s) skipped (never flushable)"
    if skipped_unknown:
        summary += f"; {skipped_unknown} unknown-recipe value(s) skipped"
    if missing_records:
        summary += f"; {missing_records} target(s) had no record"
    print(summary)
    return 0
