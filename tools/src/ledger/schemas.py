"""Schemas — `schemas/{type}.yaml` (§4.4): declared, validating shapes.

Concept types and edge types alike. A schema is data the checker reads, never
code that produces anything. Only mis-shape is an error; missing owed fields
(`expected: true`, unmet `expectations`) are frontier for the work-list,
never validation failures.
"""

from __future__ import annotations

from pathlib import Path

import yaml

SCHEMA_KEYS = {"type", "description", "fields", "roster_roles", "participants",
               "expectations"}
FIELD_KEYS = {"target", "description", "expected", "values", "participant"}
EXPECTATION_KEYS = {"when", "expect", "description"}


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
        for i, exp in enumerate(data.get("expectations") or []):
            ew = f"{where}: expectations[{i}]"
            if not isinstance(exp, dict):
                errors.append(f"{ew} must be a mapping")
                continue
            bad = set(exp) - EXPECTATION_KEYS
            if bad:
                errors.append(f"{ew} unknown keys {sorted(bad)}")
            expect = exp.get("expect")
            if not (isinstance(expect, list) and expect
                    and all(isinstance(x, str) for x in expect)):
                errors.append(f"{ew} expect must be a non-empty list of field names")
            when = exp.get("when")
            if when is not None:
                if not (isinstance(when, dict) and len(when) == 1
                        and all(isinstance(v, dict) for v in when.values())):
                    errors.append(f"{ew} when must be {{edge-type: {{kind?, with?}}}}")
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
        out[f.stem] = data
    return out, errors


def expectation_selects(exp: dict, fact: dict, edges: list[dict]) -> bool:
    """Does this expectation's `when` select this fact? (§4.4)

    No `when` selects every fact of the type. A selector names an edge type;
    the fact is selected when it participates in an edge of that type whose
    `kind` claim (when `kind:` is given) takes a listed value and whose
    participants (when `with:` is given) include the named id — a fact is
    never selected by a `with:` naming itself.
    """
    when = exp.get("when")
    if not when:
        return True
    fid = str(fact.get("id"))
    (edge_type, sel), = when.items()
    kinds = sel.get("kind")
    other = sel.get("with")
    if other is not None and fid == other:
        return False
    for edge in edges:
        if str(edge.get("type")) != edge_type:
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
        return True
    return False
