"""`ath ledger` — the ledger's deterministic surface.

Everything resolves through the manifest: the ledger member's path, the
registered corpora (with declared visibility) the ledger interprets, and the
reference datasets `ref://` citations may name. There is deliberately no bare
`ledger` command.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

from ath.manifest import ManifestError, Member, find_root, load, load_references
from ledger.corpora import CorpusJoin, RegisteredCorpus

_USAGE = """\
usage: ath ledger <command> [options...]

The ledger's deterministic surface (spec/ledger.md).

Commands:
  check         the validation contract (§13.1) — rc 1 on errors
  verify        evidence-content verification (§13.2): anchors resolve,
                quotes match verbatim; --stamp writes snapshot bindings
  harvest       run the mechanical minting rules (harvest/*.yaml, §10):
                strip auto output, sweep the corpora, re-mint
  promote ID    move a hypothesis's proposed claim into its fact (§7.2)
  stamp ID      (re-)pin a correction's challenge to the claim state (§7.3)
  supersede OLD NEW  rewrite corpus citations old→new on re-capture, gated by
                content continuity; --retire reclaims the old bytes (§13.3)
  worklist REF  dependents to revisit — REF is a fact id, a corpus hash,
                or an invariant id
  regen         rewrite the generated views (VOCAB.md, the open-questions
                block; --coverage additionally sweeps corpora for coverage.md)

All commands resolve the ledger, corpora, and reference datasets through the
manifest (athenaeum.yaml, walked up from the current directory; --root to
point elsewhere).
"""


def _base_parser(prog: str, description: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=prog, description=description)
    ap.add_argument("--root", type=Path, default=None,
                    help="orchestrator repo root (default: walk up for athenaeum.yaml)")
    return ap


def _system(root: Path | None) -> tuple[Path, CorpusJoin, set[str]]:
    """(ledger root, corpus join, registered dataset names) from the manifest."""
    base = find_root(root)
    members = load(base)
    ledgers = [m for m in members if m.layer == "ledger"]
    if not ledgers:
        raise ManifestError("no ledger registered in the manifest")
    ledger = ledgers[0]
    if not (ledger.path / "ledger.yaml").is_file():
        raise ManifestError(f"{ledger.path} has no ledger.yaml — run `ath sync`?")
    manifest_corpora: dict[str, Member] = {m.name: m for m in members if m.layer == "corpora"}
    declared = yaml.safe_load(
        (ledger.path / "ledger.yaml").read_text(encoding="utf-8")
    ) or {}
    names = declared.get("corpora") or []
    if not isinstance(names, list) or not names:
        raise ManifestError("ledger.yaml corpora: must list the corpora this ledger "
                            "interprets")
    registered: list[RegisteredCorpus] = []
    for name in names:
        m = manifest_corpora.get(str(name))
        if m is None:
            raise ManifestError(f"ledger.yaml names corpus {name!r} which the manifest "
                                "does not register")
        registered.append(
            RegisteredCorpus(name=m.name, root=m.path, private=m.visibility == "private")
        )
    datasets = {r.dataset for r in load_references(base)}
    return ledger.path, CorpusJoin(registered), datasets


def _cmd_check(argv: Sequence[str]) -> int:
    ap = _base_parser("ath ledger check", "Validate the ledger (spec/ledger.md §13.1).")
    ap.add_argument("--no-corpus", action="store_true",
                    help="skip the corpus join (resolution/status/sensitivity checks)")
    ns = ap.parse_args(list(argv))
    ledger_root, join, datasets = _system(ns.root)
    from ledger.check import run_check

    rep = run_check(ledger_root, join, datasets, no_corpus=ns.no_corpus)
    for n in rep.notes:
        print(f"note: {n}")
    for w in rep.warnings:
        print(f"WARN  {w}")
    for e in rep.errors:
        print(f"ERROR {e}")
    print(f"\n{rep.counts.get('facts', 0)} fact files, "
          f"{rep.counts.get('claims', 0)} claims, "
          f"{rep.counts.get('interpretations', 0)} interpretations — "
          f"{len(rep.errors)} errors, {len(rep.warnings)} warnings")
    return 0 if rep.ok else 1


def _cmd_regen(argv: Sequence[str]) -> int:
    ap = _base_parser("ath ledger regen",
                      "Rewrite the generated views (VOCAB.md, open-questions block).")
    ap.add_argument("--coverage", action="store_true",
                    help="also regenerate coverage.md (sweeps every corpus record)")
    ns = ap.parse_args(list(argv))
    ledger_root, join, _ = _system(ns.root)
    from ledger import views
    from ledger.model import load_json_dir
    from ledger.schemas import load_schemas

    facts, _ = load_json_dir(ledger_root, "facts/*/*.json")
    interps, _ = load_json_dir(ledger_root, "interpretations/*.json")
    schemas, _ = load_schemas(ledger_root)
    (ledger_root / views.VOCAB_PATH).write_text(
        views.fresh_vocab(ledger_root, facts), encoding="utf-8"
    )
    print(f"wrote {views.VOCAB_PATH}")
    fresh = views.fresh_openq(ledger_root, facts, interps, schemas)
    if fresh is None:
        print(f"{views.OPENQ_PATH}: markers missing — block not written", file=sys.stderr)
        return 1
    (ledger_root / views.OPENQ_PATH).write_text(fresh, encoding="utf-8")
    print(f"wrote the generated block in {views.OPENQ_PATH}")
    if ns.coverage:
        from ledger.coverage import COVERAGE_PATH, render_coverage

        (ledger_root / COVERAGE_PATH).write_text(
            render_coverage(ledger_root, join.corpora), encoding="utf-8"
        )
        print(f"wrote {COVERAGE_PATH}")
    return 0


def _cmd_verify(argv: Sequence[str]) -> int:
    ap = _base_parser("ath ledger verify",
                      "Verify evidence content: anchors + verbatim quotes (§13.2).")
    ap.add_argument("ids", nargs="*", help="fact ids to verify (default: all)")
    ap.add_argument("--stamp", action="store_true",
                    help="write snapshot-binding stamps on passing evidence")
    ns = ap.parse_args(list(argv))
    ledger_root, join, datasets = _system(ns.root)
    from datetime import date

    from ledger.verify import verify_ledger

    res = verify_ledger(ledger_root, join, datasets, stamp=ns.stamp,
                        only_ids=set(ns.ids) or None,
                        today=date.today().isoformat())
    for n in res.notes:
        print(f"note: {n}")
    for w in res.warnings:
        print(f"WARN  {w}")
    for e in res.errors:
        print(f"ERROR {e}")
    scoped = (f" ({res.record_scoped} record-scoped: anchor unresolvable, "
              "quote found record-wide)" if res.record_scoped else "")
    print(f"\n{res.verified} verified{scoped}, {res.unverifiable} unverifiable, "
          f"{res.stamped} stamped — {len(res.errors)} errors, "
          f"{len(res.warnings)} warnings")
    return 0 if res.ok else 1


def _cmd_harvest(argv: Sequence[str]) -> int:
    ap = _base_parser("ath ledger harvest",
                      "Strip auto output, sweep the corpora, re-mint (§10).")
    ns = ap.parse_args(list(argv))
    ledger_root, join, _ = _system(ns.root)
    from ledger.harvest import run_harvest

    run = run_harvest(ledger_root, join.corpora)
    for n in run.notes:
        print(f"note: {n}")
    print(f"stripped {run.stripped_files} auto files + {run.stripped_entries} entries; "
          f"{run.matched_records} record matches → {run.minted} concepts minted, "
          f"{run.rostered} rostered, {run.claimed} claims")
    print("run `ath ledger regen && ath ledger check` to refresh views and validate")
    return 0


def _cmd_promote(argv: Sequence[str]) -> int:
    ap = _base_parser("ath ledger promote", "Promote a claim-shaped hypothesis (§7.2).")
    ap.add_argument("id")
    ns = ap.parse_args(list(argv))
    ledger_root, _, _ = _system(ns.root)
    from ledger.promote import PromoteError, promote

    try:
        landed = promote(ledger_root, ns.id)
    except PromoteError as e:
        print(f"ath ledger promote: {e}", file=sys.stderr)
        return 1
    print(f"promoted → {landed}")
    return 0


def _cmd_stamp(argv: Sequence[str]) -> int:
    ap = _base_parser("ath ledger stamp", "(Re-)pin a correction's challenge (§7.3).")
    ap.add_argument("id")
    ns = ap.parse_args(list(argv))
    ledger_root, _, _ = _system(ns.root)
    from ledger.promote import PromoteError, stamp

    try:
        state = stamp(ledger_root, ns.id)
    except PromoteError as e:
        print(f"ath ledger stamp: {e}", file=sys.stderr)
        return 1
    print(f"pinned {ns.id} → {state}")
    return 0


def _cmd_worklist(argv: Sequence[str]) -> int:
    ap = _base_parser("ath ledger worklist",
                      "Dependents to revisit for a fact id / corpus hash / invariant.")
    ap.add_argument("ref")
    ns = ap.parse_args(list(argv))
    ledger_root, _, _ = _system(ns.root)
    from ledger.worklist import worklist

    rows = worklist(ledger_root, ns.ref)
    for row in rows:
        print(row)
    print(f"\n{len(rows)} dependents")
    return 0


def _cmd_supersede(argv: Sequence[str]) -> int:
    ap = _base_parser("ath ledger supersede",
                      "Rewrite corpus citations old→new when a record is re-captured (§13.3).")
    ap.add_argument("old", help="the superseded record hash")
    ap.add_argument("new", help="the replacement record hash")
    ap.add_argument("--retire", action="store_true",
                    help="reclaim the old record's bytes (corpus rm) once no diverged "
                         "citation still references it")
    ns = ap.parse_args(list(argv))
    ledger_root, join, _ = _system(ns.root)
    from ledger.supersede import supersede

    res = supersede(ledger_root, ns.old, ns.new, join, retire=ns.retire)
    if not res.ok:
        print(f"ath ledger supersede: {res.note}", file=sys.stderr)
        return 2
    for rw in res.rewrites:
        print(f"rewrote  {rw.fact}: {rw.old_uri[:20]}… → corpus://{res.new[:12]}…")
    for dv in res.divergences:
        print(f"DIVERGED {dv.fact}: {dv.uri[:20]}… [{dv.address}] — left as-is, re-anchor it")
    if res.retired:
        print(f"retired old record {res.old[:12]}… (bytes reclaimed)")
    if res.note:
        print(f"note: {res.note}")
    print(
        f"\n{len(res.rewrites)} citation(s) rewritten across {len(res.facts_touched)} fact(s), "
        f"{len(res.divergences)} diverged"
    )
    # A leftover divergence is a real problem to resolve; signal it non-zero.
    return 1 if res.divergences else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(_USAGE, end="")
        return 0
    cmd, rest = args[0], args[1:]
    handlers = {
        "check": _cmd_check,
        "regen": _cmd_regen,
        "verify": _cmd_verify,
        "harvest": _cmd_harvest,
        "promote": _cmd_promote,
        "stamp": _cmd_stamp,
        "worklist": _cmd_worklist,
        "supersede": _cmd_supersede,
    }
    try:
        if cmd in handlers:
            return handlers[cmd](rest)
    except ManifestError as e:
        print(f"ath ledger: {e}", file=sys.stderr)
        return 2
    print(f"ath ledger: unknown command {cmd!r}", file=sys.stderr)
    print("Run 'ath ledger --help' to see available commands.", file=sys.stderr)
    return 2
