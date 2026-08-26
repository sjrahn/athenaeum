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
               "expectations", "normalization_intent", "extends", "requires_domain"}
# A domain type sense (`schemas/{domain-id}/{type}.yaml`, §15.4) carries the
# same grammar plus one extra top-level key.
DOMAIN_SCHEMA_KEYS = SCHEMA_KEYS | {"domain"}
FIELD_KEYS = {"target", "description", "expected", "values", "participant",
              "timeboxed", "elements", "value", "extends", "invariants"}
ELEMENT_KEYS = {"target", "values", "description", "value"}
EXPECTATION_KEYS = {"when", "expect", "description", "id"}


def _load_one_schema(f: Path, where: str, allowed_keys: set[str]) -> tuple[dict | None, list[str]]:
    """One `{type}.yaml` file's full §4.4 shape check — shared by the
    shared-tier loader (`load_schemas`) and the domain-sense loader
    (`load_domain_schemas`, §15.4), which differ only in *allowed_keys*
    (a domain sense additionally carries `domain:`) and in what the caller
    does with the result. Returns (schema-or-None, errors); None only for a
    YAML/shape failure severe enough that the file contributes nothing
    (unparseable, non-mapping top level) — a schema with milder per-field
    defects is still returned (errors reported, narrower drops applied,
    exactly as before)."""
    errors: list[str] = []
    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as e:
        errors.append(f"{where}: invalid YAML — {e}")
        return None, errors
    if not isinstance(data, dict):
        errors.append(f"{where}: top level must be a mapping")
        return None, errors
    if data.get("type") != f.stem:
        errors.append(f"{where}: type {data.get('type')!r} != filename stem {f.stem!r}")
    unknown = set(data) - allowed_keys
    if unknown:
        errors.append(f"{where}: unknown keys {sorted(unknown)}")
    # the extension chain into the spine (§15.3): a string naming either
    # another declared type or a spine reference (`{dataset}:{id-or-label}`,
    # recognized here by its colon — structural only; resolving it against
    # the registered spine datasets, and following the chain upward across
    # the whole schema set, is `extends_chain_errors`'s job, run once all
    # schemas are loaded). Missing is frontier (§15.3), never an error here.
    extends = data.get("extends")
    if extends is not None and not (isinstance(extends, str) and extends.strip()):
        errors.append(f"{where}: extends must be a non-empty string (§15.3)")
    requires_domain = data.get("requires_domain")
    if requires_domain is not None and not isinstance(requires_domain, bool):
        errors.append(f"{where}: requires_domain must be a bool (§15.4)")
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
        fextends = fspec.get("extends")
        if fextends is not None and not (
            isinstance(fextends, str) and fextends.strip()
        ):
            errors.append(f"{where}: field {fname!r} extends must be a non-empty "
                          "string naming a spine relation (§15.3)")
        # field-attached invariants sugar (§4.4, §11): shape checked here
        # (a list of mappings) — the constraint-kind/severity/unknown-key
        # detail is `invariants.field_invariant_rules`'s job, run once all
        # schemas (shared + domain) are loaded, mirroring how `expected`
        # fields are checked here but `expectations:` selectors are
        # checked structurally below.
        finvariants = fspec.get("invariants")
        if finvariants is not None and not isinstance(finvariants, list):
            errors.append(f"{where}: field {fname!r} invariants must be a list (§4.4, §11)")
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
    return data, errors


def load_schemas(ledger_root: Path) -> tuple[dict[str, dict], list[str]]:
    """All shared-tier schemas → ({type: schema}, shape errors)."""
    out: dict[str, dict] = {}
    errors: list[str] = []
    base = ledger_root / "schemas"
    if not base.is_dir():
        return out, errors
    for f in sorted(base.glob("*.yaml")):
        schema, errs = _load_one_schema(f, f"schemas/{f.name}", SCHEMA_KEYS)
        errors.extend(errs)
        if schema is not None:
            out[f.stem] = schema
    return out, errors


def load_domain_schemas(ledger_root: Path) -> tuple[dict[str, dict[str, dict]], list[str]]:
    """Domain type senses — `schemas/{domain-id}/{type}.yaml` (§15.4): the
    same §4.4 grammar `load_schemas` checks, plus a `domain:` key that MUST
    equal the parent directory name. Returns {domain-id: {type: schema}} —
    a separate namespace from the shared tier's flat {type: schema}, since
    two domains may legitimately mint the same type name (§15.4: "the
    domain: field selects the sense"). `schemas/values/` is the value-kinds
    directory (§4.5), never a domain — excluded here by name, the same way
    `values.load_kinds` owns that subtree exclusively."""
    out: dict[str, dict[str, dict]] = {}
    errors: list[str] = []
    base = ledger_root / "schemas"
    if not base.is_dir():
        return out, errors
    for ddir in sorted(p for p in base.iterdir() if p.is_dir() and p.name != "values"):
        domain_id = ddir.name
        for f in sorted(ddir.glob("*.yaml")):
            where = f"schemas/{domain_id}/{f.name}"
            schema, errs = _load_one_schema(f, where, DOMAIN_SCHEMA_KEYS)
            errors.extend(errs)
            if schema is None:
                continue
            if schema.get("domain") != domain_id:
                errors.append(f"{where}: domain {schema.get('domain')!r} != parent "
                              f"directory {domain_id!r} (§15.4)")
            out.setdefault(domain_id, {})[f.stem] = schema
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


def spine_references(schemas: dict[str, dict]) -> set[str]:
    """Every spine-form `extends:` reference a schema set declares (§15.3) — type-
    level and field-level alike — recognized structurally by its colon (a qualified
    `{dataset}:{id-or-label}`, e.g. `cco:Artifact`, `bfo:generically dependent
    continuant`). This module stops here: resolving a reference against the
    registered spine datasets' actual terms (§15.2) is another seam's job — this
    is that seam, the set it resolves against.
    """
    refs: set[str] = set()
    for schema in schemas.values():
        if not isinstance(schema, dict):
            continue
        ext = schema.get("extends")
        if isinstance(ext, str) and ":" in ext:
            refs.add(ext)
        for fspec in (schema.get("fields") or {}).values():
            if not isinstance(fspec, dict):
                continue
            fext = fspec.get("extends")
            if isinstance(fext, str) and ":" in fext:
                refs.add(fext)
    return refs


def extends_chain_errors(schemas: dict[str, dict]) -> list[str]:
    """Type-level `extends:` chains (§15.3): following them upward MUST be
    acyclic and MUST terminate at a spine-form reference (a colon-bearing string)
    where the chain terminates at all.

    A chain that simply runs out at a declared type carrying no `extends:` of its
    own is not an error here — that intermediate type's own missing chain is
    frontier (§15.3), surfaced on the work-list, never here. Only a genuine cycle,
    or a name resolving to neither a declared type nor a spine reference, is a
    check error. A type carrying no `extends:` at all is likewise not this
    function's business — frontier, not checked here.
    """
    errors: list[str] = []
    for name, schema in sorted(schemas.items()):
        if not isinstance(schema, dict):
            continue
        ext = schema.get("extends")
        if not (isinstance(ext, str) and ext.strip()):
            continue
        chain = [name]
        current = ext
        while True:
            if ":" in current:
                break  # spine-form reference — chain terminates cleanly
            if current in chain:
                errors.append(f"schemas/{name}.yaml: extends chain is cyclic — "
                              f"{' -> '.join([*chain, current])}")
                break
            if current not in schemas:
                errors.append(f"schemas/{name}.yaml: extends {current!r} names neither "
                              "a declared type nor a spine reference (no colon, §15.3)")
                break
            chain.append(current)
            nxt = schemas[current].get("extends") if isinstance(schemas[current], dict) \
                else None
            if not (isinstance(nxt, str) and nxt.strip()):
                break  # runs out at a declared type with no chain of its own — frontier
            current = nxt
    return errors
