"""The v35 fleet remap — `corpus remap-el-ordinal` (spec §6.1.1, CHANGELOG v35).

Rewrites every stored dotted-path `el=1.3.2` / `el=1.3.[2-9]` address (and any remaining
pre-3.6 legacy `el=<N>` / `el=<N>-<M>` straggler) — content zone, member roster,
annotation zone, and origin-block lineage URIs — to its v35 document-order ordinal,
stamps `addressing: {parser, elements, scheme: ordinal}`, and appends the migration
touch. Dry-run by default: `--apply` writes.

Every produced address is verified inside the engine by re-resolving it to the identical
element the old grammar named (`corpus.remap_el_ordinal`); a record that cannot be
remapped mechanically is HELD with a reason and left byte-untouched. `--manifest` writes
one JSON line per record — mappings, form histogram, holds.

**Origin lineage URIs need the whole candidate set up front.** A promoted member leaf's
origin cites an address in its CONTAINER's space (§8.1) — mapped against the container's
tree, which must reflect the container's PRE-migration grammar regardless of whether this
sweep visits the container before or after the leaf citing it. This CLI computes every
candidate's report FIRST (no writes at all — `corpus.remap_el_ordinal.remap_record` is
pure/read-only until the caller applies `report.new_text`), sharing one
`container_pairings` cache across the whole pass so every container is read from disk
exactly once, in its original state, then applies all writes in a second pass.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from corpus import records, remap_el_ordinal
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="a single record (hash / hex prefix / path); omit to sweep the whole corpus.",
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
        help="write one JSON line per considered record (mappings, forms, holds).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="stop after this many CHANGED records (a staged fleet run).",
    )
    parser.add_argument(
        "--override",
        action="append",
        default=[],
        metavar="OLD::NEW",
        help="re-address one stored dotted/legacy address deliberately, e.g. "
             "'el=1.2.[3-9]::el=[14-22]'. Repeatable; requires a single target. This is "
             "how a HELD record is resolved: the engine holds when addresses alias under "
             "§6.1.1, and what an over-wide claim actually covers is a reading of the "
             "document, not a mapping. Everything else still migrates mechanically.",
    )
    add_corpus_root_arg(parser)


def _parse_overrides(raw: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in raw:
        old, sep, new = item.partition("::")
        if not sep or not old.strip() or not new.strip():
            raise ValueError(f"--override {item!r} is not OLD::NEW")
        out[old.strip()] = new.strip()
    return out


def run(args: argparse.Namespace) -> int:
    from corpus import paths

    corpus_root = resolved_corpus_root(args)
    try:
        overrides = _parse_overrides(args.override)
    except ValueError as exc:
        print(f"{exc}", file=sys.stderr)
        return 2
    if overrides and not args.target:
        print(
            "--override re-addresses ONE record deliberately; name the target.",
            file=sys.stderr,
        )
        return 2
    if args.target:
        _, rf = paths.resolve_record(corpus_root, args.target)
        candidates = [rf]
    else:
        candidates = sorted(records.iter_record_paths(corpus_root))

    # Pass 1 (read-only): compute every candidate's report against ONE shared
    # container-pairing cache, built lazily from whatever is currently on disk — the
    # module docstring's ordering guarantee.
    cache: dict = {}
    reports: list = []
    errors = 0
    for rf in candidates:
        try:
            report = remap_el_ordinal.remap_record(rf, corpus_root, overrides, cache)
        except Exception as exc:  # tolerant sweep: one bad record never stops the fleet
            print(f"  ERROR {rf.stem[:12]}: {exc}", file=sys.stderr)
            errors += 1
            continue
        reports.append((rf, report))

    manifest = None
    if args.manifest:
        manifest_path = Path(args.manifest)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = manifest_path.open("w", encoding="utf-8")

    changed = skipped = held = errors
    stamp_only_count = 0
    forms: dict[str, int] = {}
    addresses = 0
    try:
        for rf, report in reports:
            if manifest:
                manifest.write(json.dumps({
                    "record": report.record_id,
                    "relpath": report.relpath,
                    "changed": report.changed,
                    "skipped": report.skipped,
                    "hold": report.hold,
                    "generation": report.generation,
                    "elements": report.elements,
                    "emit_normalized": report.emit_normalized,
                    "stamp_only": report.stamp_only,
                    "forms": report.forms,
                    "mappings": report.mappings,
                    "overrides": overrides or None,
                }) + "\n")

            if report.hold:
                held += 1
                print(f"  HOLD {report.record_id[:12]}: {report.hold}", file=sys.stderr)
                continue
            if report.skipped:
                skipped += 1
                continue
            changed += 1
            if report.stamp_only:
                stamp_only_count += 1
            addresses += len(report.mappings)
            for k, v in report.forms.items():
                forms[k] = forms.get(k, 0) + v
            if args.apply and report.new_text is not None:
                rf.write_text(report.new_text, encoding="utf-8")
            if changed % 500 == 0:
                print(f"  … {changed} records, {addresses} addresses")
            if args.limit and changed >= args.limit:
                print(f"  --limit {args.limit} reached; stopping.")
                break
    finally:
        if manifest:
            manifest.close()

    verb = "remapped" if args.apply else "would remap"
    form_summary = ", ".join(f"{k}={v}" for k, v in sorted(forms.items())) or "none"
    print(
        f"{verb} {changed} record(s) / {addresses} address(es) "
        f"({form_summary}); {stamp_only_count} stamp-only (zero addresses); "
        f"{skipped} skipped, {held} held"
    )
    return 1 if held else 0
