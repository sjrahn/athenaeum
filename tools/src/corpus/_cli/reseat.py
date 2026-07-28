"""The §12.30 placement migration — `corpus reseat` (ATH-CORPUS 3.8).

Moves a member's representation onto the member's own record and leaves a `placement` behind
(§4.3.2.4): for every member a record positions in its body, promote it if it has no record,
re-seat its renderings onto the leaf at the leaf's own address, and replace the parent's marker
and/or transcription with one placement. Dry-run by default: `--apply` writes.

The dry run is not cheap and is not meant to be — it streams and blake3-verifies every member
against its roster row, because a promoted `id` that is not the member's true hash is the one
error here that cannot be undone. What it does avoid is re-parsing: one artifact parse serves
all of a record's members, so a 214-member page reads its bytes once, not 214 times.

`--manifest` writes one JSON line per considered record: which members were promoted, which
renderings moved and to what address, which leaves already agreed (the dedup win), and every
hold with its reason. Holds are the interesting output — two parents disagreeing about one set
of bytes is a judgment this verb refuses to make.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from corpus import records, reseat
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
        help="write the parent rewrites and the leaf records (default is a dry run that "
             "verifies every member hash and writes nothing).",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        metavar="PATH",
        help="write one JSON line per considered record (promotions, re-seats, holds).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="stop after N records that would change — for a bounded pilot.",
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
    totals: Counter[str] = Counter()
    changed = held = skipped = 0
    leaves_minted = 0

    try:
        for record_file in files:
            report = reseat.reseat_record(record_file, corpus_root)
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
                            "leaves": [
                                {
                                    "id": leaf.record_id,
                                    "outcome": leaf.outcome,
                                    "media_type": leaf.media_type,
                                    "address": leaf.address,
                                    "segments_moved": leaf.segments_moved,
                                    "positions": leaf.positions,
                                }
                                for leaf in report.leaves
                            ],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            if report.hold:
                held += 1
                print(f"HOLD {report.record_id[:12]}: {report.hold}")
                continue
            if report.skipped:
                skipped += 1
                continue
            if not report.changed:
                skipped += 1
                continue
            changed += 1
            totals.update(report.counts)
            new_leaves = [leaf for leaf in report.leaves if leaf.new_text is not None]
            leaves_minted += len(new_leaves)
            if args.apply:
                for leaf in new_leaves:
                    path = corpus_root / leaf.relpath
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(leaf.new_text or "", encoding="utf-8")
                record_file.write_text(report.new_text or "", encoding="utf-8")
            else:
                detail = ", ".join(f"{k} {v}" for k, v in sorted(report.counts.items()))
                print(f"     {report.record_id[:12]}: {detail}")
            if args.limit is not None and changed >= args.limit:
                print(f"-- stopping at --limit {args.limit}")
                break
    finally:
        if manifest:
            manifest.close()

    verb = "reseated" if args.apply else "would reseat"
    print(f"\n{verb} {changed} record(s); {leaves_minted} member record(s) written")
    for key, count in sorted(totals.items()):
        print(f"  {key}: {count}")
    print(f"  held: {held} · untouched: {skipped}")
    if not args.apply and changed:
        print("\n(dry run — pass --apply to write)")
    return 1 if held else 0
