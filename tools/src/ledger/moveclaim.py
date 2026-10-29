"""`ath ledger move-claim <claim-id> <to>` — one claim leaves a file that lives on (§4.1, v49).

The claim-grain counterpart of `merge`. `plan_move` computes the whole move without writing:
- the claim leaves its file;
- when `to` is a claim id `fact:short`, the claim lands there, its evidence sources
  re-hoisted into the destination's sources table;
- when `to` is a bare fact id, the claim BECAME that fact (the fact already holds what the
  claim said) and lands nowhere;
- internal references naming the claim (`based_on`, `challenges`) are rewritten, and a
  challenge pin re-stamped (§7.3 — the content examined is unchanged, only the id moved);
- the lineage row `"old-id": {"to": …, "reason": "split"|"rekeyed"}` is added, and older
  claim-grain rows that pointed at the moved id are retargeted (one-hop rule).

External holders of the old id (`ledger://…`, frozen corpus prose) resolve through the row.
`apply_move` executes a refusal-free plan behind the same `ath ledger check` gate `merge`
uses: any NEW check error rolls every write back. `apply_moves` runs several moves behind ONE
gate (a split of dozens of claims pays the two check runs once), and `preview_moves` plans
them in sequence against a scratch copy, so each plan sees the moves before it.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from ledger.check import run_check
from ledger.corpora import CorpusJoin
from ledger.merge import MergeError, _dump, apply_merge, write_all
from ledger.model import (
    CLAIM_ID_RE,
    CLAIM_LINEAGE_REASONS,
    SLUG_RE,
    canonical_claim_state,
    is_redirect,
    load_claim_lineage_rows,
    load_json_dir,
    load_lineage_rows,
    next_source_key,
    source_target,
)

if TYPE_CHECKING:
    from ath.manifest import Reference

MoveError = MergeError
Move = tuple[str, str, str]  # (claim id, to, reason)


def plan_move(ledger_root: Path, claim_id: str, to: str, reason: str) -> dict:
    plan: dict = {
        "claim": claim_id, "to": to, "reason": reason, "errors": [], "warnings": [],
        "sources_added": [], "sources_pruned": [], "references_rewritten": [],
        "challenges_repinned": [], "lineage_row": {}, "lineage_retargeted": [],
        "dependents": [], "files_touched": [],
    }

    def refuse(msg: str) -> dict:
        plan["errors"].append(msg)
        plan["_writes"], plan["_originals"] = {}, {}
        return plan

    if reason not in CLAIM_LINEAGE_REASONS:
        return refuse(f"reason {reason!r} is not a claim-grain reason "
                      f"{sorted(CLAIM_LINEAGE_REASONS)}")
    m = CLAIM_ID_RE.match(claim_id)
    if not m:
        return refuse(f"{claim_id!r} is not a claim id `{{file-id}}:{{short}}`")
    tm = CLAIM_ID_RE.match(to)
    if not tm and not SLUG_RE.match(to):
        return refuse(f"`to` {to!r} is neither a fact id nor a claim id")
    src_id, dest_id = m.group(1), (tm.group(1) if tm else to)
    if dest_id == src_id:
        return refuse("a claim moves to ANOTHER fact — a short rename in place is not a "
                      "move (§4.1: outside merge-collision, tooling never rewrites a short)")

    facts, _ = load_json_dir(ledger_root, "facts/*/*.json")
    interps, _ = load_json_dir(ledger_root, "interpretations/*.json")
    by_id = {str(o.get("id")): (p, o) for p, o in facts.items() if not is_redirect(o)}
    if src_id not in by_id:
        return refuse(f"no living fact {src_id!r}")
    if dest_id not in by_id:
        return refuse(f"no living fact {dest_id!r} — mint it first")
    src_path, src = by_id[src_id]
    dest_path, dest = by_id[dest_id]
    claim = next((c for c in src.get("claims") or []
                  if isinstance(c, dict) and c.get("id") == claim_id), None)
    if claim is None:
        return refuse(f"no living claim {claim_id!r} on {src_id!r}")

    lineage, lineage_errors = load_lineage_rows(ledger_root)
    plan["warnings"].extend(lineage_errors)
    claim_rows = load_claim_lineage_rows(ledger_root)
    if tm:
        living = {str(c.get("id")) for o in by_id.values() for c in o[1].get("claims") or []
                  if isinstance(c, dict)}
        if to in living:
            return refuse(f"{to!r} is already a living claim")
        if to in claim_rows:
            return refuse(f"{to!r} is a retired claim id (facts/LINEAGE.json) — occupied")

    # ------------------------------------------------------------ the claim itself
    src["claims"] = [c for c in src.get("claims") or [] if c is not claim]
    moved = None
    src_sources = src.get("sources") if isinstance(src.get("sources"), dict) else {}
    if tm:
        moved = dict(claim)
        moved["id"] = to
        dest_sources = dest.setdefault("sources", {})
        remap: dict[str, str] = {}
        for e in moved.get("evidence") or []:
            skey = e.get("source") if isinstance(e, dict) else None
            if not skey or skey in remap or skey not in src_sources:
                continue
            target = source_target(src_sources[skey])
            existing = next((k for k, v in dest_sources.items()
                             if isinstance(v, dict) and source_target(v) == target), None)
            if existing is None:
                existing = skey if skey not in dest_sources else next_source_key(dest_sources)
                dest_sources[existing] = dict(src_sources[skey])
                plan["sources_added"].append({"from": skey, "to": existing})
            remap[skey] = existing
        moved["evidence"] = [
            {**e, "source": remap.get(e["source"], e["source"])}
            if isinstance(e, dict) and e.get("source") else e
            for e in moved.get("evidence") or []
        ]
        dest.setdefault("claims", []).append(moved)
    else:
        plan["warnings"].append(
            f"{claim_id!r} became the fact {to!r}: its content is NOT carried — {to!r} must "
            "already state what the claim said"
        )
    # sources the moved claim alone cited leave its old file with it
    still_cited = {e.get("source") for c in src.get("claims") or [] if isinstance(c, dict)
                   for e in c.get("evidence") or [] if isinstance(e, dict)}
    for skey in list(src_sources):
        if skey not in still_cited and any(
                isinstance(e, dict) and e.get("source") == skey
                for e in claim.get("evidence") or []):
            del src_sources[skey]
            plan["sources_pruned"].append(skey)

    # ------------------------------------------------ internal references (§4.1)
    touched: set[Path] = {src_path} | ({dest_path} if tm else set())
    for path, o in interps.items():
        rel = str(path.relative_to(ledger_root))
        based = o.get("based_on")
        if isinstance(based, list) and claim_id in based:
            if not tm:
                plan["errors"].append(
                    f"{rel}: based_on names {claim_id!r}, which becomes the fact {to!r} — "
                    "based_on takes claim ids and citations; re-point it by hand first")
                continue
            o["based_on"] = [to if b == claim_id else b for b in based]
            plan["references_rewritten"].append({"file": rel, "kind": "based_on"})
            touched.add(path)
        ch = o.get("challenges")
        if isinstance(ch, dict) and ch.get("claim") == claim_id:
            if not tm:
                plan["errors"].append(
                    f"{rel}: challenges {claim_id!r}, which becomes the fact {to!r} — "
                    "resolve or retarget the correction first")
                continue
            ch["claim"] = to
            plan["references_rewritten"].append({"file": rel, "kind": "challenges"})
            if ch.get("state") and moved is not None:
                old_state = ch["state"]
                ch["state"] = canonical_claim_state(moved, dest.get("sources") or {})
                plan["challenges_repinned"].append(
                    {"interp": o.get("id"), "old_state": old_state, "new_state": ch["state"]})
            touched.add(path)
    if plan["errors"]:
        plan["_writes"], plan["_originals"] = {}, {}
        return plan

    # --------------------------------------------------------------- lineage
    for key, row in list(claim_rows.items()):
        if row.get("to") == claim_id:
            claim_rows[key] = {"to": to, "reason": row.get("reason")}
            plan["lineage_retargeted"].append({"key": key, "old_target": claim_id,
                                               "new_target": to})
    claim_rows[claim_id] = {"to": to, "reason": reason}
    plan["lineage_row"] = {claim_id: dict(claim_rows[claim_id])}
    plan["dependents"] = [f"{r['kind']} in {r['file']}" for r in plan["references_rewritten"]]

    # ------------------------------------------------------------ assemble
    all_objs = {**facts, **interps}
    writes: dict[str, str | None] = {}
    originals: dict[str, str | None] = {}
    for path in sorted(touched, key=str):
        rel = str(path.relative_to(ledger_root))
        originals[rel] = path.read_text(encoding="utf-8")
        writes[rel] = _dump(all_objs[path])
        plan["files_touched"].append(rel)
    lineage_path = ledger_root / "facts" / "LINEAGE.json"
    lineage_rel = "facts/LINEAGE.json"
    originals[lineage_rel] = (lineage_path.read_text(encoding="utf-8")
                              if lineage_path.is_file() else None)
    writes[lineage_rel] = json.dumps(dict(sorted({**lineage, **claim_rows}.items())),
                                     indent=1, ensure_ascii=False) + "\n"
    plan["_writes"], plan["_originals"] = writes, originals
    return plan


def apply_move(ledger_root: Path, plan: dict, join=None, datasets=None) -> None:
    """Execute a refusal-free `plan_move`, gated by `ath ledger check` (see `apply_merge`)."""
    apply_merge(ledger_root, plan, join, datasets, verb="move-claim")


def apply_moves(
    ledger_root: Path, moves: Iterable[Move], join: CorpusJoin | None = None,
    datasets: Mapping[str, Reference] | None = None,
) -> list[dict]:
    """Execute `moves` in order behind ONE `ath ledger check` gate. Each move is planned
    against the ledger as the moves before it left it. A refused plan, or any NEW check error
    after the last move, rolls every move's writes back and raises `MoveError`."""
    no_corpus = join is None
    real_join = join if join is not None else CorpusJoin([])
    real_datasets = datasets if datasets is not None else {}
    baseline = run_check(ledger_root, real_join, real_datasets, no_corpus=no_corpus)
    originals: dict[str, str | None] = {}
    plans: list[dict] = []
    try:
        for claim_id, to, reason in moves:
            plan = plan_move(ledger_root, claim_id, to, reason)
            plans.append(plan)
            if plan["errors"]:
                raise MoveError(f"{claim_id} → {to} refused: " + "; ".join(plan["errors"]))
            for rel, content in plan["_originals"].items():
                originals.setdefault(rel, content)
            write_all(ledger_root, plan["_writes"])
        if not plans:
            raise MoveError("no moves given")
        after = run_check(ledger_root, real_join, real_datasets, no_corpus=no_corpus)
        new_errors = [e for e in after.errors if e not in baseline.errors]
        if new_errors:
            raise MoveError(f"{len(plans)} moves introduced new check errors: "
                            + "; ".join(new_errors))
    except BaseException as e:
        write_all(ledger_root, originals)
        if isinstance(e, MoveError):
            raise MoveError(f"{e} — rolled back all {len(plans)} planned moves") from None
        raise
    return plans


def preview_moves(ledger_root: Path, moves: Iterable[Move]) -> list[dict]:
    """Plan `moves` in order without touching the ledger: each plan is computed on, and
    written to, a scratch copy of `facts/` and `interpretations/`, so a later move sees the
    earlier ones. Planning stops at the first refused move (its plan is the last returned)."""
    plans: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="ath-move-claim-") as tmp:
        scratch = Path(tmp)
        for sub in ("facts", "interpretations"):
            if (ledger_root / sub).is_dir():
                shutil.copytree(ledger_root / sub, scratch / sub)
        for claim_id, to, reason in moves:
            plan = plan_move(scratch, claim_id, to, reason)
            plans.append(plan)
            if plan["errors"]:
                break
            write_all(scratch, plan["_writes"])
    return plans
