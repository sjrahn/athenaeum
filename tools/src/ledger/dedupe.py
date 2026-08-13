"""The coalescence proposer — `ath ledger dedupe` (#177, spec/ledger.md §8
vocabulary reuse-before-mint + §4.1 merges).

A pure report: it PROPOSES candidate duplicates and dead schema surface, it
never merges facts, redirects ids, or edits vocabulary — that stays a human
(or `ledger-scribe`) decision. Three sweeps:

- `concepts`: candidate duplicate concept/edge groups, by name/alias
  collision, id-containment (one id a token-subset of another, same type),
  or a shared external-id claim (VIN, account number, ...).
- `predicates`: near-duplicate claim predicates — one a token-subset of the
  other, or a one-token add/drop/substitution — with their usage counts, so
  a human can judge which (if either) should retire.
- `schemas`: per-schema field/roster-role usage against the fact population,
  to surface dead declared surface, plus a census of fact types carrying no
  schema at all.

Reuses `ledger.index` for id/name/alias resolution structures — it does not
re-implement normalization.
"""

from __future__ import annotations

import itertools
from collections import Counter
from pathlib import Path

import yaml

from ledger import index as index_mod
from ledger.model import is_redirect, load_json_dir

_PRED_ID_SUFFIXES = ("-id", "_id")


def propose(ledger_root: Path) -> dict:
    idx = index_mod.load_or_build(ledger_root)
    entries: dict[str, dict] = idx.get("entries") or {}
    names: dict[str, list[str]] = idx.get("names") or {}

    facts, fact_errors = load_json_dir(ledger_root, "facts/*/*.json")
    skipped: list[str] = list(fact_errors)

    fact_count_by_type: Counter[str] = Counter()
    predicate_counts: Counter[str] = Counter()
    field_usage: dict[str, Counter[str]] = {}
    role_usage: dict[str, Counter[str]] = {}
    external_id_groups: dict[tuple[str, str], list[str]] = {}

    for path, fact in facts.items():
        if is_redirect(fact):
            continue
        fid = fact.get("id")
        if not isinstance(fid, str) or not fid:
            skipped.append(f"{path.relative_to(ledger_root)}: missing id")
            continue
        ftype = path.parent.name
        fact_count_by_type[ftype] += 1

        for art in fact.get("artifacts") or []:
            if not isinstance(art, dict):
                continue
            role = art.get("role")
            if isinstance(role, str) and role:
                role_usage.setdefault(ftype, Counter())[role] += 1

        for c in fact.get("claims") or []:
            if not isinstance(c, dict):
                continue
            pred = c.get("predicate")
            if not isinstance(pred, str) or not pred:
                continue
            predicate_counts[pred] += 1
            field_usage.setdefault(ftype, Counter())[pred] += 1

            if pred.endswith(_PRED_ID_SUFFIXES):
                val = c.get("value")
                if val in (None, ""):
                    val = c.get("object")
                if val in (None, ""):
                    continue
                key = (pred, index_mod.normalize_text(val))
                bucket = external_id_groups.setdefault(key, [])
                if fid not in bucket:
                    bucket.append(fid)

    concepts = _propose_concepts(entries, names, external_id_groups)
    predicates = _propose_predicates(predicate_counts)
    schemas, schema_skip = _propose_schemas(
        ledger_root, fact_count_by_type, field_usage, role_usage
    )
    skipped.extend(schema_skip)

    return {"concepts": concepts, "predicates": predicates, "schemas": schemas,
            "skipped": skipped}


# ----------------------------------------------------------------- concepts


def _propose_concepts(
    entries: dict[str, dict],
    names: dict[str, list[str]],
    external_id_groups: dict[tuple[str, str], list[str]],
) -> list[dict]:
    def coalescible(eid: str) -> bool:
        return entries.get(eid, {}).get("kind") in ("concept", "edge")

    found: list[dict] = []

    name_pairs: set[frozenset[str]] = set()
    for key in sorted(names):
        ids = sorted({i for i in names[key] if coalescible(i)})
        if len(ids) >= 2:
            found.append({"basis": "name-collision", "key": key, "ids": ids})
            for a, b in itertools.combinations(ids, 2):
                name_pairs.add(frozenset((a, b)))

    by_type: dict[str, list[tuple[str, frozenset[str]]]] = {}
    for eid, e in entries.items():
        if e.get("kind") not in ("concept", "edge"):
            continue
        by_type.setdefault(e.get("type", ""), []).append(
            (eid, frozenset(index_mod.tokenize(eid)))
        )
    for ftype in sorted(by_type):
        items = sorted(by_type[ftype])
        for (id_a, tok_a), (id_b, tok_b) in itertools.combinations(items, 2):
            if tok_a < tok_b:
                shorter, longer = id_a, id_b
            elif tok_b < tok_a:
                shorter, longer = id_b, id_a
            else:
                continue
            if frozenset((shorter, longer)) in name_pairs:
                continue
            found.append({"basis": "id-containment", "ids": [shorter, longer],
                          "type": ftype})

    for (pred, norm_val), ids in sorted(external_id_groups.items()):
        if len(ids) >= 2:
            found.append({"basis": "shared-external-id", "key": f"{pred}={norm_val}",
                          "ids": sorted(ids)})

    return found


# --------------------------------------------------------------- predicates


def _predicate_basis(tok_a: frozenset[str], tok_b: frozenset[str]) -> str | None:
    if tok_a < tok_b or tok_b < tok_a:
        return "token-subset"
    sym_diff = tok_a ^ tok_b
    if len(sym_diff) == 1:
        return "one-token-diff"
    # Substitution: |A|==|B| and |A∩B|==|A|-1 — but for singleton token sets
    # this degenerates to "any two distinct one-word predicates" (intersection
    # of two different singletons is always 0 == 1-1), which is not a
    # duplicate signal at all. Require at least 2 tokens a side so this only
    # fires on the intended case (one substituted word within a multi-word
    # predicate, e.g. shares_service_information_with / ..._manual_with).
    if len(tok_a) >= 2 and len(tok_a) == len(tok_b) and len(tok_a & tok_b) == len(tok_a) - 1:
        return "one-token-diff"
    return None


def _propose_predicates(predicate_counts: Counter[str]) -> list[dict]:
    found: list[dict] = []
    preds = sorted(predicate_counts)
    tokens = {p: frozenset(index_mod.tokenize(p)) for p in preds}
    for a, b in itertools.combinations(preds, 2):
        basis = _predicate_basis(tokens[a], tokens[b])
        if basis is None:
            continue
        # token-subset: report subset predicate as `a`, superset as `b`.
        if basis == "token-subset" and not tokens[a] < tokens[b]:
            a, b = b, a
        found.append({
            "a": a, "b": b, "count_a": predicate_counts[a], "count_b": predicate_counts[b],
            "basis": basis,
        })
    found.sort(key=lambda p: (p["a"], p["b"]))
    return found


# ------------------------------------------------------------------ schemas


def _load_schema_files(ledger_root: Path) -> tuple[dict[str, dict], list[str]]:
    """Tolerant load of `schemas/*.yaml` — parse failures only, no shape
    validation (that is `ledger.schemas.load_schemas`'s job at check-time)."""
    out: dict[str, dict] = {}
    skipped: list[str] = []
    base = ledger_root / "schemas"
    if not base.is_dir():
        return out, skipped
    for f in sorted(base.glob("*.yaml")):
        where = f"schemas/{f.name}"
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError) as e:
            skipped.append(f"{where}: invalid YAML — {e}")
            continue
        if not isinstance(data, dict):
            skipped.append(f"{where}: top level must be a mapping")
            continue
        out[f.stem] = data
    return out, skipped


def _propose_schemas(
    ledger_root: Path,
    fact_count_by_type: Counter[str],
    field_usage: dict[str, Counter[str]],
    role_usage: dict[str, Counter[str]],
) -> tuple[dict, list[str]]:
    schema_files, skipped = _load_schema_files(ledger_root)

    reports: list[dict] = []
    for t in sorted(schema_files):
        data = schema_files[t]
        raw_fields = data.get("fields")
        field_names = sorted(raw_fields) if isinstance(raw_fields, dict) else []
        raw_roles = data.get("roster_roles")
        roles = sorted(raw_roles) if isinstance(raw_roles, list) else []
        raw_expect = data.get("expectations")

        fcounts = field_usage.get(t, Counter())
        rcounts = role_usage.get(t, Counter())
        fields_report = {name: fcounts.get(name, 0) for name in field_names}
        roles_report = {role: rcounts.get(role, 0) for role in roles}

        reports.append({
            "type": t,
            "fact_count": fact_count_by_type.get(t, 0),
            "fields": fields_report,
            "unused_fields": sorted(n for n, c in fields_report.items() if c == 0),
            "roster_roles": roles_report,
            "unused_roles": sorted(r for r, c in roles_report.items() if c == 0),
            "all_fields_unused": bool(fields_report) and all(
                c == 0 for c in fields_report.values()
            ),
            "expectations": len(raw_expect) if isinstance(raw_expect, list) else 0,
        })

    schemaless = sorted(
        ({"type": t, "fact_count": n} for t, n in fact_count_by_type.items()
         if t not in schema_files),
        key=lambda s: (-s["fact_count"], s["type"]),
    )

    return {"reports": reports, "schemaless_types": schemaless}, skipped
