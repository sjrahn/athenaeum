#!/usr/bin/env python3
"""#88's re-segment, extended to the fleet — `corpus.resegment` driven over one corpus.

Two applied samples proved the two repairs (corpus `c50013581` — 641 segments merged across
168 records; `fbab00e5e` — 238 segments re-addressed across 193 records). This walks every
record under `<corpus-root>/records/`, plans both repairs with `corpus.resegment.plan_record`,
and — only with `--apply` — writes them, with the guards `plan_record` cannot see because they
need the whole corpus:

  R  round-trip stability — the record must already re-emit byte-identical, checked BEFORE
     this migration's own edits, since a serializer difference this pass did not cause would
     otherwise ride along under cover of the address/body change it DID make
  Z  positive landing — a neutrality gate ("no new lint findings") cannot tell "changed nothing
     harmful" from "changed nothing at all"; this migration's own first run reported 641 merges
     while writing zero bytes and passed exactly such a gate. So every applied record is
     asserted to have dropped EXACTLY the expected number of leaf segments and to still contain
     every merged member's own text, or it is reverted rather than trusted.

Ledger exposure is checked with `--ledger-root`: any address a fact cites is held, never moved,
however tight its container — the ledger's citations are JSON, not markdown (688 of 1,185 fact
files carry one), so both extensions are walked.

Usage:
    resegment_88.py --corpus-root /path/to/corpus [--ledger-root /path/to/ledger] [--apply]
        [--limit N] [--json OUT]
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path
from typing import Any

from corpus import lint, records, segments, touches
from corpus.resegment import TOUCH_ID, apply_record, plan_record

_CITE = re.compile(r"corpus://([0-9a-f]{64})\?([^\s\"'\)\]\\]+)")


def ledger_citations(ledger_root: Path | None) -> dict[str, set[str]]:
    """`record id -> {addresses it cites}`, over `*.json` AND `*.md` — the ledger's facts are
    JSON (1,185 files, 688 with citations); a markdown-only walk once reported zero exposure
    for an authored fleet change that had 152 live citations."""
    out: dict[str, set[str]] = collections.defaultdict(set)
    if ledger_root is None or not ledger_root.is_dir():
        return out
    for ext in ("*.json", "*.yaml", "*.yml", "*.md"):
        for p in ledger_root.rglob(ext):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in _CITE.finditer(text):
                out[m.group(1)].add(m.group(2))
    return out


def member_rendered_count(post: Any, blocks: list, corpus_root: Path) -> int:
    findings = lint.lint(post, blocks, corpus_root)
    return sum(1 for f in findings if f.rule_id == "member-rendered-on-parent")


def run(
    corpus_root: Path, *, ledger_root: Path | None, apply: bool, limit: int | None
) -> tuple[dict[str, Any], list[str]]:
    cited_by_record = ledger_citations(ledger_root)
    print(f"ledger cites addresses in {len(cited_by_record)} record(s)"
          f"{' (no ledger given)' if ledger_root is None else ''}\n")

    verdict: collections.Counter = collections.Counter()
    holds_total: collections.Counter = collections.Counter()
    before_total = after_total = 0
    before_records = after_records = 0
    touched: list[str] = []
    manifest: dict[str, Any] = {}
    scanned = 0

    for path in sorted(corpus_root.joinpath("records").rglob("*.md")):
        try:
            post = records.load(path)
        except Exception as exc:
            verdict["skipped (unparseable record)"] += 1
            print(f"  ! {path.name}: {exc}", file=sys.stderr)
            continue
        try:
            blocks = list(segments.iter_blocks(post.content or ""))
        except ValueError as exc:
            verdict["skipped (content zone does not parse)"] += 1
            print(f"  ! {path.name}: {exc}", file=sys.stderr)
            continue

        before_n = member_rendered_count(post, blocks, corpus_root)
        if before_n:
            before_total += before_n
            before_records += 1

        rid = str(post.metadata.get("id") or "")
        art = corpus_root / "artifacts" / rid[:2] / f"{rid}.html"
        plan = plan_record(
            post, art, blocks, cited=frozenset(cited_by_record.get(rid, ()))
        )
        for reason, n in plan.holds.items():
            holds_total[reason] += n

        if plan.skipped:
            verdict["skipped: " + plan.skipped] += 1
            after_total += before_n
            if before_n:
                after_records += 1
            continue
        if plan.refused:
            verdict["REFUSED: " + plan.refused] += 1
            after_total += before_n
            if before_n:
                after_records += 1
            continue
        if not plan.merges and not plan.retargets:
            verdict["held (every candidate has a named hold)"] += 1
            after_total += before_n
            if before_n:
                after_records += 1
            continue

        scanned += 1
        # ---- guard R: round-trip stability, checked on the ACTUAL write path. This migration
        # re-emits the whole content zone, so a record whose parse -> dumps is not identity
        # would silently acquire unrelated edits under cover of the ones this pass intends.
        raw = path.read_text(encoding="utf-8")
        if records.dumps(post) != raw:
            verdict["REFUSED: record is not round-trip stable"] += 1
            after_total += before_n
            if before_n:
                after_records += 1
            continue

        # snapshot BEFORE apply_record mutates `blocks` — the positive-landing check below
        # needs both ends of the change, and `blocks` only exists in its pre-apply shape now.
        before_n_leaves = len(list(segments.leaf_segments(blocks)))
        expect_drop = plan.expected_leaf_drop

        ok, problems = apply_record(plan, blocks)
        if not ok:
            verdict["REFUSED (lossless check)"] += 1
            for p in problems:
                print(f"  ! {rid[:12]}: {p}", file=sys.stderr)
            after_total += before_n
            if before_n:
                after_records += 1
            continue

        post.content = segments.emit(blocks)

        # ---- guard Z: POSITIVE landing. A neutrality gate cannot distinguish "changed
        # nothing harmful" from "changed nothing at all" — this migration's own first run
        # proved that by reporting 641 merges while writing nothing. Assert the leaf count
        # fell by EXACTLY the expected amount, that every merged member's text survived, and
        # that every retargeted address actually landed.
        after_leaves = list(segments.leaf_segments(segments.iter_blocks(post.content or "")))
        if before_n_leaves - len(after_leaves) != expect_drop:
            verdict[f"REFUSED (expected -{expect_drop} leaves, "
                    f"got -{before_n_leaves - len(after_leaves)})"] += 1
            continue
        merged_ok = all(
            any((m.body or "").strip() in (seg.body or "") for seg in after_leaves)
            for g in plan.merges
            for m in g.members
        )
        if not merged_ok:
            verdict["REFUSED (a merged member's body is not in the emitted record)"] += 1
            continue
        retarget_ok = all(
            any(r.new_address in segments._iter_addr_strings(seg.address or "")
                for seg in after_leaves)
            for r in plan.retargets
        )
        if not retarget_ok:
            verdict["REFUSED (a retargeted address is absent after emit)"] += 1
            continue

        after_n = member_rendered_count(post, blocks, corpus_root)
        after_total += after_n
        if after_n:
            after_records += 1

        verdict["records changed"] += 1
        verdict["segments merged away"] += sum(len(g.members) - 1 for g in plan.merges)
        verdict["segments retargeted"] += len(plan.retargets)
        manifest[rid] = {
            "merges": [{"address": g.address, "from": [m.address for m in g.members]}
                       for g in plan.merges],
            "retargets": [{"from": r.old_address, "to": r.new_address}
                          for r in plan.retargets],
        }
        if apply:
            touches.record_touch(post, TOUCH_ID)
            path.write_text(records.dumps(post), encoding="utf-8")
            touched.append(rid)

        if limit and scanned >= limit:
            break

    print(f"{'APPLIED' if apply else 'DRY RUN'}\n")
    for k, v in verdict.most_common():
        print(f"   {k:56} {v}")
    print("\nholds (segment-level, named reasons only):")
    for k, v in holds_total.most_common():
        print(f"   {k:66} {v}")
    print(f"\nmember-rendered-on-parent: {before_total} -> {after_total} "
          f"({before_records} -> {after_records} records)")
    if touched:
        print(f"\n{len(touched)} record(s) written")
    return manifest, touched


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus-root", required=True, type=Path)
    ap.add_argument("--ledger-root", type=Path, default=None,
                    help="checked for citations before any address is moved; omit to skip "
                         "the check (NOT recommended against a real corpus)")
    ap.add_argument("--apply", action="store_true", help="write. Without it, nothing is written.")
    ap.add_argument("--limit", type=int, default=None, help="stop after N changed records")
    ap.add_argument("--json", type=Path, default=None, help="write the manifest here")
    args = ap.parse_args(argv)

    if not (args.corpus_root / "records").is_dir():
        print(f"{args.corpus_root}: no records/ directory — not a corpus root?", file=sys.stderr)
        return 2
    if args.ledger_root is None:
        print("WARNING: no --ledger-root given — ledger exposure will NOT be checked",
              file=sys.stderr)

    manifest, _touched = run(
        args.corpus_root, ledger_root=args.ledger_root, apply=args.apply, limit=args.limit
    )
    if args.json:
        args.json.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        print(f"\nmanifest -> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
