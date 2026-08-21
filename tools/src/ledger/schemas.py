"""Schemas — `schemas/{type}.yaml` (§4.4): declared, validating shapes.

Concept types and edge types alike. A schema is data the checker reads, never
code that produces anything. Only mis-shape is an error; missing owed fields
(`expected: true`, unmet `expectations`) are frontier for the work-list,
never validation failures.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ledger.model import SLUG_RE

SCHEMA_KEYS = {"type", "description", "fields", "roster_roles", "participants",
               "expectations", "normalization_intent"}
FIELD_KEYS = {"target", "description", "expected", "values", "participant",
              "timeboxed", "elements", "value"}
ELEMENT_KEYS = {"target", "values", "description", "value"}
EXPECTATION_KEYS = {"when", "expect", "description", "id"}


def load_schemas(ledger_root: Path) -> tuple[dict[str, dict], list[str]]:
    """All schemas → ({type: schema}, shape errors)."""
    out: dict[str, dict] = {}
    errors: list[str] = []
    base = ledger_root / "schemas"
    if not base.is_dir():
        return out, errors
    for f in sorted(base.glob("*.yaml")):
        where = f"schemas/{f.name}"
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError) as e:
            errors.append(f"{where}: invalid YAML — {e}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{where}: top level must be a mapping")
            continue
        if data.get("type") != f.stem:
            errors.append(f"{where}: type {data.get('type')!r} != filename stem {f.stem!r}")
        unknown = set(data) - SCHEMA_KEYS
        if unknown:
            errors.append(f"{where}: unknown keys {sorted(unknown)}")
        intent = data.get("normalization_intent")
        if intent is not None and not isinstance(intent, str):
            errors.append(f"{where}: normalization_intent must be a string")
        fields = data.get("fields") or {}
        if not isinstance(fields, dict):
            errors.append(f"{where}: fields must be a mapping")
            fields = {}
        for fname, fspec in fields.items():
            if fspec is None:
                continue
            if not isinstance(fspec, dict):
                errors.append(f"{where}: field {fname!r} must be a mapping (or empty)")
                continue
            bad = set(fspec) - FIELD_KEYS
            if bad:
                errors.append(f"{where}: field {fname!r} unknown keys {sorted(bad)}")
            target = fspec.get("target")
            if target is not None and not (
                isinstance(target, str)
                or (isinstance(target, list)
                    and all(isinstance(t, str) for t in target))
            ):
                errors.append(f"{where}: field {fname!r} target must be a type "
                              "or a list of admissible types")
            if not isinstance(fspec.get("expected", False), bool):
                errors.append(f"{where}: field {fname!r} expected must be a bool")
            values = fspec.get("values")
            if values is not None and not (
                isinstance(values, list) and all(isinstance(v, str) for v in values)
            ):
                errors.append(f"{where}: field {fname!r} values must be a list of strings")
            if not isinstance(fspec.get("participant", False), bool):
                errors.append(f"{where}: field {fname!r} participant must be a bool")
            if not isinstance(fspec.get("timeboxed", False), bool):
                errors.append(f"{where}: field {fname!r} timeboxed must be a bool")
            value = fspec.get("value")
            if value is not None and not isinstance(value, str):
                errors.append(f"{where}: field {fname!r} value must be a string "
                              "(a §4.5 kind reference)")
            elements = fspec.get("elements")
            if elements is not None:
                if not isinstance(elements, dict):
                    errors.append(f"{where}: field {fname!r} elements must be a mapping "
                                  "of element-key to a declaration")
                else:
                    for ekey, edecl in elements.items():
                        ew = f"{where}: field {fname!r} element {ekey!r}"
                        if not isinstance(edecl, dict):
                            errors.append(f"{ew} must be a mapping (values and/or target)")
                            continue
                        bad = set(edecl) - ELEMENT_KEYS
                        if bad:
                            errors.append(f"{ew} unknown keys {sorted(bad)}")
                        etarget = edecl.get("target")
                        if etarget is not None and not (
                            isinstance(etarget, str)
                            or (isinstance(etarget, list)
                                and all(isinstance(t, str) for t in etarget))
                        ):
                            errors.append(f"{ew} target must be a type or a list of "
                                          "admissible types")
                        evalues = edecl.get("values")
                        if evalues is not None and not (
                            isinstance(evalues, list)
                            and all(isinstance(v, str) for v in evalues)
                        ):
                            errors.append(f"{ew} values must be a list of strings")
                        evalue = edecl.get("value")
                        if evalue is not None and not isinstance(evalue, str):
                            errors.append(f"{ew} value must be a string "
                                          "(a §4.5 kind reference)")
        roles = data.get("roster_roles")
        if roles is not None and not (
            isinstance(roles, list) and all(isinstance(r, str) for r in roles)
        ):
            errors.append(f"{where}: roster_roles must be a list of strings")
        participants = data.get("participants")
        if participants is not None and not (
            isinstance(participants, list) and all(isinstance(p, str) for p in participants)
        ):
            errors.append(f"{where}: participants must be a list of types (positional)")
        exp_ids: dict[str, int] = {}
        # a `when` selector that fails the shape check below would crash
        # `expectation_selects`'s `(edge_type, sel), = when.items()` at
        # evaluation time — reported here AND dropped from the returned
        # schema (the narrower drop: just the one malformed expectation,
        # never the whole file, since every other entry may be sound).
        bad_expectations: set[int] = set()
        for i, exp in enumerate(data.get("expectations") or []):
            ew = f"{where}: expectations[{i}]"
            if not isinstance(exp, dict):
                errors.append(f"{ew} must be a mapping — dropped")
                bad_expectations.add(i)
                continue
            bad = set(exp) - EXPECTATION_KEYS
            if bad:
                errors.append(f"{ew} unknown keys {sorted(bad)}")
            exp_id = exp.get("id")
            if exp_id is not None:
                if not (isinstance(exp_id, str) and SLUG_RE.match(exp_id)):
                    errors.append(f"{ew} id {exp_id!r} is not a readable slug")
                elif exp_id in exp_ids:
                    errors.append(f"{ew} id {exp_id!r} duplicates "
                                  f"expectations[{exp_ids[exp_id]}] (§4.4: unique across "
                                  "demands/ rules and all named expectations)")
                else:
                    exp_ids[exp_id] = i
            expect = exp.get("expect")
            if not (isinstance(expect, list) and expect
                    and all(isinstance(x, str) for x in expect)):
                errors.append(f"{ew} expect must be a non-empty list of field names")
            when = exp.get("when")
            if when is not None:
                if not (isinstance(when, dict) and len(when) == 1
                        and all(isinstance(v, dict) for v in when.values())):
                    errors.append(f"{ew} when must be {{edge-type: {{kind?, with?}}}} — "
                                  "dropped")
                    bad_expectations.add(i)
                else:
                    sel = next(iter(when.values()))
                    bad = set(sel) - {"kind", "with"}
                    if bad:
                        errors.append(f"{ew} when selector unknown keys {sorted(bad)}")
                    kinds = sel.get("kind")
                    if kinds is not None and not (
                        isinstance(kinds, list) and all(isinstance(k, str) for k in kinds)
                    ):
                        errors.append(f"{ew} when kind must be a list of values")
                    if "with" in sel and not isinstance(sel["with"], str):
                        errors.append(f"{ew} when with must be a fact id")
        if bad_expectations:
            data = dict(data)
            data["expectations"] = [e for i, e in enumerate(data.get("expectations") or [])
                                    if i not in bad_expectations]
        out[f.stem] = data
    return out, errors


def expectation_selects(exp: dict, fact: dict, edges: list[dict],
                        facts_by_id: dict[str, dict] | None = None,
                        lineage: dict[str, str] | None = None) -> bool:
    """Does this expectation's `when` select this fact? (§4.4)

    No `when` selects every fact of the type. A selector names an edge type;
    the fact is selected when it carries the edge's `subject` and/or is
    among its `participants` (ledger.md §4.3: a file is an edge by either),
    the `kind` claim (when `kind:` is given) takes a listed value, and the
    edge's subject/participants (when `with:` is given) include the named
    id — a fact is never selected by a `with:` naming itself. `facts_by_id`
    + `lineage` (`facts/LINEAGE.json`, §4.1), when given, resolve every
    subject/participant through at most one lineage hop before matching, so
    a merged id still selects; omitted, ids match as written (a malformed
    `when` — caught structurally at load time by `load_schemas` — simply
    never selects, rather than crashing on `when.items()`).
    """
    when = exp.get("when")
    if not when:
        return True
    if not (isinstance(when, dict) and len(when) == 1):
        return False
    (edge_type, sel), = when.items()
    if not isinstance(sel, dict):
        return False
    fid = str(fact.get("id"))
    kinds = sel.get("kind")
    other = sel.get("with")
    if other is not None and fid == other:
        return False
    if facts_by_id is not None:
        from ledger.scope import make_resolver
        resolve_id = make_resolver(facts_by_id, lineage or {})
    else:
        def resolve_id(ref: str) -> str | None:
            return ref
    for edge in edges:
        if str(edge.get("type")) != edge_type:
            continue
        parts: set[str] = set()
        subj = edge.get("subject")
        if isinstance(subj, str) and (r := resolve_id(subj)):
            parts.add(r)
        for p in edge.get("participants") or []:
            if isinstance(p, str) and (r := resolve_id(p)):
                parts.add(r)
        if fid not in parts:
            continue
        if other is not None and other not in parts:
            continue
        if kinds is not None:
            got = {str(c.get("value")) for c in edge.get("claims") or []
                   if isinstance(c, dict) and c.get("predicate") == "kind"}
            if not got & set(kinds):
                continue
        return True
    return False
