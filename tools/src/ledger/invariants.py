"""Invariants — declared constraints over the fact graph (§11).

An invariant is data (`invariants/{slug}.yaml`), evaluated deterministically;
a violation names the exact claims. Resolution is human and binary: amend the
invariant (validation then emits the migration worklist) or challenge a claim.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ledger.model import intervals_overlap, is_redirect, period_interval

INVARIANT_KEYS = {"id", "description", "applies_to", "constraint", "severity", "per", "set",
                  "requires", "min", "max"}
CONSTRAINTS = {"unique", "exclusive", "temporal-no-overlap", "requires", "cardinality"}
SEVERITIES = {"error", "warning"}


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


def _matches(inv: dict, fact: dict, claim: dict) -> bool:
    applies = inv.get("applies_to") or {}
    ftype = applies.get("type")
    if ftype and fact.get("type") != ftype:
        return False
    pred = applies.get("predicate")
    return not (pred and claim.get("predicate") != pred)


def _fact_matches(inv: dict, fact: dict) -> bool:
    ftype = (inv.get("applies_to") or {}).get("type")
    return not ftype or fact.get("type") == ftype


def evaluate(invariants: list[dict], facts: dict[Path, dict]) -> list[tuple[str, str]]:
    """Evaluate every invariant → [(severity, message)]."""
    findings: list[tuple[str, str]] = []
    for inv in invariants:
        sev = inv.get("severity", "error")
        name = inv.get("id", "?")
        for fact in facts.values():
            if is_redirect(fact) or not _fact_matches(inv, fact):
                continue
            claims = [c for c in fact.get("claims") or [] if isinstance(c, dict)]
            matching = [c for c in claims if _matches(inv, fact, c)]
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
