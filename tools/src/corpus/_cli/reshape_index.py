"""#164's mechanical index drain — `corpus reshape-index`.

Re-authors my.alldata.com's index template from the artifact DOM: the page title as a
structural byte-mark, the entry list with its links preserved, and the breadcrumb verbatim in
a trailing `form/nav` span. Every rewrite must pass the round-trip, lint-neutrality and #159
fidelity gates before it counts as changed (`corpus.reshape_index`). Dry-run by default:
`--apply` writes.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from corpus import records, reshape_index
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "target",
        nargs="*",
        default=None,
        help="record ids (hash / hex prefix / path); `-` reads ids from stdin; omit to sweep "
             "the whole corpus.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the rewrites (default is a dry run that reports and writes nothing).",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        metavar="PATH",
        help="write one JSON line per considered record (changed / skipped / held, and why).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="stop after this many CHANGED records (a staged fleet run).",
    )
    add_corpus_root_arg(parser)


def _targets(args: argparse.Namespace, corpus_root: Path) -> list[Path]:
    from corpus import paths

    raw: list[str] = []
    for token in args.target or []:
        if token == "-":
            raw.extend(tok for tok in sys.stdin.read().split() if tok)
        else:
            raw.append(token)
    if not raw:
        return sorted(records.iter_record_paths(corpus_root))
    return [paths.resolve_record(corpus_root, t)[1] for t in raw]


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    try:
        files = _targets(args, corpus_root)
    except (ValueError, FileNotFoundError) as exc:
        sys.exit(str(exc))

    manifest = None
    if args.manifest:
        manifest_path = Path(args.manifest)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = manifest_path.open("w", encoding="utf-8")

    changed = held = skipped = 0
    totals: Counter[str] = Counter()
    # Hold reasons grouped by their FIRST clause — a per-record reason names that record's own
    # counts and samples, so raw strings never group; the dry run's value is "how many
    # records, for how many distinct reasons".
    reasons: Counter[str] = Counter()
    try:
        for record_file in files:
            try:
                report = reshape_index.reshape_record(record_file, corpus_root)
            except Exception as exc:  # tolerant sweep: one bad record never stops the fleet
                print(f"  ERROR {record_file.stem[:12]}: {exc}", file=sys.stderr)
                held += 1
                reasons["engine error"] += 1
                if manifest:
                    manifest.write(
                        json.dumps({"record": record_file.stem, "hold": f"engine error: {exc}"})
                        + "\n"
                    )
                continue

            if manifest:
                manifest.write(
                    json.dumps(
                        {
                            "record": report.record_id,
                            "relpath": report.relpath,
                            "changed": report.changed,
                            "skipped": report.skipped,
                            "hold": report.hold,
                            "counts": dict(report.counts),
                        }
                    )
                    + "\n"
                )

            if report.hold:
                held += 1
                reasons[report.hold.split(" (")[0].split(" — ")[0][:110]] += 1
                print(f"  HOLD {report.record_id[:12]}: {report.hold}", file=sys.stderr)
                continue
            if report.skipped or not report.changed:
                skipped += 1
                continue
            changed += 1
            totals.update(report.counts)
            if args.apply and report.new_text is not None:
                record_file.write_text(report.new_text, encoding="utf-8")
            else:
                print(
                    f"     {report.record_id[:12]}: would re-author "
                    f"{report.counts['segments']} segment(s)"
                )
            if args.limit is not None and changed >= args.limit:
                print(f"-- stopping at --limit {args.limit}")
                break
    finally:
        if manifest:
            manifest.close()

    verb = "re-authored" if args.apply else "would re-author"
    print(f"\n{verb} {changed} record(s); {held} held, {skipped} skipped")
    if reasons:
        print("holds by reason:")
        for reason, n in reasons.most_common():
            print(f"  {n:5}  {reason}")
    if not args.apply and changed:
        print("(dry run — nothing written; re-run with --apply)")
    return 0
