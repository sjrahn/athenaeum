"""`ath ledger` — the ledger's deterministic surface.

Everything resolves through the instance (spec Part I §2.2): the ledger at
`ledger/`, the corpus at `corpus/` (the instance `visibility:` is the tenancy
floor), and the reference datasets `ref://` citations may name. There is
deliberately no bare `ledger` command.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from ath.manifest import ManifestError, Reference, find_root, load_instance, load_references
from ledger.corpora import CorpusJoin, RegisteredCorpus

_USAGE = """\
usage: ath ledger <command> [options...]

The ledger's deterministic surface (spec/ledger.md).

Commands:
  check         the validation contract (§13.1) — rc 1 on errors
  verify        evidence-content verification (§13.2): anchors resolve,
                quotes match verbatim; --stamp writes snapshot bindings
  resolve QUERY entity resolution before minting (#174) — id/name/alias/
                token candidates against the derived index; rc 1 on no match
  index         ensure/rebuild the derived resolution index (.cache/,
                uncommitted); --rebuild forces, --stats prints counts
  demands [ID]  the completeness rule layer (§14): a fact's demands with
                state visible (OPEN/BLOCKED/SATISFIED — satisfied hidden
                unless --all); --draft PATH evaluates a fact file not yet
                landed in the tree; no ID prints a ledger-wide per-rule
                summary. Never errors on open demands (rc 0 regardless).
  dedupe        coalescence proposer (#177) — candidate duplicate concepts/
                edges, near-duplicate predicates, dead schema surface;
                READ-ONLY, proposes only, never merges/writes; --json,
                --section concepts|predicates|schemas; --review [PATH]
                writes the concepts section as a self-contained HTML
                judgment page (#182) instead of printing it (default path
                <ledger>/.cache/dedupe-review.html)
  harvest       run the mechanical minting rules (harvest/*.yaml, §10):
                strip auto output, sweep the corpora, re-mint
  promote ID    move a hypothesis's proposed claim into its fact (§7.2)
  stamp ID      (re-)pin a correction's challenge to the claim state (§7.3)
  supersede OLD NEW  rewrite corpus citations old→new on re-capture, gated by
                content continuity; --retire reclaims the old bytes (§13.3)
  merge LOSER SURVIVOR  merge LOSER into SURVIVOR (#176, §4.1): claims re-key
                (shorts preserved, collisions renamed), sources unify,
                references rewrite ledger-wide, lineage row added, loser
                file deleted; dry-run by default, --apply executes, --json
                for the plan
  remap-el      §12.28 addressing remap for evidence anchors: legacy el=N →
                child-index paths, mapped against the artifacts (dry-run by
                default; --apply writes)
  worklist REF  dependents to revisit — REF is a fact id, a corpus hash,
                or an invariant id
  regen         rewrite the generated views (VOCAB.md, the open-questions
                block; --coverage additionally sweeps corpora for coverage.md)

All commands resolve the ledger, corpus, and reference datasets through the
instance config (athenaeum.yaml, walked up from the current directory; --root
to point elsewhere).
"""


def _base_parser(prog: str, description: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=prog, description=description)
    ap.add_argument("--root", type=Path, default=None,
                    help="instance root (default: walk up for athenaeum.yaml; "
                         "$ATHENAEUM_ROOT overrides)")
    return ap


def _system(root: Path | None) -> tuple[Path, CorpusJoin, dict[str, Reference]]:
    """(ledger root, corpus join, registered datasets by name) from the instance."""
    base = find_root(root)
    instance = load_instance(base)
    if not (instance.ledger_root / "facts").is_dir():
        raise ManifestError(f"{instance.ledger_root} has no facts/ — not a ledger tree "
                            "(spec/ledger.md §3)")
    registered = [
        RegisteredCorpus(
            name="corpus",
            root=instance.corpus_root,
            private=instance.visibility == "private",
        )
    ]
    datasets = {r.dataset: r for r in load_references(base)}
    return instance.ledger_root, CorpusJoin(registered), datasets


def _cmd_check(argv: Sequence[str]) -> int:
    ap = _base_parser("ath ledger check", "Validate the ledger (spec/ledger.md §13.1).")
    ap.add_argument("--no-corpus", action="store_true",
                    help="skip the corpus join (resolution/binding-staleness/sensitivity "
                         "checks)")
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
    derived = (f" ({res.derived_resolved} derived-resolved via corpus resolver)"
              if res.derived_resolved else "")
    if res.demand:
        # (1.8, §13.2.4) the standing normalize-demand aggregate: deferred-surface
        # citations per record, claim evidence + interpretation references alike
        ranked = sorted(res.demand.items(), key=lambda kv: (-kv[1], kv[0]))
        print(f"\nnormalize demand — {len(res.demand)} record(s) cited on deferred "
              "surfaces (cite-then-pressure, §13.2.4):")
        for h, n in ranked[:10]:
            print(f"  corpus://{h[:12]}… x{n}")
        if len(ranked) > 10:
            print(f"  … and {len(ranked) - 10} more")
    deferred = f", {res.deferred} deferred" if res.deferred else ""
    print(f"\n{res.verified} verified{scoped}{derived}, {res.unverifiable} "
          f"unverifiable{deferred}, {res.stamped} stamped — {len(res.errors)} errors, "
          f"{len(res.warnings)} warnings")
    return 0 if res.ok else 1


def _cmd_resolve(argv: Sequence[str]) -> int:
    ap = _base_parser("ath ledger resolve",
                      "Entity resolution before minting (#174).")
    ap.add_argument("query")
    ap.add_argument("--type", dest="type_filter", default=None,
                    help="filter candidates by type (concept/edge type, or interp kind)")
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--json", action="store_true", help="print the full candidate list as JSON")
    ap.add_argument("--ids", action="store_true", help="print bare ids only, one per line")
    ap.add_argument("--all", action="store_true", help="include interpretations")
    ns = ap.parse_args(list(argv))
    ledger_root, _, _ = _system(ns.root)
    from ledger.index import load_or_build, resolve_query

    idx = load_or_build(ledger_root)
    cands = resolve_query(idx, ns.query, type_filter=ns.type_filter,
                          include_interpretations=ns.all, limit=ns.limit)
    if ns.json:
        print(json.dumps(cands, indent=2))
    elif ns.ids:
        for c in cands:
            print(c["id"])
    else:
        for c in cands:
            basis = c["basis"]
            if c.get("note"):
                basis = f"{basis}, {c['note']}"
            print(f"{c['id']}\t{c['type']}\t{c['name']}\t({basis})")
    return 0 if cands else 1


def _cmd_index(argv: Sequence[str]) -> int:
    ap = _base_parser("ath ledger index",
                      "Ensure/rebuild the derived resolution index (uncommitted, .cache/).")
    ap.add_argument("--rebuild", action="store_true", help="force a rebuild")
    ap.add_argument("--stats", action="store_true", help="print index statistics")
    ns = ap.parse_args(list(argv))
    ledger_root, _, _ = _system(ns.root)
    from ledger import index as index_mod

    if ns.rebuild:
        idx = index_mod.build_index(ledger_root)
        index_mod.write_cache(ledger_root, idx)
        print(f"rebuilt ({idx['stamp']['files']} files)")
    else:
        fresh = index_mod.is_fresh(ledger_root)
        idx = index_mod.load_or_build(ledger_root)
        print("fresh" if fresh else f"rebuilt ({idx['stamp']['files']} files)")
    if ns.stats:
        print(f"entries: {len(idx['entries'])}  names: {len(idx['names'])}  "
              f"citations: {len(idx['citations'])}  skipped: {len(idx['skipped'])}")
        print(f"stamp: {idx['stamp']}")
    return 0


def _print_demands(demands: list[dict], *, show_satisfied: bool) -> None:
    from ledger import demands as demands_mod

    if not demands:
        print("no demands apply")
        return
    by_state: dict[str, list[dict]] = {"open": [], "blocked": [], "satisfied": []}
    for d in demands:
        by_state.setdefault(str(d.get("state")), []).append(d)
    if not show_satisfied and not by_state["open"] and not by_state["blocked"]:
        print(f"all {len(demands)} demands satisfied")
        return
    for state in ("open", "blocked", "satisfied"):
        if state == "satisfied" and not show_satisfied:
            continue
        items = by_state.get(state, [])
        if not items:
            continue
        print(f"{state.upper()} ({len(items)}):")
        for d in items:
            line = f"  {d['fact']} owes {d['field']} ({d['rule']})"
            if d.get("why"):
                line += f" — {d['why']}"
            if state == "satisfied" and d.get("satisfied_by"):
                line += f" ← {d['satisfied_by']}"
            print(line)
            shape_label = demands_mod.format_shape(d.get("shape") or {})
            if shape_label:
                print(f"    {shape_label}")
            if state == "blocked" and d.get("need"):
                need = d["need"]
                print(f"    blocked on {need.get('action', '?')}: {need.get('why', '')}")


def _cmd_demands(argv: Sequence[str]) -> int:
    ap = _base_parser(
        "ath ledger demands",
        "The completeness rule layer (§14): a fact's demands, or a ledger-wide summary.",
    )
    ap.add_argument("fact_id", nargs="?", default=None,
                    help="fact id to evaluate (omit for a ledger-wide per-rule summary)")
    ap.add_argument("--draft", metavar="PATH", default=None,
                    help="evaluate a draft fact JSON file not yet landed in the tree")
    ap.add_argument("--all", action="store_true", help="also show satisfied demands")
    ns = ap.parse_args(list(argv))
    ledger_root, _, _ = _system(ns.root)
    from ledger import demands as demands_mod
    from ledger import values as values_mod
    from ledger.model import is_edge, is_redirect, load_json_dir
    from ledger.schemas import load_schemas

    facts, _ = load_json_dir(ledger_root, "facts/*/*.json")
    interps, _ = load_json_dir(ledger_root, "interpretations/*.json")
    schemas, _ = load_schemas(ledger_root)
    kinds, _ = values_mod.load_kinds(ledger_root)
    rules, rule_errors = demands_mod.load_demand_rules(ledger_root)
    for e in rule_errors:
        print(f"WARN  {e}", file=sys.stderr)

    live = [f for f in facts.values() if not is_redirect(f)]
    edges = [f for f in live if is_edge(f)]
    facts_by_id = {str(f.get("id")): f for f in live}
    interp_list = list(interps.values())

    def _evaluate(fact: dict) -> list[dict]:
        return demands_mod.evaluate_demands(
            fact, rules=rules, schemas=schemas, kinds=kinds,
            facts_by_id=facts_by_id, edges=edges, interps=interp_list,
        )

    if ns.draft:
        try:
            fact = json.loads(Path(ns.draft).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"ath ledger demands: {ns.draft}: {e}", file=sys.stderr)
            return 1
        _print_demands(_evaluate(fact), show_satisfied=ns.all)
        return 0

    if ns.fact_id:
        fact = facts_by_id.get(ns.fact_id)
        if fact is None:
            print(f"ath ledger demands: unknown fact {ns.fact_id!r}", file=sys.stderr)
            return 1
        _print_demands(_evaluate(fact), show_satisfied=ns.all)
        return 0

    # no id: a ledger-wide summary — counts per rule, by state
    counts: dict[str, dict[str, int]] = {}
    for fact in live:
        for d in _evaluate(fact):
            bucket = counts.setdefault(str(d["rule"]), {"open": 0, "blocked": 0, "satisfied": 0})
            bucket[str(d["state"])] += 1
    if not counts:
        print("no demands")
        return 0
    for rule_id in sorted(counts):
        b = counts[rule_id]
        print(f"{rule_id}\topen={b['open']}\tblocked={b['blocked']}\tsatisfied={b['satisfied']}")
    return 0


def _cmd_dedupe(argv: Sequence[str]) -> int:
    ap = _base_parser(
        "ath ledger dedupe",
        "Coalescence proposer (#177) — candidate duplicate concepts/edges, "
        "near-duplicate predicates, dead schema surface. READ-ONLY: proposes, "
        "never merges or writes.",
    )
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    ap.add_argument("--section", choices=["concepts", "predicates", "schemas"], default=None,
                    help="restrict to one section (default: all three)")
    ap.add_argument(
        "--review", nargs="?", const="", default=None, metavar="PATH",
        help="write the concepts section as a self-contained HTML judgment page (#182) "
             "to PATH (default: <ledger_root>/.cache/dedupe-review.html) instead of "
             "printing it; composes with nothing else",
    )
    ns = ap.parse_args(list(argv))
    ledger_root, _, _ = _system(ns.root)
    from ledger.dedupe import propose

    if ns.review is not None:
        if ns.json:
            print("ath ledger dedupe: --review cannot be combined with --json",
                  file=sys.stderr)
            return 2
        from ledger.review import classify_groups, render_review

        report = propose(ledger_root)
        page = render_review(ledger_root, report)
        out_path = Path(ns.review) if ns.review else ledger_root / ".cache" / "dedupe-review.html"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_name(out_path.name + ".tmp")
        tmp.write_text(page, encoding="utf-8")
        os.replace(tmp, out_path)
        open_n, adjudicated_n = classify_groups(ledger_root, report["concepts"])
        print(f"review page: {out_path} ({open_n} open, {adjudicated_n} adjudicated groups)")
        return 0

    report = propose(ledger_root)
    if ns.section:
        report = {ns.section: report[ns.section], "skipped": report["skipped"]}
    if ns.json:
        print(json.dumps(report, indent=2))
        return 0

    if "concepts" in report:
        concepts = report["concepts"]
        print(f"== concepts ({len(concepts)} candidate group(s)) ==")
        for c in concepts:
            if c["basis"] == "name-collision":
                print(f"name-collision\t{c['key']}\t" + "\t".join(c["ids"]))
            elif c["basis"] == "id-containment":
                print(f"id-containment\t{c['type']}\t" + "\t".join(c["ids"]))
            else:
                print(f"shared-external-id\t{c['key']}\t" + "\t".join(c["ids"]))
        print()

    if "predicates" in report:
        preds = report["predicates"]
        print(f"== predicates ({len(preds)} candidate pair(s)) ==")
        for p in preds:
            print(f"{p['basis']}\t{p['a']} ({p['count_a']})\t{p['b']} ({p['count_b']})")
        print()

    if "schemas" in report:
        s = report["schemas"]
        print(f"== schemas ({len(s['reports'])} schema(s)) ==")
        for r in s["reports"]:
            print(f"{r['type']}\tfacts={r['fact_count']}\t"
                  f"unused_fields={r['unused_fields']}\tunused_roles={r['unused_roles']}\t"
                  f"all_fields_unused={r['all_fields_unused']}")
        print(f"\nschemaless types ({len(s['schemaless_types'])}):")
        for row in s["schemaless_types"]:
            print(f"{row['type']}\t{row['fact_count']} fact(s)")
        print()

    if report["skipped"]:
        print(f"skipped ({len(report['skipped'])}):")
        for s in report["skipped"]:
            print(f"  {s}")
    return 0


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


def _print_merge_plan(summary: dict, loser: str, survivor: str, *, dry_run: bool) -> None:
    label = "DRY RUN" if dry_run else "APPLYING"
    print(f"[{label}] merge {loser} → {survivor}")
    if summary["errors"]:
        print("REFUSED:")
        for e in summary["errors"]:
            print(f"  {e}")
        return
    for w in summary["warnings"]:
        print(f"warn: {w}")
    renamed = {r["old"] for r in summary["claim_renames"]}
    print(f"claims moved: {len(summary['claims_moved'])}")
    for row in summary["claims_moved"]:
        mark = " (renamed)" if row["old"] in renamed else ""
        print(f"  {row['old']} -> {row['new']}{mark}")
    if summary["sources_unified"]:
        print(f"sources unified: {len(summary['sources_unified'])}")
        for row in summary["sources_unified"]:
            note = f" — {row['note']}" if row.get("note") else ""
            print(f"  {row['loser_key']} -> {row['survivor_key']} ({row['target']}){note}")
    if summary["sources_added"]:
        print(f"sources added (fresh keys): {len(summary['sources_added'])}")
        for row in summary["sources_added"]:
            print(f"  {row['loser_key']} -> {row['new_key']} ({row['target']})")
    if summary["aliases_added"]:
        print(f"aliases added: {', '.join(summary['aliases_added'])}")
    if summary["meta"]:
        print(f"meta: {summary['meta']}")
    if summary["sensitivity"]:
        print(f"sensitivity: {summary['sensitivity']}")
    if summary["artifacts_added"]:
        print(f"artifacts added: {len(summary['artifacts_added'])}")
    if summary["references_rewritten"]:
        print(f"references rewritten: {len(summary['references_rewritten'])}")
        for row in summary["references_rewritten"]:
            extra = " ".join(f"{k}={v}" for k, v in row.items() if k not in ("file", "kind"))
            print(f"  {row['file']} :: {row['kind']} {extra}")
    if summary["challenges_repinned"]:
        print(f"challenges re-pinned: {len(summary['challenges_repinned'])}")
        for row in summary["challenges_repinned"]:
            print(f"  {row['interp']} :: {row['claim']} {row['old_state']} -> {row['new_state']}")
    print(f"lineage row: {loser} -> {survivor}")
    if summary["lineage_retargeted"]:
        print(f"lineage rows retargeted: {len(summary['lineage_retargeted'])}")
        for row in summary["lineage_retargeted"]:
            print(f"  {row['key']}: {row['old_target']} -> {row['new_target']}")
    print(f"files touched: {len(summary['files_touched'])}")
    for f in summary["files_touched"]:
        print(f"  {f}")
    print(f"files deleted: {summary['files_deleted']}")


def _cmd_merge(argv: Sequence[str]) -> int:
    ap = _base_parser(
        "ath ledger merge",
        "Merge a losing fact into a survivor (#176, §4.1) — dry-run by default.",
    )
    ap.add_argument("loser")
    ap.add_argument("survivor")
    ap.add_argument("--apply", action="store_true", help="execute the merge (default: dry-run)")
    ap.add_argument("--json", action="store_true", help="print the full plan as JSON")
    ns = ap.parse_args(list(argv))
    ledger_root, join, datasets = _system(ns.root)
    from ledger.merge import MergeError, apply_merge, plan_merge

    plan = plan_merge(ledger_root, join, ns.loser, ns.survivor)
    summary = {k: v for k, v in plan.items() if not k.startswith("_")}
    if ns.json:
        print(json.dumps(summary, indent=2))
    else:
        _print_merge_plan(summary, ns.loser, ns.survivor, dry_run=not ns.apply)
    if summary["errors"]:
        return 1
    if not ns.apply:
        print("\n(dry run — pass --apply to execute)")
        return 0
    try:
        apply_merge(ledger_root, plan, join, datasets)
    except MergeError as e:
        print(f"ath ledger merge: {e}", file=sys.stderr)
        return 1
    print(f"\napplied: {ns.loser} → {ns.survivor}")
    return 0


def _cmd_remap_el(argv: Sequence[str]) -> int:
    ap = _base_parser(
        "ath ledger remap-el",
        "§12.28 addressing remap for evidence anchors: legacy el=N → child-index "
        "paths, mapped against the artifacts through the same engine the corpus "
        "remap uses (dry-run by default).",
    )
    ap.add_argument("--apply", action="store_true", help="write the rewrites")
    ap.add_argument(
        "--manifest",
        action="append",
        default=[],
        metavar="PATH",
        help="corpus `remap-el` run manifest (repeat once per hub). REQUIRED: it is the "
        "eligibility set — only records the corpus remap actually rewrote may have "
        "their anchors rewritten, since a record it HELD keeps the legacy grammar.",
    )
    ns = ap.parse_args(list(argv))
    ledger_root, join, _ = _system(ns.root)
    from ledger.remap_el import load_migrated_ids, remap_ledger_el

    if not ns.manifest:
        print(
            "ath ledger remap-el: --manifest is required (one per hub, from `corpus "
            "remap-el`). Without it no record is eligible: an anchor rewritten to a "
            "path on a record the corpus remap held would point a §6.1.1 address at a "
            "record that still reads legacy integers.",
            file=sys.stderr,
        )
        return 2
    paths_in = [Path(p) for p in ns.manifest]
    missing = [str(p) for p in paths_in if not p.is_file()]
    if missing:
        print(f"ath ledger remap-el: manifest not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    migrated = load_migrated_ids(paths_in)
    print(f"eligibility: {len(migrated)} record(s) migrated by the corpus remap")

    res = remap_ledger_el(ledger_root, join, apply=ns.apply, migrated=migrated)
    for h in res.holds:
        print(f"HOLD {h.fact}: {h.anchor[:60]} — {h.reason}", file=sys.stderr)
    verb = "rewrote" if ns.apply else "would rewrite"
    forms = ", ".join(f"{k}={v}" for k, v in sorted(res.forms.items())) or "none"
    print(
        f"{verb} {len(res.rewrites)} anchor(s)/citation(s) across "
        f"{len(res.facts_touched)} file(s) ({forms}); {len(res.holds)} held, "
        f"{res.skipped_not_migrated} on records the corpus remap did not migrate"
    )
    if ns.apply:
        print("run `ath ledger check && ath ledger verify` — the gates must be green "
              "in the same change (spec/ledger.md §13)")
    return 1 if res.holds else 0


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
        "resolve": _cmd_resolve,
        "index": _cmd_index,
        "demands": _cmd_demands,
        "dedupe": _cmd_dedupe,
        "harvest": _cmd_harvest,
        "promote": _cmd_promote,
        "stamp": _cmd_stamp,
        "worklist": _cmd_worklist,
        "supersede": _cmd_supersede,
        "merge": _cmd_merge,
        "remap-el": _cmd_remap_el,
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
