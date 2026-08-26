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
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from ledger.model import WIKILINK_RE, derived_uri, is_edge, is_redirect, load_json_dir, load_lineage

if TYPE_CHECKING:
    from ath.manifest import Reference

FOLLOW_KINDS = {"object", "entity", "wikilink", "roster", "participants"}
DEFAULT_FOLLOW = ["object", "entity", "wikilink", "participants"]
EVIDENCE_MODES = {"none", "references", "resolved"}
COMMITMENT_MODES = {"include", "exclude"}
_OPS = {"equals", "in", "glob", "matches", "exists"}
_GROUPS = {"all_of", "any_of", "none_of"}


# ------------------------------------------------------------------ spec validation


def _validate_spec(spec: dict) -> tuple[dict, list[str], int | None, str, str]:
    """Tolerant-but-strict spec validation → (seed, follow, depth, evidence,
    commitment).

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

    # §12.1, §15.5: conditional-domain facts are included by default, carried
    # with their bracket; a scope may exclude them outright.
    commitment = spec.get("commitment", "include")
    if commitment not in COMMITMENT_MODES:
        raise ValueError(f"commitment must be one of {sorted(COMMITMENT_MODES)}, "
                         f"got {commitment!r}")

    return seed, follow, depth, evidence, commitment


# ------------------------------------------------------------------ the match predicate (§10)

# A `matches` pattern beyond this length is refused outright rather than
# compiled — a cheap, generous cap ahead of the structural check below.
_MAX_MATCH_PATTERN_LEN = 512


def _nested_repeat(items, *, under_repeat: bool = False) -> bool:
    """Structural walk of a parsed regex AST (`re._parser.parse(...).data`):
    True the moment a quantified repeat's own subpattern — reached only
    through grouping/alternation, never through another repeat — itself
    carries a repeat (the `(\\w+\\s?)*` catastrophic-backtracking signature).
    Purely syntactic and conservative: it can refuse a pattern that would in
    fact terminate quickly, never the reverse."""
    for op, av in items:
        name = str(op)
        if name in ("MAX_REPEAT", "MIN_REPEAT"):
            if under_repeat:
                return True
            if _nested_repeat(av[2], under_repeat=True):
                return True
        elif name == "SUBPATTERN":
            if _nested_repeat(av[3], under_repeat=under_repeat):
                return True
        elif name == "BRANCH":
            if any(_nested_repeat(branch, under_repeat=under_repeat) for branch in av[1]):
                return True
    return False


def compile_matches(pattern: str) -> re.Pattern[str]:
    """Compile a `matches` operator's regex (§10) — the one place every
    operator-grammar caller (scope, the demand engine, harvest's
    classify_when) validates and compiles it, so a bad or dangerous pattern
    is always the same error, never re-caught differently per caller.

    Raises ValueError — never lets a bare `re.error` (not a ValueError
    subclass) or a catastrophically-backtracking match escape: the length
    cap and the nested-quantified-repeat check both run ahead of
    `re.compile`, so a `(\\w+\\s?)*`-shaped pattern is refused outright
    rather than executed against caller data.
    """
    if len(pattern) > _MAX_MATCH_PATTERN_LEN:
        raise ValueError(f"'matches' pattern exceeds {_MAX_MATCH_PATTERN_LEN} characters")
    import re._parser as sre_parse

    try:
        parsed = sre_parse.parse(pattern)
    except re.error:
        parsed = None  # let re.compile below raise the better-worded error
    if parsed is not None and _nested_repeat(parsed.data):
        raise ValueError(
            "'matches' pattern contains a nested quantified repeat (e.g. `(a+)+`) — "
            "catastrophic-backtracking-prone, refused"
        )
    try:
        return re.compile(pattern)
    except re.error as e:
        raise ValueError(f"'matches' pattern is not a valid regex — {e}") from e


def op_matches(op: str, arg: object, values: list[str]) -> bool:
    """The §10 operator grammar's single implementation — shared by scope
    evaluation, the demand engine, and harvest's classify_when (`spec/
    ledger.md` §10, §14). Each caller adapts errors to its own boundary
    convention (scope lets ValueError propagate to its `evaluate_scope`
    caller; the demand engine's evaluation never raises, §13.1 — malformed
    is the loader's job; harvest wraps into `HarvestError`) rather than
    reimplementing the operators. Raises ValueError on an unknown operator
    or a `matches` pattern `compile_matches` refuses."""
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
        rx = compile_matches(str(arg))
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


def _match_predicate(predicate: dict, fact: dict, ctx: dict | None = None) -> bool:
    """The §10 operator grammar over one fact's addressable fields, plus —
    per §15.5 — the `domain:` fact axis and the `isa:` operator under
    `type:`. *ctx* — {lineage, schemas, domains, resolve_id, references,
    corpora_roots} — feeds both; `evaluate_scope` always supplies it, so
    only a caller hand-building a predicate outside that path need worry
    about the (both-axes-inert) default."""
    if not isinstance(predicate, dict):
        raise ValueError("match predicate must be an object")
    ctx = ctx or {}
    lineage = ctx.get("lineage") or {}
    for key, spec in predicate.items():
        if key in _GROUPS:
            subs = spec if isinstance(spec, list) else [spec]
            results = [_match_predicate(s, fact, ctx) for s in subs]
            ok = {"all_of": all(results), "any_of": any(results),
                  "none_of": not any(results)}[key]
            if not ok:
                return False
            continue
        if key == "domain":
            from ledger import ontology

            values = ontology.domain_axis_values(fact, lineage)
            resolved = ontology.resolve_domain_operand(spec, lineage)
            if isinstance(resolved, dict) and len(resolved) == 1:
                (op, arg), = resolved.items()
                if op not in _OPS:
                    raise ValueError(f"unknown operator {op!r} on 'domain'")
                if not op_matches(op, arg, values):
                    return False
            elif not op_matches("equals", resolved, values):
                return False
            continue
        if key == "type" and isinstance(spec, dict) and set(spec) == {"isa"}:
            from ledger import ontology

            operand = spec.get("isa")
            if not (isinstance(operand, str) and operand):
                raise ValueError("'isa' operand must be a non-empty string")
            if not ontology.isa_matches(
                fact, operand, schemas=ctx.get("schemas") or {},
                domains=ctx.get("domains") or {}, resolve_id=ctx.get("resolve_id"),
                references=ctx.get("references") or (),
                corpora_roots=ctx.get("corpora_roots") or (),
            ):
                return False
            continue
        if not isinstance(spec, dict):
            spec = {"equals": spec}
        values = _field_values(fact, key)
        for op, arg in spec.items():
            if op not in _OPS:
                raise ValueError(f"unknown operator {op!r} on {key!r}")
            if not op_matches(op, arg, values):
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
#
# Per-kind neighbor helpers, factored out so a caller wanting a single hop
# along one kind (the demand grammar's `related:`, `spec/ledger.md` §14) can
# reuse exactly the traversal a scope evaluation performs, rather than
# reimplementing it.


def make_resolver(live_facts: dict[str, dict], lineage: dict[str, str]):
    """A fact reference resolver — at most one lineage-map hop → live id, or
    None (§4.1) — closed over *live_facts*/*lineage*, shared by scope
    evaluation and the demand engine's `related:`/`id:` conditions (§14)."""
    def resolve_id(ref: str) -> str | None:
        if ref in live_facts:
            return ref
        target = lineage.get(ref)
        return target if target in live_facts else None
    return resolve_id


def object_neighbors(fact: dict, resolve_id) -> set[str]:
    return {r for oid in _claim_objects(fact) if (r := resolve_id(oid))}


def entity_neighbors(fact: dict, resolve_id) -> set[str]:
    return {r for eid in _claim_entity_refs(fact) if (r := resolve_id(eid))}


def wikilink_neighbors(fact: dict, resolve_id) -> set[str]:
    return {r for wid in _claim_wikilinks(fact) if (r := resolve_id(wid))}


def participant_neighbors(
    fid: str, fact: dict, resolve_id, edges_touching: dict[str, list[str]],
) -> set[str]:
    """Edge-participation neighbors (§12.1): edges touching *fid* … and,
    when *fact* is itself an edge, its subject + participants."""
    out: set[str] = set()
    out.update(edges_touching.get(fid, []))
    if is_edge(fact):
        subj = fact.get("subject")
        if isinstance(subj, str) and (r := resolve_id(subj)):
            out.add(r)
        for p in fact.get("participants") or []:
            if isinstance(p, str) and (r := resolve_id(p)):
                out.add(r)
    return out


def build_edges_touching(edges: list[dict], resolve_id) -> dict[str, list[str]]:
    """Reverse index: concept id -> ids of edges touching it as subject or
    participant, lineage-resolved. Shared by scope evaluation and the demand
    engine's `related: {via: edge}` neighbor set (§14). *edges* is the
    already-filtered edge-fact list, the shape every caller already has on
    hand."""
    edges_touching: dict[str, list[str]] = {}
    for fact in edges:
        fid = str(fact.get("id"))
        touched: set[str] = set()
        subj = fact.get("subject")
        if isinstance(subj, str) and (r := resolve_id(subj)):
            touched.add(r)
        for p in fact.get("participants") or []:
            if isinstance(p, str) and (r := resolve_id(p)):
                touched.add(r)
        for t in touched:
            edges_touching.setdefault(t, []).append(fid)
    return edges_touching


def _neighbors(
    fid: str, fact: dict, follow: list[str], resolve_id, edges_touching: dict[str, list[str]],
) -> set[str]:
    out: set[str] = set()
    if "object" in follow:
        out.update(object_neighbors(fact, resolve_id))
    if "entity" in follow:
        out.update(entity_neighbors(fact, resolve_id))
    if "wikilink" in follow:
        out.update(wikilink_neighbors(fact, resolve_id))
    if "participants" in follow:
        out.update(participant_neighbors(fid, fact, resolve_id, edges_touching))
    out.discard(fid)
    return out


# ------------------------------------------------------------------ evaluate_scope


def evaluate_scope(
    ledger_root: Path,
    spec: dict,
    *,
    references: Sequence[Reference] = (),
    corpora_roots: Sequence[Path] = (),
) -> dict:
    """Evaluate a scope spec against the ledger at *ledger_root* (§12.1).

    Deterministic: seed, traverse, close. Raises ValueError on malformed
    *spec*; raises NotImplementedError for `evidence: resolved` (materializing
    citations is the read surface's job, not this library's, §12).

    *references*/*corpora_roots* feed the §15.5 `isa:` operator's spine
    unification (`refdata.spine.resolve_term`) when a seed's `type:` names a
    spine class by label where the declared chain carries a native id, or
    vice versa — optional; omitted, `isa:` still matches every declared
    shared-tier/domain chain literally.
    """
    from ledger import ontology
    from ledger.schemas import load_schemas

    seed, follow, depth, evidence, commitment = _validate_spec(spec)
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
    schemas, _ = load_schemas(ledger_root)
    domains = ontology.load_domains(live_facts)
    resolve_id = make_resolver(live_facts, lineage)

    # §12.1/§15.5: the commitment parameter — `exclude` drops conditional-
    # domain facts from the WHOLE evaluation (seed and traversal alike), as
    # if they were never in the ledger for this run; `include` (default)
    # keeps them, annotated below with their bracket.
    if commitment == "exclude":
        live_facts = {
            fid: f for fid, f in live_facts.items()
            if ontology.commitment_for_fact(f, domains, resolve_id) != "conditional"
        }
        fact_paths = {fid: p for fid, p in fact_paths.items() if fid in live_facts}
        resolve_id = make_resolver(live_facts, lineage)

    ctx = {
        "lineage": lineage, "schemas": schemas, "domains": domains, "resolve_id": resolve_id,
        "references": references, "corpora_roots": corpora_roots,
    }
    edges_touching = build_edges_touching(
        [f for f in live_facts.values() if is_edge(f)], resolve_id)

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
        seed_ids = {fid for fid, f in live_facts.items()
                    if _match_predicate(seed["match"], f, ctx)}

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

    # §12.1/§15.5: every visited fact's commitment bracket, carried alongside
    # the member list regardless of the `commitment` parameter — under
    # `exclude` every entry here reads "real" (conditional facts never made
    # it into `visited`); under `include` (default) a consumer sees exactly
    # which members are depiction, never world-fact, without re-deriving it.
    commitment_of = {
        fid: ontology.commitment_for_fact(live_facts[fid], domains, resolve_id)
        for fid in sorted(visited)
    }
    members = [
        {"id": fid, "type": live_facts[fid].get("type"),
         "path": str(fact_paths[fid].relative_to(ledger_root)), "depth": depth_of[fid],
         "commitment": commitment_of[fid]}
        for fid in sorted(visited)
    ]

    result: dict = {
        "members": members, "unknown_seeds": sorted(set(unknown_seeds)),
        "commitment": commitment_of,
    }

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
