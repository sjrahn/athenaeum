"""The §12.27 field sweep — `corpus drop-retired` (ATH-CORPUS 3.5).

Removes what 3.5 retired from a record's grammar: the frontmatter `canonical:` hash, the
section header's `title:`/`description:`/`entry:`, the segment header's `description:` and
its content-segment `entry:` fossil, and the `relation`/`reference` context namespaces plus
`issue/generic-title`. Dry-run by default: `--apply` writes.

Every rewrite passes the **neutrality gate** — a record whose sweep would raise ANY lint
rule's finding count is HELD and left byte-untouched — and a record whose `relation` blocks
have no `form/index` span to have come home to is held too, because dropping those before
the restoration is data loss, not a sweep (`--allow-unrestored` for populations whose
overlay names no rail region).

`--manifest` writes one JSON line per considered record: what came out, the derived
title/description before and after, holds. The derived pair is in there because it is the
one *visible* consequence of the sweep — a formed record's title was resolving off the form
layer, and with the section fields gone it falls to the origin or artifact layer (§4.2.3).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from corpus import drop_retired, records
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "target",
        nargs="*",
        default=None,
        help="record ids (hash / hex prefix / path); `-` reads ids from stdin; omit to "
             "sweep the whole corpus.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the rewrites (default is a dry-run that reports and writes nothing).",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        metavar="PATH",
        help="write one JSON line per considered record (what came out, derived pair, holds).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="stop after this many CHANGED records (a staged fleet run).",
    )
    parser.add_argument(
        "--allow-unrestored",
        action="store_true",
        help="drop `relation` blocks even where no `form/index` span carries the rail — for "
             "populations whose origin overlay names no rail region (§7.2), never as a "
             "shortcut past the restoration.",
    )
    parser.add_argument(
        "--titles",
        action="store_true",
        help="print every record whose DERIVED title changes (the visible consequence).",
    )
    add_corpus_root_arg(parser)


def _expand(targets: list[str]) -> list[str]:
    out: list[str] = []
    for t in targets:
        if t == "-":
            out.extend(tok for tok in sys.stdin.read().split() if tok)
        else:
            out.append(t)
    return out


def run(args: argparse.Namespace) -> int:
    from corpus import paths

    corpus_root = resolved_corpus_root(args)
    targets = _expand(list(args.target or []))
    if targets:
        candidates = [paths.resolve_record(corpus_root, t)[1] for t in targets]
    else:
        candidates = sorted(records.iter_record_paths(corpus_root))

    manifest = None
    if args.manifest:
        manifest_path = Path(args.manifest)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = manifest_path.open("w", encoding="utf-8")

    changed = skipped = held = 0
    totals: Counter[str] = Counter()
    title_moves = 0
    try:
        for rf in candidates:
            try:
                report = drop_retired.sweep_record(
                    rf, corpus_root, allow_unrestored=args.allow_unrestored
                )
            except Exception as exc:  # tolerant sweep: one bad record never stops the fleet
                print(f"  ERROR {rf.stem[:12]}: {exc}", file=sys.stderr)
                held += 1
                if manifest:
                    manifest.write(
                        json.dumps({"record": rf.stem, "hold": f"engine error: {exc}"}) + "\n"
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
                            "emit_normalized": report.emit_normalized,
                            "dropped": dict(report.counts),
                            "title_before": report.title_before,
                            "title_after": report.title_after,
                            "description_before": report.description_before,
                        }
                    )
                    + "\n"
                )

            if report.hold:
                held += 1
                print(f"  HOLD {report.record_id[:12]}: {report.hold}", file=sys.stderr)
                continue
            if report.skipped:
                skipped += 1
                continue
            changed += 1
            totals.update(report.counts)
            if report.title_before != report.title_after:
                title_moves += 1
                if args.titles:
                    print(
                        f"  title {report.record_id[:12]}: "
                        f"{report.title_before!r} → {report.title_after!r}"
                    )
            if args.apply and report.new_text is not None:
                rf.write_text(report.new_text, encoding="utf-8")
            if changed % 500 == 0:
                print(f"  … {changed} records")
            if args.limit and changed >= args.limit:
                print(f"  --limit {args.limit} reached; stopping.")
                break
    finally:
        if manifest:
            manifest.close()

    verb = "swept" if args.apply else "would sweep"
    detail = ", ".join(f"{k}={v}" for k, v in sorted(totals.items())) or "none"
    print(f"{verb} {changed} record(s); {skipped} skipped, {held} held")
    print(f"  dropped: {detail}")
    print(f"  derived title changes: {title_moves}")
    return 1 if held else 0
