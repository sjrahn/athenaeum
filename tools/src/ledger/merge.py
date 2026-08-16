"""`ath ledger merge <loser> <survivor>` — the concept/edge merge verb (#176, §4.1).

`plan_merge` computes the full merge as a pure, JSON-serializable report: claims
re-keyed to the survivor's prefix (shorts preserved, collisions renamed
loudly), sources unified by target, identity fields folded, every reference
ledger-wide rewritten loser→survivor, and the lineage row added — without
writing anything. `apply_merge` executes a plan already free of refusals,
gated by `ath ledger check`: any NEW error the merge introduces rolls the
writes back (git remains the real undo; this only avoids leaving a
knowingly-broken tree from a single `apply` call).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from ledger.check import run_check
from ledger.corpora import CorpusJoin
from ledger.model import (
    CLAIM_ID_RE,
    canonical_claim_state,
    is_redirect,
    load_json_dir,
    load_lineage,
    next_source_key,
    source_target,
)

if TYPE_CHECKING:
    from ath.manifest import Reference

_WIKILINK_TARGET_RE = re.compile(r"\[\[([^\]|#]+)")


class MergeError(RuntimeError):
    """`apply_merge` refused or had to roll back."""


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(obj: dict) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def _new_plan(loser: str, survivor: str) -> dict:
    return {
        "loser": loser, "survivor": survivor, "errors": [], "warnings": [],
        "claims_moved": [], "claim_renames": [], "sources_unified": [],
        "sources_added": [], "aliases_added": [], "meta": None, "sensitivity": None,
        "artifacts_added": [], "references_rewritten": [], "challenges_repinned": [],
        "lineage_row": {}, "lineage_retargeted": [], "files_touched": [],
        "files_deleted": [],
    }


def _refuse(plan: dict, msg: str) -> dict:
    plan["errors"].append(msg)
    plan["_writes"] = {}
    plan["_originals"] = {}
    return plan


def _rekey_short(short: str, taken: set[str]) -> str:
    if short not in taken:
        return short
    i = 2
    while f"{short}-{i}" in taken:
        i += 1
    return f"{short}-{i}"


def _rewrite_string(s: str, loser: str, survivor: str) -> tuple[str, bool]:
    changed = False

    def repl(m: re.Match) -> str:
        nonlocal changed
        if m.group(1) == loser:
            changed = True
            return f"[[{survivor}"
        return m.group(0)

    return _WIKILINK_TARGET_RE.sub(repl, s), changed


def _rewrite_value(value: object, loser: str, survivor: str) -> tuple[object, bool]:
    """Wikilinks (`[[loser]]`) and `{"entity": loser}` refs inside a claim
    `value` — the same surface `ledger.check` scans for dangling references."""
    if isinstance(value, str):
        return _rewrite_string(value, loser, survivor)
    if isinstance(value, list):
        changed = False
        out = []
        for item in value:
            nv, c = _rewrite_value(item, loser, survivor)
            out.append(nv)
            changed = changed or c
        return out, changed
    if isinstance(value, dict):
        changed = False
        out = {}
        for k, v in value.items():
            if k == "entity" and v == loser:
                out[k] = survivor
                changed = True
                continue
            nv, c = _rewrite_value(v, loser, survivor)
            out[k] = nv
            changed = changed or c
        return out, changed
    return value, False


def _merge_sources(survivor_sources: dict, loser_sources: dict):
    """Fold *loser_sources* into a copy of *survivor_sources*: a same-target
    entry unifies onto whichever entry already occupies the combined table
    (seeded from the survivor's, so a genuine survivor/loser collision keeps
    the survivor's `verified`); a fresh target gets its own key, reusing the
    loser's key when free. Returns (combined, {loser_key: combined_key},
    unified rows, added rows)."""
    combined = {k: dict(v) if isinstance(v, dict) else v for k, v in survivor_sources.items()}
    remap: dict[str, str] = {}
    unified: list[dict] = []
    added: list[dict] = []

    def find_by_target(target):
        for k, v in combined.items():
            if isinstance(v, dict) and source_target(v) == target:
                return k
        return None

    for skey_l, entry_l in loser_sources.items():
        if not isinstance(entry_l, dict):
            continue
        target_l = source_target(entry_l)
        existing_key = find_by_target(target_l) if target_l else None
        if existing_key is not None:
            remap[skey_l] = existing_key
            row = {"loser_key": skey_l, "survivor_key": existing_key,
                   "target": f"{target_l[0]}:{target_l[1]}"}
            v_l, v_s = entry_l.get("verified"), combined[existing_key].get("verified")
            if v_l and v_s and v_l != v_s:
                row["note"] = "verified binding differs — kept the existing entry's stamp"
            unified.append(row)
        else:
            new_key = skey_l if skey_l not in combined else next_source_key(combined)
            combined[new_key] = dict(entry_l)
            remap[skey_l] = new_key
            if new_key != skey_l:
                added.append({"loser_key": skey_l, "new_key": new_key,
                              "target": f"{target_l[0]}:{target_l[1]}" if target_l else "?"})
    return combined, remap, unified, added


def _rewrite_fact(fact: dict, loser: str, survivor: str, rel: str, plan: dict) -> bool:
    """Rewrite `subject`/`participants`/claim `object`/claim `value` refs to
    *loser* → *survivor* on one fact (concept or edge). Mutates in place."""
    changed = False
    if fact.get("subject") == loser:
        fact["subject"] = survivor
        changed = True
        plan["references_rewritten"].append({"file": rel, "kind": "subject",
                                             "old": loser, "new": survivor})
    parts = fact.get("participants")
    if isinstance(parts, list) and loser in parts:
        fact["participants"] = [survivor if p == loser else p for p in parts]
        changed = True
        plan["references_rewritten"].append({"file": rel, "kind": "participant",
                                             "old": loser, "new": survivor})
    for c in fact.get("claims") or []:
        if not isinstance(c, dict):
            continue
        if c.get("object") == loser:
            c["object"] = survivor
            changed = True
            plan["references_rewritten"].append({"file": rel, "kind": "object",
                                                 "old": loser, "new": survivor,
                                                 "claim": c.get("id")})
        if "value" in c:
            new_v, v_changed = _rewrite_value(c["value"], loser, survivor)
            if v_changed:
                c["value"] = new_v
                changed = True
                plan["references_rewritten"].append({"file": rel, "kind": "wikilink/entity",
                                                     "claim": c.get("id")})
    return changed


def _rewrite_interp(
    o: dict, loser: str, survivor: str, claim_rename_map: dict[str, str],
    moved_claim_by_id: dict[str, dict], combined_sources: dict, rel: str, plan: dict,
) -> bool:
    """Rewrite `about`/`based_on`/`proposes`/`challenges` refs to *loser* →
    *survivor* on one interpretation, re-keying claim ids through
    *claim_rename_map* and re-pinning a rewritten `challenges.state` (§7.3 —
    the content examined is unchanged, only the claim id moved). Mutates in
    place."""
    changed = False
    about = o.get("about")
    if isinstance(about, list) and loser in about:
        o["about"] = [survivor if a == loser else a for a in about]
        changed = True
        plan["references_rewritten"].append({"file": rel, "kind": "about",
                                             "old": loser, "new": survivor})

    based = o.get("based_on")
    if isinstance(based, list):
        new_based = []
        b_changed = False
        for b in based:
            bs = str(b)
            if bs == loser:
                new_based.append(survivor)
                b_changed = True
            elif bs in claim_rename_map:
                new_based.append(claim_rename_map[bs])
                b_changed = True
            else:
                new_based.append(b)
        if b_changed:
            o["based_on"] = new_based
            changed = True
            plan["references_rewritten"].append({"file": rel, "kind": "based_on"})

    proposes = o.get("proposes")
    if isinstance(proposes, dict):
        pid = str(proposes.get("id", ""))
        m = CLAIM_ID_RE.match(pid)
        if m and m.group(1) == loser:
            new_pid = f"{survivor}:{m.group(2)}"
            proposes["id"] = new_pid
            changed = True
            plan["references_rewritten"].append({"file": rel, "kind": "proposes",
                                                 "old": pid, "new": new_pid})

    challenges = o.get("challenges")
    if isinstance(challenges, dict):
        target = str(challenges.get("claim", ""))
        if target in claim_rename_map:
            new_target = claim_rename_map[target]
            challenges["claim"] = new_target
            changed = True
            plan["references_rewritten"].append({"file": rel, "kind": "challenges",
                                                 "old": target, "new": new_target})
            if challenges.get("state"):
                new_claim = moved_claim_by_id.get(new_target)
                if new_claim is not None:
                    old_state = challenges["state"]
                    new_state = canonical_claim_state(new_claim, combined_sources)
                    challenges["state"] = new_state
                    plan["challenges_repinned"].append({
                        "interp": o.get("id"), "claim": new_target,
                        "old_state": old_state, "new_state": new_state,
                    })
    return changed


def plan_merge(ledger_root: Path, join: CorpusJoin | None, loser: str, survivor: str) -> dict:
    """Compute the full merge of *loser* into *survivor* — pure, no writes.

    *join* is accepted for symmetry with the other ledger verbs and reserved
    for a future corpus-aware refusal; today's merge is pure ledger-graph
    rewriting and doesn't need it. Refusals (missing/non-living fact,
    same id, cross-type, either id is an interpretation) land in
    `plan["errors"]`; `apply_merge` refuses to execute such a plan.
    """
    del join  # reserved, see docstring
    plan = _new_plan(loser, survivor)

    if loser == survivor:
        return _refuse(plan, f"loser and survivor are the same id ({loser!r})")

    interp_dir = ledger_root / "interpretations"
    if (interp_dir / f"{loser}.json").is_file():
        return _refuse(plan, f"{loser!r} is an interpretation, not a fact — merge operates "
                             "on facts only")
    if (interp_dir / f"{survivor}.json").is_file():
        return _refuse(plan, f"{survivor!r} is an interpretation, not a fact — merge "
                             "operates on facts only")

    facts, fact_errors = load_json_dir(ledger_root, "facts/*/*.json")
    interps, interp_errors = load_json_dir(ledger_root, "interpretations/*.json")
    plan["warnings"].extend(fact_errors + interp_errors)

    loser_path = next((p for p in facts if p.stem == loser), None)
    survivor_path = next((p for p in facts if p.stem == survivor), None)
    if loser_path is None:
        return _refuse(plan, f"loser {loser!r}: no fact file")
    if survivor_path is None:
        return _refuse(plan, f"survivor {survivor!r}: no fact file")

    loser_fact = facts[loser_path]
    survivor_fact = facts[survivor_path]
    if is_redirect(loser_fact):
        return _refuse(plan, f"loser {loser!r} carries the legacy redirect shape — not a "
                             "living fact")
    if is_redirect(survivor_fact):
        return _refuse(plan, f"survivor {survivor!r} carries the legacy redirect shape — "
                             "not a living fact")

    loser_type, survivor_type = loser_path.parent.name, survivor_path.parent.name
    if loser_type != survivor_type:
        return _refuse(plan, f"cross-type merge: loser is {loser_type!r}, survivor is "
                             f"{survivor_type!r} — retype first")

    # ---------------------------------------------------------------- claims
    survivor_claims = [c for c in survivor_fact.get("claims") or [] if isinstance(c, dict)]
    loser_claims = [c for c in loser_fact.get("claims") or [] if isinstance(c, dict)]
    taken_shorts = set()
    for c in survivor_claims:
        m = CLAIM_ID_RE.match(str(c.get("id", "")))
        if m:
            taken_shorts.add(m.group(2))

    claim_rename_map: dict[str, str] = {}
    moved_claims: list[dict] = []
    for c in loser_claims:
        m = CLAIM_ID_RE.match(str(c.get("id", "")))
        if not m:
            plan["warnings"].append(f"claim {c.get('id')!r} on {loser!r} is not claim-id "
                                    "shaped — moved verbatim, not re-keyed")
            moved_claims.append(dict(c))
            continue
        short = m.group(2)
        new_short = _rekey_short(short, taken_shorts)
        taken_shorts.add(new_short)
        old_id, new_id = f"{loser}:{short}", f"{survivor}:{new_short}"
        claim_rename_map[old_id] = new_id
        nc = dict(c)
        nc["id"] = new_id
        moved_claims.append(nc)
        plan["claims_moved"].append({"old": old_id, "new": new_id})
        if new_short != short:
            plan["claim_renames"].append({"old": old_id, "new": new_id})

    # --------------------------------------------------------------- sources
    survivor_sources = survivor_fact.get("sources") \
        if isinstance(survivor_fact.get("sources"), dict) else {}
    loser_sources = loser_fact.get("sources") \
        if isinstance(loser_fact.get("sources"), dict) else {}
    combined_sources, source_remap, unified, added = _merge_sources(
        survivor_sources, loser_sources
    )
    plan["sources_unified"] = unified
    plan["sources_added"] = added

    for c in moved_claims:
        for e in c.get("evidence") or []:
            if isinstance(e, dict) and e.get("source") in source_remap:
                e["source"] = source_remap[e["source"]]

    survivor_fact["claims"] = survivor_claims + moved_claims
    if combined_sources:
        survivor_fact["sources"] = combined_sources
    elif "sources" in survivor_fact:
        del survivor_fact["sources"]

    moved_claim_by_id = {c["id"]: c for c in moved_claims}

    # -------------------------------------------------------------- identity
    aliases = list(survivor_fact.get("aliases") or [])
    for cand in [loser_fact.get("name"), *(loser_fact.get("aliases") or [])]:
        if isinstance(cand, str) and cand and cand != survivor_fact.get("name") \
                and cand not in aliases:
            aliases.append(cand)
            plan["aliases_added"].append(cand)
    if aliases:
        survivor_fact["aliases"] = aliases

    if not survivor_fact.get("meta") and loser_fact.get("meta"):
        survivor_fact["meta"] = loser_fact["meta"]
        plan["meta"] = "took loser's meta (survivor had none)"
    elif survivor_fact.get("meta") and loser_fact.get("meta"):
        plan["meta"] = "kept survivor's meta — loser's meta discarded"

    if loser_fact.get("sensitivity") == "private" and survivor_fact.get("sensitivity") != "private":
        survivor_fact["sensitivity"] = "private"
        plan["sensitivity"] = "upgraded to private (loser asserted private)"

    existing_artifacts = list(survivor_fact.get("artifacts") or [])
    seen_art = {(a.get("uri"), a.get("role")) for a in existing_artifacts
                if isinstance(a, dict)}
    for art in loser_fact.get("artifacts") or []:
        if not isinstance(art, dict):
            continue
        key = (art.get("uri"), art.get("role"))
        if key not in seen_art:
            existing_artifacts.append(dict(art))
            seen_art.add(key)
            plan["artifacts_added"].append(key)
    if existing_artifacts:
        survivor_fact["artifacts"] = existing_artifacts

    # --------------------------------------------------------------- lineage
    lineage, lineage_errors = load_lineage(ledger_root)
    plan["warnings"].extend(lineage_errors)
    for key, target in list(lineage.items()):
        if target == loser:
            lineage[key] = survivor
            plan["lineage_retargeted"].append({"key": key, "old_target": loser,
                                               "new_target": survivor})
    lineage[loser] = survivor
    plan["lineage_row"] = {loser: survivor}

    # ------------------------------------------------- reference rewrite pass
    touched_paths: set[Path] = set()
    for path, obj in facts.items():
        if path == loser_path:
            continue
        rel = str(path.relative_to(ledger_root))
        changed = _rewrite_fact(obj, loser, survivor, rel, plan)
        if changed or path == survivor_path:
            touched_paths.add(path)

    for path, obj in interps.items():
        rel = str(path.relative_to(ledger_root))
        changed = _rewrite_interp(
            obj, loser, survivor, claim_rename_map, moved_claim_by_id,
            combined_sources, rel, plan,
        )
        if changed:
            touched_paths.add(path)

    # ------------------------------------------------------------ assemble
    all_objs = {**facts, **interps}
    writes: dict[str, str | None] = {}
    originals: dict[str, str | None] = {}
    for path in sorted(touched_paths, key=lambda p: str(p)):
        rel = str(path.relative_to(ledger_root))
        originals[rel] = path.read_text(encoding="utf-8") if path.is_file() else None
        writes[rel] = _dump(all_objs[path])
        plan["files_touched"].append(rel)
    plan["files_touched"].sort()

    loser_rel = str(loser_path.relative_to(ledger_root))
    originals[loser_rel] = loser_path.read_text(encoding="utf-8")
    writes[loser_rel] = None
    plan["files_deleted"].append(loser_rel)

    lineage_path = ledger_root / "facts" / "LINEAGE.json"
    lineage_rel = "facts/LINEAGE.json"
    originals[lineage_rel] = lineage_path.read_text(encoding="utf-8") \
        if lineage_path.is_file() else None
    writes[lineage_rel] = json.dumps(dict(sorted(lineage.items())), indent=1,
                                     ensure_ascii=False) + "\n"

    plan["_writes"] = writes
    plan["_originals"] = originals
    return plan


def apply_merge(
    ledger_root: Path, plan: dict, join: CorpusJoin | None = None,
    datasets: Mapping[str, Reference] | None = None,
) -> None:
    """Execute a plan from `plan_merge`. Refuses a plan carrying errors.
    Writes every file the plan computed, then gates on `ath ledger check`
    (full corpus join when *join* is given, `--no-corpus` mode otherwise):
    any NEW error the merge introduced rolls every write back."""
    if plan.get("errors"):
        raise MergeError("refused: " + "; ".join(plan["errors"]))
    writes: dict[str, str | None] = plan.get("_writes") or {}
    originals: dict[str, str | None] = plan.get("_originals") or {}
    if not writes:
        raise MergeError("empty plan — nothing to apply")

    no_corpus = join is None
    real_join = join if join is not None else CorpusJoin([])
    real_datasets = datasets if datasets is not None else {}
    baseline = run_check(ledger_root, real_join, real_datasets, no_corpus=no_corpus)

    def _write_all(mapping: dict[str, str | None]) -> None:
        for rel, content in mapping.items():
            path = ledger_root / rel
            if content is None:
                if path.is_file():
                    path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

    _write_all(writes)

    after = run_check(ledger_root, real_join, real_datasets, no_corpus=no_corpus)
    new_errors = [e for e in after.errors if e not in baseline.errors]
    if new_errors:
        _write_all(originals)
        raise MergeError("merge introduced new check errors — rolled back: "
                         + "; ".join(new_errors))
