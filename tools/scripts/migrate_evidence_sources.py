#!/usr/bin/env python3
"""Migrate claim evidence from the inline-`uri` shape to the per-fact sources
table (`spec/ledger.md` §6 amendment — the per-fact `sources` table replacing
`{uri, quote, note, kind, verified}` with `{source, anchor?, quote?, note?,
kind?}` evidence entries citing a fact-level `sources` mapping).

For every fact file under `--ledger-root/facts/*/*.json`:

- every claim's evidence entries are grouped by citation TARGET (a corpus
  record hash, or a `ref://` dataset/id) in first-citation order across the
  whole file;
- a source key `s1`, `s2`, … is minted per distinct target, reused for every
  repeat citation of that target within the fact (this is the deduplication
  the table exists for);
- when entries citing the SAME target carry DIFFERING `verified` stamps, the
  newest (by `at`) is kept on the sources entry and the discrepancy is noted
  on stderr;
- each evidence entry rewrites to `{source, anchor?, quote?, note?, kind?}`,
  dropping the inline `uri` and its own `verified`;
- the fact-level `sources` table is inserted immediately before `claims`
  (existing key order is otherwise preserved, matching the file's current
  2-space/trailing-newline JSON convention).

Roster `artifacts[].uri` and interpretation `based_on` are NOT touched — the
design amendment scopes the sources table to claim evidence only.

Idempotent: a file with no inline-`uri` evidence entries is left byte-for-byte
untouched, so a second run is a no-op.

Run from the tool venv (the `ledger` package is installed editable):

    cd tools && uv run --no-sync python scripts/migrate_evidence_sources.py \\
        --ledger-root /path/to/ledger [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ledger.model import CORPUS_URI_RE, REF_URI_RE

Target = tuple[str, str]  # ("record", hash) | ("ref", "dataset/id")


def _target_of(uri: str) -> tuple[Target | None, str]:
    """A legacy inline `uri` → (target, anchor). A query-param tail (`?el=3`)
    loses its leading `?`; a fragment tail (`#name`) keeps its `#` — it's a
    different addressing form, not a query (see `ledger.model.derived_uri`)."""
    m = CORPUS_URI_RE.match(uri)
    if m:
        tail = m.group(2) or ""
        anchor = tail[1:] if tail[:1] == "?" else tail
        return ("record", m.group(1)), anchor
    m = REF_URI_RE.match(uri)
    if m:
        # group(2) is the optional pinned tag (§6.5) — preserve it in the target.
        pin = f"@{m.group(2)}" if m.group(2) else ""
        return ("ref", f"{m.group(1)}{pin}/{m.group(3)}"), ""
    return None, ""


def migrate_fact(fact: dict, *, where: str) -> bool:
    """Rewrite *fact*'s claim evidence in place. Returns True iff it changed —
    a file with no inline-`uri` evidence is left untouched (idempotence)."""
    changed = False
    order: list[Target] = []          # first-citation order
    keys: dict[Target, str] = {}
    verified: dict[Target, dict] = {}

    def key_for(target: Target) -> str:
        key = keys.get(target)
        if key is None:
            key = f"s{len(keys) + 1}"
            keys[target] = key
            order.append(target)
        return key

    def hoist_verified(target: Target, v: dict) -> None:
        prev = verified.get(target)
        if prev is None:
            verified[target] = v
            return
        if prev == v:
            return
        newer = v if str(v.get("at", "")) >= str(prev.get("at", "")) else prev
        older = prev if newer is v else v
        print(f"{where}: source for {target[0]} {target[1][:12]}… carries "
              f"differing verified stamps — keeping {newer} over {older}",
              file=sys.stderr)
        verified[target] = newer

    for claim in fact.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        for e in claim.get("evidence") or []:
            if not isinstance(e, dict) or "uri" not in e:
                continue
            changed = True
            uri = str(e.pop("uri"))
            target, anchor = _target_of(uri)
            v = e.pop("verified", None)
            if target is None:
                # unparseable inline uri — drop it bare; `ath ledger check`
                # flags the resulting sourceless entry same as any other
                # malformed evidence (parse tolerantly, author strictly)
                continue
            e["source"] = key_for(target)
            if anchor:
                e["anchor"] = anchor
            if isinstance(v, dict):
                hoist_verified(target, v)

    if not changed:
        return False

    sources: dict[str, dict] = {}
    for target in order:
        kind, value = target
        entry: dict = {"record": value} if kind == "record" else {"ref": value}
        v = verified.get(target)
        if v is not None:
            entry["verified"] = v
        sources[keys[target]] = entry

    # land `sources` immediately before `claims` — fact-level, sibling of
    # "claims" (the design amendment's placement) — every other key's
    # relative order is preserved untouched
    rebuilt: dict = {}
    for k, v in fact.items():
        if k == "claims":
            rebuilt["sources"] = sources
        rebuilt[k] = v
    fact.clear()
    fact.update(rebuilt)
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ledger-root", required=True, type=Path,
                    help="the ledger repo root (holding facts/, interpretations/, …)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change; write nothing")
    args = ap.parse_args(argv)

    base = args.ledger_root
    if not (base / "facts").is_dir():
        print(f"{base}: no facts/ directory — not a ledger root?", file=sys.stderr)
        return 2

    n_files = n_changed = n_errors = 0
    for f in sorted(base.glob("facts/*/*.json")):
        n_files += 1
        try:
            text = f.read_text(encoding="utf-8")
            fact = json.loads(text)
        except (json.JSONDecodeError, OSError) as e:
            print(f"{f.relative_to(base)}: skipped — invalid JSON ({e})", file=sys.stderr)
            n_errors += 1
            continue
        where = str(f.relative_to(base))
        if migrate_fact(fact, where=where):
            n_changed += 1
            if args.dry_run:
                print(f"{where}: would migrate")
            else:
                f.write_text(json.dumps(fact, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")

    suffix = " (dry run — nothing written)" if args.dry_run else ""
    print(f"{n_changed} of {n_files} fact files migrated{suffix}"
          + (f"; {n_errors} unparseable, skipped" if n_errors else ""), file=sys.stderr)
    return 1 if n_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
