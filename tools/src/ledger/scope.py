"""Scope selection and traversal — the library `spec/ledger.md` §12.1 names as
the one place scope semantics live, shared by every consumer (the read
surface's query parameters included) rather than reimplemented per caller.

A scope evaluation is deterministic: seed, traverse, close.

- **Seed** — explicit ids, every fact of a type, or the facts matched by a
  deterministic predicate (the §10 operator grammar: equals/in/glob/matches/
  exists; all_of/any_of/none_of; exact-by-default, missing-is-false) over
  fact fields (`type`, `id`, `name`) and claim predicates/values
  (`claim.<predicate>`, tested against each matching claim's `value` and
  `object`).
- **Traverse** — relational claim `object`s, `{"entity": …}` refs inside
  claim values (recursing nested lists/dicts), wikilinks in string claim
  values, and edge participation: an edge joins the scope when its subject
  or a participant is in scope, and an in-scope edge's subject + participants
  become reachable. Every hop resolves through the lineage map (§4.1) before
  it counts — a scope never contains a retired id. The roster (`artifacts`)
  never adds facts to scope; it is carried in the result when followed.
- **Close** — a visited-set closure: cycle-safe, order-deterministic (ids
  sorted at each frontier), reproducible for a given instance commit.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from ledger.model import WIKILINK_RE, derived_uri, is_edge, is_redirect, load_json_dir, load_lineage

FOLLOW_KINDS = {"object", "entity", "wikilink", "roster", "participants"}
DEFAULT_FOLLOW = ["object", "entity", "wikilink", "participants"]
EVIDENCE_MODES = {"none", "references", "resolved"}
_OPS = {"equals", "in", "glob", "matches", "exists"}
_GROUPS = {"all_of", "any_of", "none_of"}


# ------------------------------------------------------------------ spec validation


def _validate_spec(spec: dict) -> tuple[dict, list[str], int | None, str]:
    """Tolerant-but-strict spec validation → (seed, follow, depth, evidence).

    Raises ValueError with a clear message on malformed spec. Does not touch
    the ledger — pure shape checking.
    """
    if not isinstance(spec, dict):
        raise ValueError("scope spec must be an object")

    seed = spec.get("seed")
    if not isinstance(seed, dict):
        raise ValueError("scope spec requires a 'seed' object")
    present = [k for k in ("ids", "type", "match") if k in seed]
    if len(present) != 1:
        raise ValueError(
            "seed must specify exactly one of: ids, type, match "
            f"(got {sorted(seed) or 'none'})"
        )
    unknown = set(seed) - {"ids", "type", "match"}
    if unknown:
        raise ValueError(f"seed: unknown keys {sorted(unknown)}")
    kind = present[0]
    if kind == "ids":
        ids = seed["ids"]
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise ValueError("seed.ids must be a list of strings")
    elif kind == "type":
        if not isinstance(seed["type"], str):
            raise ValueError("seed.type must be a string")
    else:
        if not isinstance(seed["match"], dict):
            raise ValueError("seed.match must be an object (the operator-grammar predicate)")

    follow = spec.get("follow", DEFAULT_FOLLOW)
    if not isinstance(follow, list) or not all(isinstance(f, str) for f in follow):
        raise ValueError("follow must be a list of strings")
    bad = sorted(set(follow) - FOLLOW_KINDS)
    if bad:
        raise ValueError(f"follow: unknown kind(s) {bad} — admissible: {sorted(FOLLOW_KINDS)}")

    depth = spec.get("depth")
    if depth is not None and (isinstance(depth, bool) or not isinstance(depth, int) or depth < 0):
        raise ValueError("depth must be a non-negative integer")

    evidence = spec.get("evidence", "none")
    if evidence not in EVIDENCE_MODES:
        raise ValueError(f"evidence must be one of {sorted(EVIDENCE_MODES)}, got {evidence!r}")

    return seed, follow, depth, evidence


# ------------------------------------------------------------------ the match predicate (§10)


def _op_matches(op: str, arg: object, values: list[str]) -> bool:
    if op == "exists":
        return bool(values) is bool(arg)
    if not values:
        return False
    if op == "equals":
        return any(v == str(arg) for v in values)
    if op == "in":
        options = [str(a) for a in (arg if isinstance(arg, list) else [arg])]
        return any(v in options for v in values)
    if op == "glob":
        return any(fnmatch.fnmatchcase(v, str(arg)) for v in values)
    if op == "matches":
        rx = re.compile(str(arg))
        return any(rx.search(v) for v in values)
    raise ValueError(f"unknown operator {op!r}")


def _field_values(fact: dict, key: str) -> list[str]:
    """A seed-match field's values (§12.1): `type`/`id`/`name` from the fact
    itself; `claim.<predicate>` from every matching claim's `value` AND
    `object` (either side of the claim addresses the predicate)."""
    if key in ("type", "id", "name"):
        v = fact.get(key)
        if v is None:
            return []
        return [str(x) for x in v] if isinstance(v, list) else [str(v)]
    if key.startswith("claim."):
        pred = key[len("claim."):]
        out: list[str] = []
        for c in fact.get("claims") or []:
            if not isinstance(c, dict) or c.get("predicate") != pred:
                continue
            for side in ("value", "object"):
                sv = c.get(side)
                if sv is None:
                    continue
                out.extend(str(x) for x in sv) if isinstance(sv, list) else out.append(str(sv))
        return out
    return []  # an unaddressable field is simply never present — missing-is-false


def _match_predicate(predicate: dict, fact: dict) -> bool:
    """The §10 operator grammar over one fact's addressable fields."""
    if not isinstance(predicate, dict):
        raise ValueError("match predicate must be an object")
    for key, spec in predicate.items():
        if key in _GROUPS:
            subs = spec if isinstance(spec, list) else [spec]
            results = [_match_predicate(s, fact) for s in subs]
            ok = {"all_of": all(results), "any_of": any(results),
                  "none_of": not any(results)}[key]
            if not ok:
                return False
            continue
        if not isinstance(spec, dict):
            spec = {"equals": spec}
        values = _field_values(fact, key)
        for op, arg in spec.items():
            if op not in _OPS:
                raise ValueError(f"unknown operator {op!r} on {key!r}")
            if not _op_matches(op, arg, values):
                return False
    return True


# ------------------------------------------------------------------ reference extraction (§4.4)


def _iter_strings(v: object):
    if isinstance(v, str):
        yield v
    elif isinstance(v, list):
        for x in v:
            yield from _iter_strings(x)
    elif isinstance(v, dict):
        for x in v.values():
            yield from _iter_strings(x)


def _iter_entity_refs(v: object):
    """Ids from every `{"entity": <str>}` object inside a claim value,
    recursing nested lists/dicts (the roster shape, §4.4)."""
    if isinstance(v, dict):
        e = v.get("entity")
        if isinstance(e, str):
            yield e
        for x in v.values():
            yield from _iter_entity_refs(x)
    elif isinstance(v, list):
        for x in v:
            yield from _iter_entity_refs(x)


def _claim_objects(fact: dict):
    for c in fact.get("claims") or []:
        if isinstance(c, dict) and isinstance(c.get("object"), str):
            yield c["object"]


def _claim_entity_refs(fact: dict):
    for c in fact.get("claims") or []:
        if isinstance(c, dict):
            yield from _iter_entity_refs(c.get("value"))


def _claim_wikilinks(fact: dict):
    for c in fact.get("claims") or []:
        if isinstance(c, dict):
            for s in _iter_strings(c.get("value")):
                yield from WIKILINK_RE.findall(s)


# ------------------------------------------------------------------ traversal


def _neighbors(
    fid: str, fact: dict, follow: list[str], resolve_id, edges_touching: dict[str, list[str]],
) -> set[str]:
    out: set[str] = set()
    if "object" in follow:
        out.update(r for oid in _claim_objects(fact) if (r := resolve_id(oid)))
    if "entity" in follow:
        out.update(r for eid in _claim_entity_refs(fact) if (r := resolve_id(eid)))
    if "wikilink" in follow:
        out.update(r for wid in _claim_wikilinks(fact) if (r := resolve_id(wid)))
    if "participants" in follow:
        # an edge joins the scope when it touches an in-scope concept …
        out.update(edges_touching.get(fid, []))
        # … and an in-scope edge makes its subject + participants reachable
        if is_edge(fact):
            subj = fact.get("subject")
            if isinstance(subj, str) and (r := resolve_id(subj)):
                out.add(r)
            for p in fact.get("participants") or []:
                if isinstance(p, str) and (r := resolve_id(p)):
                    out.add(r)
    out.discard(fid)
    return out


# ------------------------------------------------------------------ evaluate_scope


def evaluate_scope(ledger_root: Path, spec: dict) -> dict:
    """Evaluate a scope spec against the ledger at *ledger_root* (§12.1).

    Deterministic: seed, traverse, close. Raises ValueError on malformed
    *spec*; raises NotImplementedError for `evidence: resolved` (materializing
    citations is the read surface's job, not this library's, §12).
    """
    seed, follow, depth, evidence = _validate_spec(spec)
    if evidence == "resolved":
        raise NotImplementedError("resolved evidence chasing lands with the read surface")

    facts, _ = load_json_dir(ledger_root, "facts/*/*.json")
    live_facts: dict[str, dict] = {}
    fact_paths: dict[str, Path] = {}
    for path, fact in facts.items():
        fid = fact.get("id")
        if not isinstance(fid, str) or is_redirect(fact):
            continue
        live_facts[fid] = fact
        fact_paths[fid] = path

    lineage, _ = load_lineage(ledger_root)

    def resolve_id(ref: str) -> str | None:
        """A fact reference through at most one lineage-map hop → live id, or None (§4.1)."""
        if ref in live_facts:
            return ref
        if ref in lineage:
            target = lineage[ref]
            return target if target in live_facts else None
        return None

    # reverse index: concept id -> edges that touch it as subject/participant
    edges_touching: dict[str, list[str]] = {}
    for fid, fact in live_facts.items():
        if not is_edge(fact):
            continue
        touched: set[str] = set()
        subj = fact.get("subject")
        if isinstance(subj, str) and (r := resolve_id(subj)):
            touched.add(r)
        for p in fact.get("participants") or []:
            if isinstance(p, str) and (r := resolve_id(p)):
                touched.add(r)
        for t in touched:
            edges_touching.setdefault(t, []).append(fid)

    # ---------------------------------------------------------------- seed
    unknown_seeds: list[str] = []
    seed_ids: set[str] = set()
    if "ids" in seed:
        for raw in seed["ids"]:
            r = resolve_id(raw)
            if r is None:
                unknown_seeds.append(raw)
            else:
                seed_ids.add(r)
    elif "type" in seed:
        seed_ids = {fid for fid, f in live_facts.items() if f.get("type") == seed["type"]}
    else:
        seed_ids = {fid for fid, f in live_facts.items() if _match_predicate(seed["match"], f)}

    # ---------------------------------------------------------------- traverse + close
    depth_of: dict[str, int] = {sid: 0 for sid in seed_ids}
    visited: set[str] = set(seed_ids)
    frontier = sorted(seed_ids)
    hop = 0
    while frontier and (depth is None or hop < depth):
        next_frontier: set[str] = set()
        for fid in frontier:
            fact = live_facts.get(fid)
            if fact is None:
                continue
            for nid in _neighbors(fid, fact, follow, resolve_id, edges_touching):
                if nid not in visited:
                    visited.add(nid)
                    depth_of[nid] = hop + 1
                    next_frontier.add(nid)
        frontier = sorted(next_frontier)
        hop += 1

    members = [
        {"id": fid, "type": live_facts[fid].get("type"),
         "path": str(fact_paths[fid].relative_to(ledger_root)), "depth": depth_of[fid]}
        for fid in sorted(visited)
    ]

    result: dict = {"members": members, "unknown_seeds": sorted(set(unknown_seeds))}

    if evidence == "references":
        ev: dict[str, list[str]] = {}
        for fid in sorted(visited):
            fact = live_facts[fid]
            sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
            uris: set[str] = set()
            for c in fact.get("claims") or []:
                if not isinstance(c, dict):
                    continue
                for e in c.get("evidence") or []:
                    if not isinstance(e, dict):
                        continue
                    uri = derived_uri(sources, e.get("source"), e.get("anchor"))
                    if uri is not None:
                        uris.add(uri)
            ev[fid] = sorted(uris)
        result["evidence"] = ev

    if "roster" in follow:
        roster: dict[str, list[str]] = {}
        for fid in sorted(visited):
            fact = live_facts[fid]
            uris = {e["uri"] for e in fact.get("artifacts") or []
                    if isinstance(e, dict) and isinstance(e.get("uri"), str)}
            roster[fid] = sorted(uris)
        result["roster"] = roster

    return result
