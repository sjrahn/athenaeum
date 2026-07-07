"""Scope materialization — the deterministic targeting pass (`spec/codex.md` §3).

Selectors are additive: `types` includes every fact of the listed types;
`roots` includes the listed concepts and their subgraph traversed in both
directions within the traversal type bound; `exclude` carves out visibly.
Interpretations ride along when their `about` intersects the scope.

Traversal follows claim `object`s, edge `subject`/`participants`, and the
structured-value entity references of `facts/SCHEMA.md` conv. 7 —
`{"entity": <id>}` elements inside a claim's `value` (an event's attendance,
a group's members, a lineup) — treating each entity like a claim object.
"""

from __future__ import annotations

from pathlib import Path

from codex.manifest import CodexManifest
from ledger.model import is_edge, is_redirect, load_json_dir


def _value_entities(value: object) -> list[str]:
    """Every `entity` reference inside a claim `value` (conv. 7 roster shape).

    Walks lists and tolerates nested dicts; collects each string `"entity"`.
    Parse tolerantly — a malformed element contributes nothing, never raises.
    """
    out: list[str] = []

    def walk(v: object) -> None:
        if isinstance(v, dict):
            ent = v.get("entity")
            if isinstance(ent, str):
                out.append(ent)
            for sub in v.values():
                walk(sub)
        elif isinstance(v, list):
            for item in v:
                walk(item)

    walk(value)
    return out


def _claim_refs(o: dict) -> list[object]:
    """A fact's outgoing/incoming claim references: each claim's `object` plus
    the entity references buried in its structured `value`."""
    refs: list[object] = []
    for c in o.get("claims") or []:
        if not isinstance(c, dict):
            continue
        refs.append(c.get("object"))
        refs.extend(_value_entities(c.get("value")))
    return refs


def materialize(ledger_root: Path, manifest: CodexManifest) -> tuple[
    dict[str, dict], dict[str, dict], list[str]
]:
    """→ (scoped facts by id, riding interpretations by id, notes/problems)."""
    facts, errors = load_json_dir(ledger_root, "facts/*/*.json")
    interps, ierrors = load_json_dir(ledger_root, "interpretations/*.json")
    problems = list(errors) + list(ierrors)

    by_id: dict[str, dict] = {}
    redirects: dict[str, str] = {}
    for o in facts.values():
        fid = str(o.get("id"))
        if is_redirect(o):
            redirects[fid] = str(o.get("merged_into"))
        else:
            by_id[fid] = o

    def resolve(ref: str) -> str | None:
        if ref in by_id:
            return ref
        target = redirects.get(ref)
        return target if target in by_id else None

    scope = manifest.scope
    selected: set[str] = {
        fid for fid, o in by_id.items() if o.get("type") in scope.types
    }
    for root in scope.roots:
        rid = resolve(root)
        if rid is None:
            problems.append(f"scope root {root!r} is not a ledger fact")
        else:
            selected.add(rid)

    bound = set(scope.traversal_bound)

    def admissible(fid: str) -> bool:
        return not bound or by_id[fid].get("type") in bound

    # bidirectional fixed-point traversal within the bound
    changed = True
    while changed:
        changed = False
        for fid, o in by_id.items():
            if fid in selected:
                # outgoing: claim objects + structured-value entities; edge members
                targets = _claim_refs(o)
                targets.append(o.get("subject"))
                targets.extend(o.get("participants") or [])
                for t in targets:
                    if t is None:
                        continue
                    r = resolve(str(t))
                    if r and r not in selected and admissible(r):
                        selected.add(r)
                        changed = True
                continue
            if not admissible(fid):
                continue
            # incoming: this fact's claims (object or structured-value entity)
            # target the scope (spoke → hub), or this edge spans it
            refs = _claim_refs(o)
            if is_edge(o):
                refs.append(o.get("subject"))
                refs.extend(o.get("participants") or [])
            if any((r := resolve(str(t))) and r in selected
                   for t in refs if t is not None):
                selected.add(fid)
                changed = True

    for ex in scope.exclude:
        selected.discard(ex)

    riding = {
        str(o.get("id")): o
        for o in interps.values()
        if any(resolve(str(a)) in selected for a in o.get("about") or [])
    }
    scoped = {fid: by_id[fid] for fid in sorted(selected)}
    return scoped, riding, problems
