"""Demands — the completeness rule layer (`spec/ledger.md` §14).

Ledger integrity's third third: grounding is verified (§13.2), coherence is
declared (§11), completeness is declared here. A demand rule is data, not
code — `demands/{slug}.yaml` — evaluated deterministically against one fact
at a time; schema `expectations:` (§4.4) are the type-local sugar over the
same grammar, absorbed unchanged through this module's one engine so the
§7.4 work-list frontier and the interactive surface (`ath ledger demands`)
never disagree.

A demand is **open** (owed, unmet), **satisfied** (the demanded claim
exists), or **blocked** (an open/standing interpretation names the rule in a
`needs` entry's `demand:`, §7.2) — blocked state is derived, never stored.
Evaluation itself never produces an error or a warning (§13.1 "Demands");
rule *well-formedness* is checked at load time, here, and surfaced by the
caller.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

import yaml

from ledger.schemas import expectation_selects
from ledger.scope import (
    build_edges_touching,
    entity_neighbors,
    make_resolver,
    object_neighbors,
    wikilink_neighbors,
)

RULE_KEYS = {"id", "description", "when", "owes"}
OWE_KEYS = {"field", "description"}
CONDITION_KEYS = {"type", "claim", "roster", "edge", "id", "related",
                  "all_of", "any_of", "none_of"}
CLAIM_COND_KEYS = {"predicate", "value", "object"}
ROSTER_COND_KEYS = {"role", "exists"}
EDGE_SEL_KEYS = {"kind", "with", "target_type"}
RELATED_KEYS = {"via", "edge", "where", "exists"}
# The fact-reaching §12.1 traversal kinds. `roster` is deliberately absent:
# roster rows target corpus records, never facts (§4.2) — a roster `via`
# could never hold, so it is malformed, not vacuous (§14).
VIA_KINDS = {"object", "entity", "wikilink", "edge"}
_OPS = {"equals", "in", "glob", "matches", "exists"}
_GROUPS = {"all_of", "any_of", "none_of"}


# --------------------------------------------------------------------- loading


def load_demand_rules(ledger_root: Path) -> tuple[dict[str, dict], list[str]]:
    """All declared demand rules → ({id: rule}, well-formedness errors).

    Tolerant of a bad file (dropped, error string emitted) but strict about
    what's kept — `demands/*.yaml`, rule id == filename stem. A rule with no
    `when` or a malformed `owes` is dropped; other shape errors are reported
    but the rule is still kept (mirrors `load_schemas`/`load_kinds`).
    """
    out: dict[str, dict] = {}
    errors: list[str] = []
    base = ledger_root / "demands"
    if not base.is_dir():
        return out, errors
    for f in sorted(base.glob("*.yaml")):
        where = f"demands/{f.name}"
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError) as e:
            errors.append(f"{where}: invalid YAML — {e}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{where}: top level must be a mapping")
            continue
        if data.get("id") != f.stem:
            errors.append(f"{where}: id {data.get('id')!r} != filename stem {f.stem!r}")
            continue
        unknown = set(data) - RULE_KEYS
        if unknown:
            errors.append(f"{where}: unknown keys {sorted(unknown)}")
        if "when" not in data:
            errors.append(f"{where}: when is required")
        else:
            errors.extend(_validate_condition(data.get("when"), f"{where}: when"))
        owes = data.get("owes")
        if not (isinstance(owes, list) and owes):
            errors.append(f"{where}: owes must be a non-empty list of "
                          "{field, description?}")
        else:
            for i, owe in enumerate(owes):
                ow = f"{where}: owes[{i}]"
                if not isinstance(owe, dict):
                    errors.append(f"{ow} must be a mapping")
                    continue
                bad = set(owe) - OWE_KEYS
                if bad:
                    errors.append(f"{ow} unknown keys {sorted(bad)}")
                if not (isinstance(owe.get("field"), str) and owe.get("field")):
                    errors.append(f"{ow} field is required and must be a non-empty string")
        out[f.stem] = data
    return out, errors


def _validate_op(op: object, where: str) -> list[str]:
    """One value/role op — a scalar (exact equals) or a single-key {op: arg}
    dict from the §10 operator grammar."""
    if not isinstance(op, dict):
        return []  # a bare scalar is legitimate — implicit equals
    if len(op) != 1:
        return [f"{where}: operator dict must carry exactly one operator"]
    (k, arg), = op.items()
    if k not in _OPS:
        return [f"{where}: unknown operator {k!r} (allowed: {sorted(_OPS)})"]
    if k == "in" and not isinstance(arg, list):
        return [f"{where}: 'in' operator requires a list"]
    if k == "exists" and not isinstance(arg, bool):
        return [f"{where}: 'exists' operator requires a bool"]
    if k in ("glob", "matches") and not isinstance(arg, str):
        return [f"{where}: {k!r} operator requires a string"]
    if k == "matches":
        try:
            re.compile(str(arg))
        except re.error as e:
            return [f"{where}: 'matches' pattern is not a valid regex — {e}"]
    return []


def _validate_edge_selector(spec: object, where: str) -> list[str]:
    """The §4.4 `{edge-type: {kind?, with?, target_type?}}` selector shape —
    shared by the `edge:` condition and `related.edge` (§14)."""
    if not (isinstance(spec, dict) and len(spec) == 1):
        return [f"{where}: must be {{edge-type: {{...}}}}"]
    (etype, sel), = spec.items()
    errors: list[str] = []
    if not isinstance(etype, str):
        errors.append(f"{where}: edge-type name must be a string")
    if not isinstance(sel, dict):
        errors.append(f"{where}.{etype}: selector must be a mapping")
        return errors
    bad = set(sel) - EDGE_SEL_KEYS
    if bad:
        errors.append(f"{where}.{etype}: unknown keys {sorted(bad)}")
    kinds = sel.get("kind")
    if kinds is not None and not (
        isinstance(kinds, list) and all(isinstance(k, str) for k in kinds)
    ):
        errors.append(f"{where}.{etype}.kind: must be a list of strings")
    if "with" in sel and not isinstance(sel["with"], str):
        errors.append(f"{where}.{etype}.with: must be a fact id")
    tt = sel.get("target_type")
    if tt is not None and not (
        isinstance(tt, str)
        or (isinstance(tt, list) and all(isinstance(t, str) for t in tt))
    ):
        errors.append(f"{where}.{etype}.target_type: must be a type or a "
                      "list of types")
    return errors


def _validate_related(spec: object, where: str) -> list[str]:
    """`related: {via, edge?, where?, exists?}` (§14) — one hop, deliberate:
    `where` parses under this same grammar but MUST NOT itself carry
    `related:` (checked by the caller via `allow_related=False`)."""
    if not isinstance(spec, dict):
        return [f"{where}: must be a mapping"]
    errors: list[str] = []
    bad = set(spec) - RELATED_KEYS
    if bad:
        errors.append(f"{where}: unknown keys {sorted(bad)}")
    via = spec.get("via")
    if via not in VIA_KINDS:
        errors.append(f"{where}.via: must be one of {sorted(VIA_KINDS)}")
    if "edge" in spec:
        if via != "edge":
            errors.append(f"{where}.edge: only admissible under via: edge")
        else:
            errors.extend(_validate_edge_selector(spec["edge"], f"{where}.edge"))
    if "where" in spec:
        errors.extend(_validate_condition(spec["where"], f"{where}.where", allow_related=False))
    if "exists" in spec and not isinstance(spec["exists"], bool):
        errors.append(f"{where}.exists: must be a bool")
    return errors


def _validate_condition(cond: object, where: str, *, allow_related: bool = True) -> list[str]:
    """One `when` (sub-)condition against the §14 grammar. *allow_related*
    is False while validating a `related.where` — one hop is deliberate, so
    `related:` may not nest inside a `where`."""
    if not isinstance(cond, dict) or not cond:
        return [f"{where}: condition must be a non-empty mapping"]
    errors: list[str] = []
    bad = set(cond) - CONDITION_KEYS
    if bad:
        errors.append(f"{where}: unknown condition key(s) {sorted(bad)}")
    for key, spec in cond.items():
        if key == "related" and not allow_related:
            errors.append(f"{where}.related: not allowed inside a where — "
                          "one hop is deliberate (§14)")
        elif key in _GROUPS:
            if not (isinstance(spec, list) and spec):
                errors.append(f"{where}.{key}: must be a non-empty list of conditions")
                continue
            for i, sub in enumerate(spec):
                errors.extend(_validate_condition(sub, f"{where}.{key}[{i}]",
                                                  allow_related=allow_related))
        elif key == "type":
            ok = isinstance(spec, str) or (
                isinstance(spec, dict) and set(spec) == {"in"}
                and isinstance(spec["in"], list) and all(isinstance(x, str) for x in spec["in"])
            )
            if not ok:
                errors.append(f"{where}.type: must be a string or {{in: [strings]}}")
        elif key == "claim":
            if not isinstance(spec, dict):
                errors.append(f"{where}.claim: must be a mapping")
                continue
            bad = set(spec) - CLAIM_COND_KEYS
            if bad:
                errors.append(f"{where}.claim: unknown keys {sorted(bad)}")
            if not (isinstance(spec.get("predicate"), str) and spec.get("predicate")):
                errors.append(f"{where}.claim: predicate is required and must be a "
                              "non-empty string")
            for opkey in ("value", "object"):
                if opkey in spec:
                    errors.extend(_validate_op(spec[opkey], f"{where}.claim.{opkey}"))
        elif key == "roster":
            if not isinstance(spec, dict):
                errors.append(f"{where}.roster: must be a mapping")
                continue
            bad = set(spec) - ROSTER_COND_KEYS
            if bad:
                errors.append(f"{where}.roster: unknown keys {sorted(bad)}")
            if "role" in spec:
                errors.extend(_validate_op(spec["role"], f"{where}.roster.role"))
            if "exists" in spec and not isinstance(spec["exists"], bool):
                errors.append(f"{where}.roster.exists: must be a bool")
        elif key == "edge":
            errors.extend(_validate_edge_selector(spec, f"{where}.edge"))
        elif key == "id":
            errors.extend(_validate_op(spec, f"{where}.id"))
        elif key == "related":
            errors.extend(_validate_related(spec, f"{where}.related"))
        # an unknown key is already flagged above; nothing further to validate
    return errors


# ------------------------------------------------------------------ evaluation


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
    return False


def _op_test(op: object, values: list[str]) -> bool:
    if isinstance(op, dict):
        if len(op) != 1:
            return False
        (k, arg), = op.items()
        return k in _OPS and _op_matches(k, arg, values)
    return _op_matches("equals", op, values)  # a bare scalar is exact equals


def _values_of(v: object) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


def _resolve_operand(v: object, lineage: dict[str, str]) -> object:
    """One `id:` operand through at most one lineage-map hop (§4.1) — a rule
    naming a retired id still matches the living successor it merged into."""
    return lineage.get(str(v), v)


def _id_matches(spec: object, fact: dict, lineage: dict[str, str]) -> bool:
    """`id:` condition (§14): the operator grammar over the fact's own
    (living) id. `equals`/`in` operands resolve through the lineage map
    before comparison; `glob`/`matches` match the living id as written."""
    if isinstance(spec, dict) and len(spec) == 1:
        (k, arg), = spec.items()
        if k == "equals":
            spec = {k: _resolve_operand(arg, lineage)}
        elif k == "in" and isinstance(arg, list):
            spec = {k: [_resolve_operand(a, lineage) for a in arg]}
    elif not isinstance(spec, dict):
        spec = _resolve_operand(spec, lineage)  # bare scalar — implicit equals
    return _op_test(spec, [str(fact.get("id"))])


def _type_matches(spec: object, fact: dict) -> bool:
    ftype = str(fact.get("type"))
    if isinstance(spec, str):
        return ftype == spec
    if isinstance(spec, dict) and "in" in spec:
        return ftype in [str(x) for x in spec["in"] or []]
    return False


def _claim_matches(spec: dict, fact: dict) -> bool:
    """Matches when the fact carries a claim under `spec['predicate']` whose
    value/object (each, if given) satisfies its operator — one claim must
    satisfy both sides; array-valued claims match on any element (§14)."""
    pred = spec.get("predicate")
    for c in fact.get("claims") or []:
        if not isinstance(c, dict) or c.get("predicate") != pred:
            continue
        if "value" in spec and not _op_test(spec["value"], _values_of(c.get("value"))):
            continue
        if "object" in spec and not _op_test(spec["object"], _values_of(c.get("object"))):
            continue
        return True
    return False


def _roster_matches(spec: dict, fact: dict) -> bool:
    entries = [e for e in fact.get("artifacts") or [] if isinstance(e, dict)]
    role_op = spec.get("role")
    if role_op is not None:
        values = [str(e.get("role")) for e in entries if e.get("role") is not None]
        matched = _op_test(role_op, values)
    else:
        matched = bool(entries)
    if "exists" in spec:
        return matched == bool(spec["exists"])
    return matched


def _edge_matches(spec: dict, fact: dict, edges: list[dict],
                  facts_by_id: dict[str, dict]) -> bool:
    """The §4.4 `when` selector, generalized with `target_type`: the fact
    participates in an edge of the named type, restricted by `kind` claim
    values, a co-participant `with`, or a co-participant's type. Never
    selected by `with:` naming itself."""
    if len(spec) != 1:
        return False
    (etype, sel), = spec.items()
    if not isinstance(sel, dict):
        return False
    fid = str(fact.get("id"))
    kinds = sel.get("kind")
    other = sel.get("with")
    if other is not None and fid == other:
        return False
    target_type = sel.get("target_type")
    target_types = (target_type if isinstance(target_type, list)
                     else [target_type] if target_type else None)
    for edge in edges:
        if str(edge.get("type")) != str(etype):
            continue
        parts = [str(p) for p in edge.get("participants") or []]
        if fid not in parts:
            continue
        if other is not None and other not in parts:
            continue
        if kinds is not None:
            got = {str(c.get("value")) for c in edge.get("claims") or []
                   if isinstance(c, dict) and c.get("predicate") == "kind"}
            if not got & set(kinds):
                continue
        if target_types is not None:
            others = [p for p in parts if p != fid]
            if not any(str((facts_by_id.get(p) or {}).get("type")) in target_types
                       for p in others):
                continue
        return True
    return False


def _edge_neighbors(edge_sel: dict | None, fid: str, edges: list[dict],
                    facts_by_id: dict[str, dict], resolve_id,
                    edges_touching: dict[str, list[str]]) -> list[dict]:
    """`related: {via: edge}` neighbors (§14): the edges *fid* participates
    in, narrowed by the optional §4.4 selector — the neighbor IS the edge
    fact itself (unlike the other `via` kinds, whose neighbors are the
    referenced facts)."""
    edges_by_id = {str(e.get("id")): e for e in edges}
    candidates = [edges_by_id[eid] for eid in edges_touching.get(fid, []) if eid in edges_by_id]
    if edge_sel is None:
        return candidates
    (etype, sel), = edge_sel.items()
    kinds = sel.get("kind")
    other = sel.get("with")
    if other is not None and fid == other:
        return []
    target_type = sel.get("target_type")
    target_types = (target_type if isinstance(target_type, list)
                     else [target_type] if target_type else None)
    out: list[dict] = []
    for edge in candidates:
        if str(edge.get("type")) != str(etype):
            continue
        parts: set[str] = set()
        subj = edge.get("subject")
        if isinstance(subj, str) and (r := resolve_id(subj)):
            parts.add(r)
        for p in edge.get("participants") or []:
            if isinstance(p, str) and (r := resolve_id(p)):
                parts.add(r)
        if other is not None and other not in parts:
            continue
        if kinds is not None:
            got = {str(c.get("value")) for c in edge.get("claims") or []
                   if isinstance(c, dict) and c.get("predicate") == "kind"}
            if not got & set(kinds):
                continue
        if target_types is not None:
            others = parts - {fid}
            if not any(str((facts_by_id.get(p) or {}).get("type")) in target_types
                       for p in others):
                continue
        out.append(edge)
    return out


def _neighbor_facts(spec: dict, fact: dict, edges: list[dict],
                    facts_by_id: dict[str, dict], lineage: dict[str, str]) -> list[dict]:
    """The one-hop neighbor set for a `related:` condition (§14, §12.1):
    lineage-resolved, deduplicated, deterministic — exactly what a scope
    evaluation's traverse step would take for *via*."""
    via = spec.get("via")
    fid = str(fact.get("id"))
    resolve_id = make_resolver(facts_by_id, lineage)
    if via == "edge":
        edges_touching = build_edges_touching(edges, resolve_id)
        neighbors = _edge_neighbors(spec.get("edge"), fid, edges, facts_by_id, resolve_id,
                                    edges_touching)
        return sorted(neighbors, key=lambda e: str(e.get("id")))
    if via == "object":
        ids = object_neighbors(fact, resolve_id)
    elif via == "entity":
        ids = entity_neighbors(fact, resolve_id)
    elif via == "wikilink":
        ids = wikilink_neighbors(fact, resolve_id)
    else:  # a malformed via caught at load time — no neighbors
        ids = set()
    ids.discard(fid)
    return [facts_by_id[i] for i in sorted(ids) if i in facts_by_id]


def _related_matches(spec: dict, fact: dict, edges: list[dict], facts_by_id: dict[str, dict],
                     lineage: dict[str, str]) -> bool:
    """`related:` condition (§14): one hop, lineage-resolved. `exists: true`
    (default) holds iff some neighbor matches `where` (or any neighbor
    exists, when `where` is omitted); `exists: false` holds iff none does."""
    neighbors = _neighbor_facts(spec, fact, edges, facts_by_id, lineage)
    where = spec.get("where")
    if where is None:
        matched = bool(neighbors)
    else:
        matched = any(condition_matches(where, n, edges, facts_by_id, lineage=lineage)
                      for n in neighbors)
    return matched == bool(spec.get("exists", True))


def condition_matches(cond: dict, fact: dict, edges: list[dict],
                      facts_by_id: dict[str, dict], *,
                      lineage: dict[str, str] | None = None) -> bool:
    """Does this `when` (sub-)condition select *fact*? Several keys at the
    top level are an implicit `all_of`; missing-is-false throughout.
    *lineage* — the `facts/LINEAGE.json` map (§4.1) — resolves `id:`
    operands and `related:` neighbor hops; callers with no lineage on hand
    may omit it (no rows resolve, correct for a lineage-free ledger)."""
    if not isinstance(cond, dict) or not cond:
        return False
    lineage = lineage or {}
    for key, spec in cond.items():
        if key == "all_of":
            ok = isinstance(spec, list) and bool(spec) and all(
                condition_matches(s, fact, edges, facts_by_id, lineage=lineage) for s in spec)
        elif key == "any_of":
            ok = isinstance(spec, list) and any(
                condition_matches(s, fact, edges, facts_by_id, lineage=lineage) for s in spec)
        elif key == "none_of":
            ok = isinstance(spec, list) and not any(
                condition_matches(s, fact, edges, facts_by_id, lineage=lineage) for s in spec)
        elif key == "type":
            ok = _type_matches(spec, fact)
        elif key == "claim":
            ok = isinstance(spec, dict) and _claim_matches(spec, fact)
        elif key == "roster":
            ok = isinstance(spec, dict) and _roster_matches(spec, fact)
        elif key == "edge":
            ok = isinstance(spec, dict) and _edge_matches(spec, fact, edges, facts_by_id)
        elif key == "id":
            ok = _id_matches(spec, fact, lineage)
        elif key == "related":
            ok = isinstance(spec, dict) and _related_matches(spec, fact, edges, facts_by_id,
                                                              lineage)
        else:
            ok = False  # unknown key — well-formedness is caught at load time
        if not ok:
            return False
    return True


def when_label(when: object) -> str:
    """A compact rendering of an expectation's selector — the description
    fallback for an unnamed/undescribed expectation, shared by evaluation
    (below) and the VOCAB "Demand rules" listing (`views.fresh_vocab`)."""
    if not isinstance(when, dict) or not when:
        return "expected"
    (etype, sel), = when.items()
    bits = [str(etype)]
    if isinstance(sel, dict):
        if sel.get("kind"):
            bits.append("kind " + "/".join(str(k) for k in sel["kind"]))
        if sel.get("with"):
            bits.append(f"with {sel['with']}")
    return " ".join(bits)


def _field_shape(schema: dict, field_name: str, kinds: dict[str, dict]) -> dict:
    """The owed field's own declared answer shape (§4.4, §4.5): a value
    kind, a closed `values:` vocabulary, or a relational `target` type —
    whichever exists; `{}` when the field carries none (including when it
    isn't declared at all, e.g. the reserved `period` timebox)."""
    fspec = (schema.get("fields") or {}).get(field_name) if isinstance(schema, dict) else None
    if not isinstance(fspec, dict):
        return {}
    fkind = fspec.get("value")
    if isinstance(fkind, str):
        shape: dict = {"value": fkind}
        if fkind in kinds:
            shape["kind"] = kinds[fkind]
        return shape
    values = fspec.get("values")
    if isinstance(values, list):
        return {"values": values}
    target = fspec.get("target")
    if target is not None:
        return {"target": target}
    return {}


def _is_satisfied(fact: dict, field_name: str) -> bool:
    """The same presence test the §7.4 owed-field frontier uses: the
    reserved name `period` reads the fact's own timebox; anything else is a
    carried claim predicate."""
    if field_name == "period":
        return bool(fact.get("period"))
    carried = {str(c.get("predicate")) for c in fact.get("claims") or [] if isinstance(c, dict)}
    return field_name in carried


def _satisfying_claim(fact: dict, field_name: str) -> str | None:
    """The claim id satisfying an owed field — the first (claim-list order)
    claim under *field_name*, deterministic display-time provenance. `None`
    for the reserved `period` name (the fact's own timebox, not a claim) or
    when no id is carried."""
    if field_name == "period":
        return None
    for c in fact.get("claims") or []:
        if isinstance(c, dict) and c.get("predicate") == field_name and c.get("id") is not None:
            return str(c["id"])
    return None


def format_shape(shape: dict) -> str:
    """A compact one-line rendering of an owed field's answer shape (§14),
    for the interactive surface and the open-questions Demands section —
    `""` when nothing is declared (callers omit the line entirely rather
    than print "shape: none")."""
    if not shape:
        return ""
    if "values" in shape:
        return "one of: " + ", ".join(str(v) for v in shape["values"])
    if "target" in shape:
        target = shape["target"]
        targets = target if isinstance(target, list) else [target]
        return "target: " + "|".join(str(t) for t in targets)
    if "value" in shape:
        kind = shape.get("kind")
        if not isinstance(kind, dict):
            return f"shape: {shape['value']}"
        fields = kind.get("shape") if isinstance(kind.get("shape"), dict) else {}
        bits = []
        for fname, entry in fields.items():
            constraint = entry.get("constraint") if isinstance(entry, dict) else None
            bits.append(f"{fname}: {constraint}" if constraint else str(fname))
        required = kind.get("required") or []
        req = f" required: {', '.join(str(r) for r in required)}" if required else ""
        return f"shape: {kind.get('kind') or shape['value']} {{{', '.join(bits)}}}{req}"
    return ""


def named_expectations(schemas: dict[str, dict]) -> dict[str, tuple[str, dict]]:
    """{expectation id: (fact type, expectation)} across every schema (§4.4)
    — first-seen wins on a duplicate id (an authoring error `check` flags
    separately, §13.1); this collapsed view is for usage/description display
    (`views.fresh_vocab`) and the blockable-namespace helper below."""
    out: dict[str, tuple[str, dict]] = {}
    for ftype, schema in schemas.items():
        if not isinstance(schema, dict):
            continue
        for exp in schema.get("expectations") or []:
            if isinstance(exp, dict) and isinstance(exp.get("id"), str) \
                    and exp["id"] not in out:
                out[exp["id"]] = (ftype, exp)
    return out


def blockable_ids(rules: dict[str, dict], schemas: dict[str, dict]) -> set[str]:
    """The full blockable-id namespace (§13.1, §14): declared `demands/` rule
    ids plus named expectation ids — the only two kinds a needs entry's
    `demand:` may reference. Positional expectation display ids
    (`expectation:{type}[{i}]`) and unconditional `expected:{type}.{field}`
    ids are display-only and never a blocking target."""
    return set(rules) | set(named_expectations(schemas))


def _blocking_need(fact_id: str, rule_id: str, interps: list[dict]) -> dict | None:
    """An open/standing interpretation `about`ing *fact_id* with a `needs`
    entry naming *rule_id* in `demand:` — the blocking need, plus its
    interpretation id, or None (§14: blocked is derived, never stored)."""
    for interp in interps:
        if not isinstance(interp, dict) or interp.get("status") not in ("open", "standing"):
            continue
        about = [str(a) for a in interp.get("about") or []]
        if fact_id not in about:
            continue
        for n in interp.get("needs") or []:
            if isinstance(n, dict) and n.get("demand") == rule_id:
                need = dict(n)
                need["interpretation"] = str(interp.get("id"))
                return need
    return None


def evaluate_demands(
    fact: dict,
    *,
    rules: dict[str, dict],
    schemas: dict[str, dict],
    kinds: dict[str, dict],
    facts_by_id: dict[str, dict],
    edges: list[dict],
    interps: list[dict] | dict[object, dict],
    lineage: dict[str, str] | None = None,
) -> list[dict]:
    """Every demand *fact* currently carries (§14), deterministic.

    One engine over three sources — cross-type `demands/*.yaml` rules,
    schema `expectations:` (§4.4, absorbed unchanged as sugar; a named entry's
    `id:` is its rule id, an unnamed entry keeps the positional display id
    `expectation:{type}[{i}]`), and unconditionally owed fields
    (`expected: true`, rule id `expected:{type}.{field}`) — so the §7.4
    work-list and the interactive surface (`ath ledger demands`) read off
    the same ground truth. Demands come back in every state, satisfied
    included; callers filter for display. Blocked-state derivation only ever
    fires for a rule id in the blockable namespace (§13.1: declared rules and
    named expectations) — a positional or `expected:*` id can never be a
    needs entry's blocking target, so it stays open until satisfied.

    *lineage* — `facts/LINEAGE.json` (§4.1) — feeds a rule `when`'s `id:` and
    `related:` conditions (§14); callers with none on hand may omit it.
    """
    interp_list = list(interps.values()) if isinstance(interps, dict) else list(interps)
    fact_id = str(fact.get("id"))
    ftype = str(fact.get("type"))
    schema = schemas.get(ftype) if isinstance(schemas.get(ftype), dict) else {}
    blockable = blockable_ids(rules, schemas)
    out: list[dict] = []

    def make(rule_id: str, field_name: str, why: str) -> None:
        if _is_satisfied(fact, field_name):
            state, need = "satisfied", None
        else:
            need = _blocking_need(fact_id, rule_id, interp_list) if rule_id in blockable else None
            state = "blocked" if need is not None else "open"
        d = {
            "rule": rule_id, "fact": fact_id, "field": field_name, "state": state,
            "why": why, "shape": _field_shape(schema, field_name, kinds),
        }
        if need is not None:
            d["need"] = need
        if state == "satisfied":
            satisfied_by = _satisfying_claim(fact, field_name)
            if satisfied_by is not None:
                d["satisfied_by"] = satisfied_by
        out.append(d)

    for rule_id, rule in sorted(rules.items()):
        when = rule.get("when")
        if not isinstance(when, dict) or not condition_matches(
            when, fact, edges, facts_by_id, lineage=lineage,
        ):
            continue
        for owe in rule.get("owes") or []:
            if not isinstance(owe, dict):
                continue
            field_name = str(owe.get("field", ""))
            if not field_name:
                continue
            why = str(owe.get("description") or rule.get("description") or "")
            make(rule_id, field_name, why)

    for i, exp in enumerate(schema.get("expectations") or []):
        if not isinstance(exp, dict) or not expectation_selects(exp, fact, edges):
            continue
        exp_id = exp.get("id")
        rule_id = str(exp_id) if isinstance(exp_id, str) else f"expectation:{ftype}[{i}]"
        why = str(exp.get("description") or when_label(exp.get("when")))
        for field_name in exp.get("expect") or []:
            make(rule_id, str(field_name), why)

    for field_name in sorted(schema.get("fields") or {}):
        fspec = (schema.get("fields") or {}).get(field_name)
        if isinstance(fspec, dict) and fspec.get("expected"):
            rule_id = f"expected:{ftype}.{field_name}"
            why = str(fspec.get("description") or f"owed unconditionally ({ftype} schema)")
            make(rule_id, field_name, why)

    return out
