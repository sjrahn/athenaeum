"""Generated views — `facts/VOCAB.md` and the open-questions work-list block (§7.4, §8).

VOCAB.md is regenerated wholesale: rows and counts are computed from the
facts; the definition column and the Retired section are the file's only
hand-curated content, parsed out and preserved across regenerations (a new
term lands as a visible diff — an empty definition cell to fill). The
open-questions block regenerates between its markers; curated items outside
survive untouched.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ledger import demands as demands_mod
from ledger import values as values_mod
from ledger.model import CORPUS_REF_RE, is_edge, is_redirect, load_lineage
from ledger.schemas import expectation_selects, load_schemas

VOCAB_PATH = "facts/VOCAB.md"
OPENQ_PATH = "open-questions.md"
OPENQ_MARKS = ("<!--worklist:begin-->", "<!--worklist:end-->")
_SECTION_MARKS = ("<!-- vocab:{}:start -->", "<!-- vocab:{}:end -->")

# (section slug, heading, term-column label)
_SECTIONS = (
    ("types", "Concept types", "type"),
    ("edge-types", "Edge types", "type"),
    ("predicates", "Claim predicates", "predicate"),
    ("qualifiers", "Qualifier keys", "qualifier"),
    ("roster-roles", "Roster roles", "role"),
    ("roster-modality", "Roster modality", "modality"),
    ("roster-derivation", "Roster derivation", "derivation"),
    ("value-kinds", "Value kinds", "kind"),
    ("demand-rules", "Demand rules", "rule"),
)

_HEADER = """\
# Vocabulary registry — GENERATED

Every concept type, edge type, claim predicate, qualifier key, roster role,
value kind (§4.5), and demand rule (§14) in use, with counts (`spec/ledger.md`
§8). Rows and counts are computed by `ath ledger regen`; the **definition
column** and the **Retired** section are this file's only hand-curated
content and are preserved across regenerations — except **Value kinds** and
**Demand rules**, whose description columns are the kind's/rule's own
declared `description:` (§4.5, §14), never hand-curated here. Reuse before
minting — a new term lands here as a visible diff. Using a retired term is a
validation error.
"""


def collect_vocab(facts: dict[Path, dict]) -> dict[str, Counter]:
    """Usage counters per vocabulary section, computed from the fact files."""
    c: dict[str, Counter] = {name: Counter() for name, _, _ in _SECTIONS}
    for fact in facts.values():
        if is_redirect(fact):
            continue
        section = "edge-types" if is_edge(fact) else "types"
        c[section][str(fact.get("type", "?"))] += 1
        for entry in fact.get("artifacts") or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("role"):
                c["roster-roles"][str(entry["role"])] += 1
            if entry.get("modality"):
                c["roster-modality"][str(entry["modality"])] += 1
            if entry.get("derivation"):
                c["roster-derivation"][str(entry["derivation"])] += 1
        for claim in fact.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            c["predicates"][str(claim.get("predicate", "?"))] += 1
            for qk in claim.get("qualifiers") or {}:
                c["qualifiers"][str(qk)] += 1
    return c


def _kind_usage(kinds: dict[str, dict], schemas: dict[str, dict]) -> Counter:
    """Value kind usage counts (§4.5): every declared kind starts at 0 —
    listed for adoption visibility even unused — incremented once per schema
    field or element `value:` reference."""
    c: Counter = Counter({k: 0 for k in kinds})
    for schema in schemas.values():
        if not isinstance(schema, dict):
            continue
        for fspec in (schema.get("fields") or {}).values():
            if not isinstance(fspec, dict):
                continue
            if isinstance(fspec.get("value"), str):
                c[fspec["value"]] += 1
            for edecl in (fspec.get("elements") or {}).values():
                if isinstance(edecl, dict) and isinstance(edecl.get("value"), str):
                    c[edecl["value"]] += 1
    return c


def _demand_rule_usage(rules: dict[str, dict], named_exps: dict[str, tuple[str, dict]],
                       live: list[dict], edges: list[dict],
                       facts_by_id: dict[str, dict],
                       lineage: dict[str, str] | None = None) -> Counter:
    """Rule/named-expectation id → count of facts currently matched (§14),
    regardless of demand state — every declared rule and named expectation
    starts at 0, listed for visibility even unused, mirroring `_kind_usage`."""
    c: Counter = Counter({rid: 0 for rid in rules} | {eid: 0 for eid in named_exps})
    for fact in live:
        for rid, rule in rules.items():
            when = rule.get("when")
            if isinstance(when, dict) and demands_mod.condition_matches(
                when, fact, edges, facts_by_id, lineage=lineage
            ):
                c[rid] += 1
        for eid, (_ftype, exp) in named_exps.items():
            if expectation_selects(exp, fact, edges, facts_by_id, lineage):
                c[eid] += 1
    return c


def _block(text: str, section: str) -> str | None:
    start, end = (m.format(section) for m in _SECTION_MARKS)
    if start in text and end in text:
        return text.split(start, 1)[1].split(end, 1)[0]
    return None


def _parse_rows(block: str) -> list[list[str]]:
    rows = []
    for line in block.strip().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] and not set(cells[0]) <= set("-: ") and (
            cells[0].strip("`") not in ("type", "predicate", "qualifier", "role", "kind",
                                        "modality", "derivation", "rule", "term")
        ):
            rows.append([c.strip("`") for c in cells])
    return rows


def parse_definitions(vocab_text: str) -> dict[str, dict[str, str]]:
    """{section: {term: definition}} from an existing VOCAB.md."""
    defs: dict[str, dict[str, str]] = {}
    for section, _, _ in _SECTIONS:
        block = _block(vocab_text, section)
        if block is None:
            continue
        defs[section] = {r[0]: (r[2] if len(r) > 2 else "") for r in _parse_rows(block)}
    return defs


def parse_retired(vocab_text: str) -> list[list[str]]:
    """[[term, kind, reason], …] from the Retired section."""
    block = _block(vocab_text, "retired")
    return _parse_rows(block) if block else []


def render_vocab(counters: dict[str, Counter], defs: dict[str, dict[str, str]],
                 retired: list[list[str]],
                 kind_descriptions: dict[str, str] | None = None,
                 rule_descriptions: dict[str, str] | None = None) -> str:
    parts = [_HEADER]
    for section, heading, label in _SECTIONS:
        start, end = (m.format(section) for m in _SECTION_MARKS)
        lines = [f"| {label} | count | definition |", "|---|---:|---|"]
        for term, n in sorted(counters.get(section, Counter()).items()):
            # value kinds and demand rules carry their own `description:`
            # (§4.5, §14) — authoritative, never a hand-curated VOCAB.md cell
            # like every other section's.
            if section == "value-kinds":
                d = (kind_descriptions or {}).get(term, "")
            elif section == "demand-rules":
                d = (rule_descriptions or {}).get(term, "")
            else:
                d = defs.get(section, {}).get(term, "")
            lines.append(f"| `{term}` | {n} | {d} |")
        table = "\n".join(lines)
        parts.append(f"\n## {heading}\n\n{start}\n{table}\n{end}\n")
    start, end = (m.format("retired") for m in _SECTION_MARKS)
    lines = ["| term | kind | reason |", "|---|---|---|"]
    for row in retired:
        padded = [*row, "", "", ""][:3]
        lines.append(f"| `{padded[0]}` | {padded[1]} | {padded[2]} |")
    parts.append(f"\n## Retired\n\n{start}\n" + "\n".join(lines) + f"\n{end}\n")
    return "".join(parts)


def fresh_vocab(ledger_root: Path, facts: dict[Path, dict]) -> str:
    """The regenerated VOCAB.md text (definitions/retired preserved from disk)."""
    path = ledger_root / VOCAB_PATH
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    schemas, _ = load_schemas(ledger_root)
    kinds, _ = values_mod.load_kinds(ledger_root)
    rules, _ = demands_mod.load_demand_rules(ledger_root)
    named_exps = demands_mod.named_expectations(schemas)
    counters = collect_vocab(facts)
    counters["value-kinds"] = _kind_usage(kinds, schemas)
    live = [f for f in facts.values() if not is_redirect(f)]
    edges = [f for f in live if is_edge(f)]
    facts_by_id = {str(f.get("id")): f for f in live}
    counters["demand-rules"] = _demand_rule_usage(rules, named_exps, live, edges, facts_by_id,
                                                  load_lineage(ledger_root)[0])
    kind_descriptions = {k: str(v.get("description") or "") for k, v in kinds.items()
                         if isinstance(v, dict)}
    rule_descriptions = {rid: str(r.get("description") or "") for rid, r in rules.items()
                         if isinstance(r, dict)}
    # named expectations share the demand-rules section (§13.1) — marked in
    # their definition cell since their `id:` lives in a schema, not demands/
    for eid, (_ftype, exp) in named_exps.items():
        desc = str(exp.get("description") or demands_mod.when_label(exp.get("when")))
        rule_descriptions[eid] = f"{desc} (schema expectation)"
    return render_vocab(counters, parse_definitions(old), parse_retired(old),
                        kind_descriptions, rule_descriptions)


def retired_terms(ledger_root: Path) -> set[str]:
    path = ledger_root / VOCAB_PATH
    if not path.is_file():
        return set()
    return {row[0] for row in parse_retired(path.read_text(encoding="utf-8"))}


# ---------------------------------------------------------------- open questions


def render_worklist(ledger_root: Path, facts: dict[Path, dict], interps: dict[Path, dict],
                    schemas: dict[str, dict]) -> str:
    """The generated open-questions block: live interpretations, the schema-
    conformance frontier, and open/blocked demands (§7.4, §14) — all fed by
    the one demand engine so this block and the interactive surface
    (`ath ledger demands`) never disagree."""
    lines: list[str] = []
    order = {"hypothesis": 0, "correction": 1, "assessment": 2}
    live = [o for o in interps.values() if o.get("status") in ("open", "standing")]
    live.sort(key=lambda o: (order.get(str(o.get("kind")), 9), str(o.get("id", ""))))
    for o in live:
        conf = f" ({o['confidence']})" if o.get("confidence") else ""
        lines.append(f"- **{o.get('kind')}**{conf} `{o.get('id')}` — {o.get('statement')}")
        for n in o.get("needs") or []:
            if not isinstance(n, dict):
                continue
            m = CORPUS_REF_RE.search(str(n.get("record", "")))
            rec = f" `{m.group(1)[:12]}…`" if m else ""
            lines.append(f"  - ({n.get('action')}){rec} {n.get('why')}")
    if not lines:
        lines = ["*(no open interpretations)*"]

    frontier: list[str] = []
    timebox_gaps: dict[tuple[str, str], list[str]] = {}
    live = [f for f in facts.values() if not is_redirect(f)]
    edges = [f for f in live if is_edge(f)]
    for fact in sorted(live, key=lambda f: str(f.get("id", ""))):
        claims = fact.get("claims") or []
        roster = fact.get("artifacts") or []
        if not is_edge(fact) and not claims and not roster:
            frontier.append(f"- stub `{fact.get('id')}` ({fact.get('type')}) — no claims, "
                            "no roster")
            continue
        schema = schemas.get(str(fact.get("type")))
        if not schema:
            continue
        # `expected: true` fields and `expectations:` gaps are the demand
        # engine's job (§14) — the Demands section below is their one
        # source now, so they're not re-listed here (avoids double-listing
        # every open item, once per section).
        #
        # `timeboxed: true` fields owe every claim a `period` — an attested
        # residence/employment episode without a timespan is half a fact;
        # the gap is a chase (frontier), never an error (§4.4). The demand
        # engine doesn't emit this one, so it stays here.
        timeboxed = {name for name, spec in (schema.get("fields") or {}).items()
                     if isinstance(spec, dict) and spec.get("timeboxed")}
        for c in claims:
            if (isinstance(c, dict) and str(c.get("predicate")) in timeboxed
                    and not c.get("period")):
                timebox_gaps.setdefault(
                    (str(fact.get("type")), str(c.get("predicate"))), [],
                ).append(str(c.get("id") or fact.get("id")))
    for (t, fieldname), cids in sorted(timebox_gaps.items()):
        if len(cids) <= 5:
            frontier.append(f"- `{t}.{fieldname}` claims missing their timebox "
                            f"(`period`): " + ", ".join(f"`{i}`" for i in cids))
        else:
            sample = ", ".join(f"`{i}`" for i in cids[:3])
            frontier.append(f"- `{t}.{fieldname}` claims missing their timebox "
                            f"(`period`) on {len(cids)} claims ({sample}, …)")
    if frontier:
        lines += ["", "### Frontier (stubs + schema conformance)", "", *frontier]

    rules, _ = demands_mod.load_demand_rules(ledger_root)
    kinds, _ = values_mod.load_kinds(ledger_root)
    facts_by_id = {str(f.get("id")): f for f in live}
    lineage = load_lineage(ledger_root)[0]
    interp_list = list(interps.values())
    by_fact: dict[str, list[str]] = {}
    for fact in sorted(live, key=lambda f: str(f.get("id", ""))):
        for d in demands_mod.evaluate_demands(
            fact, rules=rules, schemas=schemas, kinds=kinds,
            facts_by_id=facts_by_id, edges=edges, interps=interp_list,
            lineage=lineage,
        ):
            if d["state"] == "satisfied":
                continue
            rule_tag = f"({d['rule']})"
            if d["state"] == "open":
                why = f" — {d['why']}" if d["why"] else ""
                line = f"  - owes `{d['field']}` {rule_tag}{why}"
            else:  # blocked
                need = d.get("need") or {}
                line = (f"  - owes `{d['field']}` {rule_tag} — blocked on "
                        f"{need.get('action', '?')}: {need.get('why', '')}")
            shape_label = demands_mod.format_shape(d.get("shape") or {})
            if shape_label:
                line += f" [{shape_label}]"
            by_fact.setdefault(d["fact"], []).append(line)
    if by_fact:
        demand_lines: list[str] = []
        for fid in sorted(by_fact):
            demand_lines.append(f"- `{fid}`")
            demand_lines.extend(by_fact[fid])
        lines += ["", "### Demands (§14)", "", *demand_lines]
    return "\n".join(lines)


def fresh_openq(ledger_root: Path, facts: dict[Path, dict], interps: dict[Path, dict],
                schemas: dict[str, dict]) -> str | None:
    """The full regenerated open-questions.md, or None when markers are absent."""
    path = ledger_root / OPENQ_PATH
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    start, end = OPENQ_MARKS
    if start not in text or end not in text:
        return None
    block = render_worklist(ledger_root, facts, interps, schemas)
    pre, rest = text.split(start, 1)
    _, post = rest.split(end, 1)
    return f"{pre}{start}\n{block}\n{end}{post}"
