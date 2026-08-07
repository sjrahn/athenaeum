"""The §89 rail restoration — `corpus home-rail` (ATH-CORPUS 3.5's framing restoration, and
the additive half of the §12.27 sweep; `corpus drop-retired` is the subtractive half).

Renders each `relation/related-information` entry as a markdown link, grouped by the rail's
own addresses, into a trailing `<!--section index-->` — joining the crumb's span where one
exists, appending a new one otherwise. Leaves the `relation` blocks exactly where they are:
their removal belongs to `drop-retired`, whose hold releases once the span claims the address.
Dry-run by default: `--apply` writes.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from corpus import home_rail, records
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
    # Hold reasons grouped by their FIRST clause: a per-record reason names the record's own
    # addresses and counts, so the raw strings never group. The verb's value in a dry run is
    # "how many records, for how many distinct reasons", and that needs the reason class.
    reasons: Counter[str] = Counter()
    try:
        for record_file in files:
            try:
                report = home_rail.home_rail_record(record_file, corpus_root)
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
                entries = report.counts["entries rendered"]
                addresses = report.counts["addresses"]
                print(
                    f"     {report.record_id[:12]}: would restore {entries} entr"
                    f"{'y' if entries == 1 else 'ies'} across {addresses} address(es)"
                )
            if args.limit is not None and changed >= args.limit:
                print(f"-- stopping at --limit {args.limit}")
                break
    finally:
        if manifest:
            manifest.close()

    verb = "restored" if args.apply else "would restore"
    print(f"\n{verb} the rail on {changed} record(s)")
    for key, count in sorted(totals.items()):
        print(f"  {key}: {count}")
    print(f"  held: {held} · untouched: {skipped}")
    for reason, count in reasons.most_common():
        print(f"    hold · {count}: {reason}")
    if not args.apply and changed:
        print("\n(dry run — pass --apply to write)")
    return 1 if held else 0
