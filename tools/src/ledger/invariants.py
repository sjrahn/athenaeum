"""Invariants — declared constraints over the fact graph (§11).

An invariant is data (`invariants/{slug}.yaml`), evaluated deterministically;
a violation names the exact claims. Resolution is human and binary: amend the
invariant (validation then emits the migration worklist) or challenge a claim.

`applies_to` gains the §15.5 condition-grammar growth: `type:` may carry
`{isa: <operand>}` (subsumption over declared `extends:` chains, §15.5) in
place of a bare string, and `applies_to` may additionally carry `domain:`
(the fact-domain axis, equals/in, lineage-resolved as `id:` operands are).
Field-attached `invariants:` sugar (§4.4/§11) — a schema field carrying a
list of the same constraint-kind mappings, `applies_to` implied by the
declaring type + field — is absorbed by `field_invariant_rules`, run once at
load and merged into the ordinary rule list before `evaluate`.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from ledger import ontology
from ledger.model import intervals_overlap, is_redirect, period_interval
from ledger.scope import make_resolver

if TYPE_CHECKING:
    from ath.manifest import Reference

INVARIANT_KEYS = {"id", "description", "applies_to", "constraint", "severity", "per", "set",
                  "requires", "min", "max"}
CONSTRAINTS = {"unique", "exclusive", "temporal-no-overlap", "requires", "cardinality"}
SEVERITIES = {"error", "warning"}
# Field-attached sugar (§4.4/§11) carries the same per-invariant keys minus
# `id`/`applies_to` — both are implied by the declaring type + field.
FIELD_INVARIANT_KEYS = INVARIANT_KEYS - {"id", "applies_to"}


def load_invariants(ledger_root: Path) -> tuple[list[dict], list[str]]:
    out: list[dict] = []
    errors: list[str] = []
    base = ledger_root / "invariants"
    if not base.is_dir():
        return out, errors
    for f in sorted(base.glob("*.yaml")):
        where = f"invariants/{f.name}"
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
        unknown = set(data) - INVARIANT_KEYS
        if unknown:
            errors.append(f"{where}: unknown keys {sorted(unknown)}")
        if data.get("constraint") not in CONSTRAINTS:
            errors.append(f"{where}: constraint must be one of {sorted(CONSTRAINTS)}")
            continue
        if data.get("severity", "error") not in SEVERITIES:
            errors.append(f"{where}: severity must be error|warning")
        if not isinstance(data.get("applies_to") or {}, dict):
            errors.append(f"{where}: applies_to must be a mapping")
            continue
        data.setdefault("_where", where)
        out.append(data)
    return out, errors


def field_invariant_rules(
    schemas: dict[str, dict], domain_schemas: dict[str, dict[str, dict]] | None = None,
) -> tuple[list[dict], list[str]]:
    """Field-attached `invariants:` sugar (§4.4, §11): a schema field MAY
    carry a list of the same constraint-kind mappings `invariants/*.yaml`
    uses, minus `id`/`applies_to` — both implied by the declaring type and
    field. Domain-sense schema fields (`schemas/{domain}/{type}.yaml`,
    §15.4) get the same treatment. Returns (synthesized rules, shape
    errors) — rules carry a display id `field:{type}.{field}[{i}]` and an
    implied `applies_to: {type, predicate: field}`, ready to merge straight
    into the ordinary `invariants/*.yaml` rule list `evaluate` reads; shape
    errors follow `load_invariants`'s own idiom (unknown keys, a bad
    constraint/severity name), reported against the owning schema file."""
    rules: list[dict] = []
    errors: list[str] = []

    def scan(ftype: str, schema: dict, where: str) -> None:
        for fname, fspec in (schema.get("fields") or {}).items():
            if not isinstance(fspec, dict):
                continue
            field_invs = fspec.get("invariants")
            if field_invs is None:
                continue
            if not isinstance(field_invs, list):
                continue  # already flagged at schema load (`schemas._load_one_schema`)
            for i, inv in enumerate(field_invs):
                iwhere = f"{where}: field {fname!r} invariants[{i}]"
                if not isinstance(inv, dict):
                    errors.append(f"{iwhere} must be a mapping")
                    continue
                bad = set(inv) - FIELD_INVARIANT_KEYS
                if bad:
                    errors.append(f"{iwhere} unknown keys {sorted(bad)}")
                if inv.get("constraint") not in CONSTRAINTS:
                    errors.append(f"{iwhere} constraint must be one of {sorted(CONSTRAINTS)}")
                    continue
                if inv.get("severity", "error") not in SEVERITIES:
                    errors.append(f"{iwhere} severity must be error|warning")
                rule = {k: v for k, v in inv.items() if k in FIELD_INVARIANT_KEYS}
                rule["id"] = f"field:{ftype}.{fname}[{i}]"
                rule["applies_to"] = {"type": ftype, "predicate": fname}
                rule["_where"] = iwhere
                rules.append(rule)

    for ftype, schema in schemas.items():
        if isinstance(schema, dict):
            scan(ftype, schema, f"schemas/{ftype}.yaml")
    for did, types in (domain_schemas or {}).items():
        for ftype, schema in types.items():
            if isinstance(schema, dict):
                scan(ftype, schema, f"schemas/{did}/{ftype}.yaml")
    return rules, errors


def _type_sel_matches(spec: object, fact: dict, ctx: dict) -> bool:
    """`applies_to.type` (§11, §15.5): a bare string is exact equality
    (unchanged); `{isa: <operand>}` is the §15.5 subsumption test over
    declared `extends:` chains — `ontology.isa_matches`, given the run's
    shared schema/domain/spine context. Anything else never matches
    (well-formedness of `applies_to` isn't this module's job to enforce)."""
    if spec is None:
        return True
    if isinstance(spec, str):
        return fact.get("type") == spec
    if isinstance(spec, dict) and set(spec) == {"isa"} and isinstance(spec["isa"], str):
        return ontology.isa_matches(
            fact, spec["isa"], schemas=ctx["schemas"], domains=ctx["domains"],
            resolve_id=ctx["resolve_id"], references=ctx["references"],
            corpora_roots=ctx["corpora_roots"],
        )
    return False


def _domain_sel_matches(spec: object, fact: dict, lineage: dict[str, str]) -> bool:
    """`applies_to.domain` (§15.5): the fact-domain axis, `equals`/`in`
    lineage-resolved exactly as an `id:` operand is."""
    if spec is None:
        return True
    values = ontology.domain_axis_values(fact, lineage)
    resolved = ontology.resolve_domain_operand(spec, lineage)
    from ledger.scope import op_matches

    if isinstance(resolved, dict) and len(resolved) == 1:
        (op, arg), = resolved.items()
        try:
            return op_matches(op, arg, values)
        except ValueError:
            return False
    return op_matches("equals", resolved, values)


def _fact_matches(inv: dict, fact: dict, ctx: dict) -> bool:
    applies = inv.get("applies_to") or {}
    if not _type_sel_matches(applies.get("type"), fact, ctx):
        return False
    return _domain_sel_matches(applies.get("domain"), fact, ctx["lineage"])


def _matches(inv: dict, fact: dict, claim: dict, ctx: dict) -> bool:
    if not _fact_matches(inv, fact, ctx):
        return False
    pred = (inv.get("applies_to") or {}).get("predicate")
    return not (pred and claim.get("predicate") != pred)


def evaluate(
    invariants: list[dict],
    facts: dict[Path, dict],
    *,
    lineage: dict[str, str] | None = None,
    schemas: dict[str, dict] | None = None,
    domains: dict[str, dict] | None = None,
    references: Sequence[Reference] = (),
    corpora_roots: Sequence[Path] = (),
) -> list[tuple[str, str]]:
    """Evaluate every invariant → [(severity, message)].

    *lineage*/*schemas*/*domains*/*references*/*corpora_roots* feed
    `applies_to`'s §15.5 `domain:`/`isa:` axes (all optional — an invariant
    set using neither axis runs exactly as before); *resolve_id* is built
    once here from *facts* + *lineage*, the same lineage-and-liveness
    resolver every other engine shares (`scope.make_resolver`)."""
    lineage = lineage or {}
    live = {o.get("id"): o for o in facts.values()
            if isinstance(o.get("id"), str) and not is_redirect(o)}
    ctx = {
        "lineage": lineage, "schemas": schemas or {}, "domains": domains or {},
        "resolve_id": make_resolver(live, lineage), "references": references,
        "corpora_roots": corpora_roots,
    }
    findings: list[tuple[str, str]] = []
    for inv in invariants:
        sev = inv.get("severity", "error")
        name = inv.get("id", "?")
        for fact in facts.values():
            if is_redirect(fact) or not _fact_matches(inv, fact, ctx):
                continue
            claims = [c for c in fact.get("claims") or [] if isinstance(c, dict)]
            matching = [c for c in claims if _matches(inv, fact, c, ctx)]
            kind = inv["constraint"]
            if kind == "unique":
                groups: dict[object, list[str]] = {}
                per = inv.get("per")
                for c in matching:
                    key = (c.get("qualifiers") or {}).get(per) if per else None
                    groups.setdefault(_hashable(key), []).append(str(c.get("id")))
                for key, ids in groups.items():
                    if len(ids) > 1:
                        scope = f" (per {per}={key!r})" if per else ""
                        findings.append(
                            (sev, f"invariant {name}: {len(ids)} matching claims on "
                                  f"{fact.get('id')!r}{scope} — {', '.join(ids)}")
                        )
            elif kind == "exclusive":
                held = [
                    str(c.get("id"))
                    for c in claims
                    for member in inv.get("set") or []
                    if isinstance(member, dict)
                    and c.get("predicate") == member.get("predicate")
                    and ("value" not in member or c.get("value") == member.get("value"))
                ]
                if len(held) > 1:
                    findings.append(
                        (sev, f"invariant {name}: {fact.get('id')!r} holds "
                              f"{len(held)} of an exclusive set — {', '.join(held)}")
                    )
            elif kind == "temporal-no-overlap":
                spans = [
                    (period_interval(c["period"]), str(c.get("id")))
                    for c in matching
                    if c.get("period") is not None
                ]
                spans = [(iv, cid) for iv, cid in spans if iv is not None]
                for i, (a, aid) in enumerate(spans):
                    for b, bid in spans[i + 1:]:
                        if intervals_overlap(a, b):
                            findings.append(
                                (sev, f"invariant {name}: overlapping periods on "
                                      f"{fact.get('id')!r} — {aid} vs {bid}")
                            )
            elif kind == "requires":
                required = (inv.get("requires") or {}).get("predicate")
                if matching and required and not any(
                    c.get("predicate") == required for c in claims
                ):
                    findings.append(
                        (sev, f"invariant {name}: {fact.get('id')!r} matches but carries no "
                              f"{required!r} claim")
                    )
            elif kind == "cardinality":
                n = len(matching)
                lo, hi = inv.get("min"), inv.get("max")
                if (lo is not None and n < int(lo)) or (hi is not None and n > int(hi)):
                    findings.append(
                        (sev, f"invariant {name}: {fact.get('id')!r} has {n} matching claims "
                              f"(bounds {lo}..{hi})")
                    )
    return findings


def _hashable(value: object) -> object:
    if isinstance(value, list | dict):
        import json

        return json.dumps(value, sort_keys=True)
    return value
