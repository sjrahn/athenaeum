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
from ledger import ontology
from ledger import values as values_mod
from ledger.model import CORPUS_REF_RE, is_edge, is_redirect, load_lineage
from ledger.schemas import expectation_selects, load_domain_schemas, load_schemas
from ledger.scope import make_resolver

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

**Two tiers** (§15.1, §15.4): **Concept types** and **Edge types** below are
the shared tier only — each row also shows its declared `extends:` chain
target (§15.3), or *(chain-frontier)* where an in-use type owes one still. A
**domain's own minted vocabulary never appears in these two tables** — it
gets its own `## Domain: {id}` section further down, qualified on display
(`vessel @ bsg-reimagined`) the same way `ledger check`/the work-list qualify
it; a domain type's definition column is its own declared `description:`
(the `ontology.types` entry), authoritative like Value kinds/Demand rules —
never hand-curated here either.
"""


def _minting_domain(ftype: str, dom: object, domains: dict[str, dict], resolve_id) -> str | None:
    """The domain (in *dom*'s resolved import closure) that mints *ftype*, or
    None when *dom* is absent/dangling or the type isn't domain-minted at
    all (§15.4's economy default) — the closure's sorted first declarer is
    deterministic; a genuine collision is `ontology.ambiguous_type_names`'s
    validation error to catch, never arbitrated here. Shared by the VOCAB
    two-tier split (`collect_vocab`) and the work-list chain-frontier
    (`render_worklist`) so both read the same domain-minted-ness."""
    if not (domains and isinstance(dom, str) and dom):
        return None
    live_dom = resolve_id(dom)
    if not live_dom:
        return None
    closure = ontology.import_closure(live_dom, domains, resolve_id)
    for did in sorted(closure):
        block = domains.get(did)
        if isinstance(block, dict) and ftype in (block.get("types") or {}):
            return did
    return None


def collect_vocab(
    facts: dict[Path, dict],
    domains: dict[str, dict] | None = None,
    resolve_id=None,
) -> tuple[dict[str, Counter], dict[str, Counter]]:
    """Usage counters per vocabulary section, computed from the fact files,
    plus a second {domain id: Counter} map of domain-MINTED type usage
    (§15.4) — a domain-minted type is carved out of the shared tier's own
    `types`/`edge-types` counters entirely (the two-tier split, §8/§15.1),
    attributed to whichever domain in the fact's import closure actually
    declares the type name (deterministic: the closure's sorted first
    declarer — real collisions are `ontology.ambiguous_type_names`'s error to
    catch, never silently arbitrated here). A fact carrying no `domain:`, or
    one whose type isn't domain-minted at all (the economy default, §15.4),
    counts in the shared tier exactly as before. *domains*/*resolve_id* are
    optional (no ontology layer yet ⇒ never any domain-minted vocabulary,
    §15.2's "an instance with no spine registered has no ontology layer
    yet" reading applies just as well to no domains registered at all)."""
    domains = domains or {}
    c: dict[str, Counter] = {name: Counter() for name, _, _ in _SECTIONS}
    domain_counts: dict[str, Counter] = {}
    for fact in facts.values():
        if is_redirect(fact):
            continue
        ftype = str(fact.get("type", "?"))
        minted_by = _minting_domain(ftype, fact.get("domain"), domains, resolve_id) \
            if resolve_id is not None else None
        if minted_by:
            domain_counts.setdefault(minted_by, Counter())[ftype] += 1
        else:
            section = "edge-types" if is_edge(fact) else "types"
            c[section][ftype] += 1
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
    return c, domain_counts


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


def _has_extends_column(block: str) -> bool:
    """Whether the section's header row carries the v39 `extends` column
    (§15.3) — False for a pre-v39 3-column file, whose definition cells sit
    one cell left. Read from the header row so the first regen after the
    upgrade carries every preserved definition across losslessly."""
    for line in block.strip().splitlines():
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] and not set(cells[0]) <= set("-: "):
            return "extends" in cells
    return True


def parse_definitions(vocab_text: str) -> dict[str, dict[str, str]]:
    """{section: {term: definition}} from an existing VOCAB.md — the
    definition column sits one cell further right in **Concept types**/
    **Edge types** (§15.3's extra `extends` column, `_CHAIN_SECTIONS`) than
    in every other section — except in a pre-v39 file (no `extends` header
    cell), where those sections are still 3-column and the parse falls back
    accordingly: the one-time upgrade regen writes the 4-column shape."""
    defs: dict[str, dict[str, str]] = {}
    for section, _, _ in _SECTIONS:
        block = _block(vocab_text, section)
        if block is None:
            continue
        idx = 3 if section in _CHAIN_SECTIONS and _has_extends_column(block) else 2
        defs[section] = {r[0]: (r[idx] if len(r) > idx else "") for r in _parse_rows(block)}
    return defs


def parse_retired(vocab_text: str) -> list[list[str]]:
    """[[term, kind, reason], …] from the Retired section."""
    block = _block(vocab_text, "retired")
    return _parse_rows(block) if block else []


_CHAIN_SECTIONS = {"types", "edge-types"}  # the two owe an extends: chain (§15.3)


def _extends_cell(term: str, schemas: dict[str, dict]) -> str:
    """The declared `extends:` target for a shared-tier type/edge type
    (§15.3), backtick-quoted like every other VOCAB cell — or the
    *(chain-frontier)* marker for an in-use type that still owes one (§8:
    "extension chains are owed"), so the gap reads here too, not only on
    the work-list (§7.4)."""
    schema = schemas.get(term)
    ext = schema.get("extends") if isinstance(schema, dict) else None
    if isinstance(ext, str) and ext.strip():
        return f"`{ext}`"
    return "*(chain-frontier)*"


def render_vocab(counters: dict[str, Counter], defs: dict[str, dict[str, str]],
                 retired: list[list[str]],
                 kind_descriptions: dict[str, str] | None = None,
                 rule_descriptions: dict[str, str] | None = None,
                 schemas: dict[str, dict] | None = None,
                 domain_counts: dict[str, Counter] | None = None,
                 domains: dict[str, dict] | None = None) -> str:
    schemas = schemas or {}
    parts = [_HEADER]
    for section, heading, label in _SECTIONS:
        start, end = (m.format(section) for m in _SECTION_MARKS)
        chained = section in _CHAIN_SECTIONS
        header = f"| {label} | count | extends | definition |" if chained \
            else f"| {label} | count | definition |"
        rule = "|---|---:|---|---|" if chained else "|---|---:|---|"
        lines = [header, rule]
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
            if chained:
                lines.append(f"| `{term}` | {n} | {_extends_cell(term, schemas)} | {d} |")
            else:
                lines.append(f"| `{term}` | {n} | {d} |")
        table = "\n".join(lines)
        parts.append(f"\n## {heading}\n\n{start}\n{table}\n{end}\n")

    # Domains (§15.4): a domain's own minted vocabulary, one section per
    # domain that has actually minted something in use, qualified display
    # throughout (`{type} @ {domain}`) — never folded into the shared-tier
    # tables above. Definitions are the type's own declared `description:`
    # (the `ontology.types` entry) — authoritative, like Value kinds/Demand
    # rules, never a hand-curated VOCAB.md cell.
    for did in sorted(domain_counts or {}):
        block = (domains or {}).get(did) or {}
        types = block.get("types") if isinstance(block, dict) else None
        types = types if isinstance(types, dict) else {}
        start, end = (m.format(f"domain-{did}") for m in _SECTION_MARKS)
        lines = ["| type | count | extends | definition |", "|---|---:|---|---|"]
        for tname, n in sorted(domain_counts[did].items()):
            tdecl = types.get(tname)
            tdecl = tdecl if isinstance(tdecl, dict) else {}
            ext = tdecl.get("extends")
            ext_cell = f"`{ext}`" if isinstance(ext, str) and ext.strip() \
                else "*(chain-frontier)*"
            d = str(tdecl.get("description") or "")
            lines.append(f"| `{tname} @ {did}` | {n} | {ext_cell} | {d} |")
        table = "\n".join(lines)
        parts.append(f"\n## Domain: {did}\n\n{start}\n{table}\n{end}\n")

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
    live = [f for f in facts.values() if not is_redirect(f)]
    edges = [f for f in live if is_edge(f)]
    facts_by_id = {str(f.get("id")): f for f in live}
    lineage = load_lineage(ledger_root)[0]
    domains = ontology.load_domains(facts_by_id)
    resolve_id = make_resolver(facts_by_id, lineage)
    counters, domain_counts = collect_vocab(facts, domains, resolve_id)
    counters["value-kinds"] = _kind_usage(kinds, schemas)
    counters["demand-rules"] = _demand_rule_usage(rules, named_exps, live, edges, facts_by_id,
                                                  lineage)
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
                        kind_descriptions, rule_descriptions,
                        schemas, domain_counts, domains)


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
    facts_by_id = {str(f.get("id")): f for f in live}
    lineage = load_lineage(ledger_root)[0]
    domains = ontology.load_domains(facts_by_id)
    domain_schemas, _ = load_domain_schemas(ledger_root)
    resolve_id = make_resolver(facts_by_id, lineage)

    # Extension chains are owed (§8, §15.3, §15.4): an in-use type — shared-
    # tier or domain-minted alike — with no declared `extends:` is frontier,
    # never an error. One line per (type[, domain]) regardless of how many
    # facts use it, mirroring the timebox-gap aggregation just below.
    chain_owed: set[str] = set()
    for fact in live:
        ftype = str(fact.get("type"))
        minted_by = _minting_domain(ftype, fact.get("domain"), domains, resolve_id)
        if minted_by:
            tdecl = (domains.get(minted_by, {}).get("types") or {}).get(ftype)
            ext = tdecl.get("extends") if isinstance(tdecl, dict) else None
            key = f"{ftype} @ {minted_by}"
        else:
            eff = ontology.effective_schema(fact, schemas, domain_schemas)
            ext = eff.get("extends") if isinstance(eff, dict) else None
            key = ftype
        if not (isinstance(ext, str) and ext.strip()):
            chain_owed.add(key)
    for key in sorted(chain_owed):
        frontier.append(f"- `{key}` has no `extends:` — extension chain owed (§15.3)")

    for fact in sorted(live, key=lambda f: str(f.get("id", ""))):
        claims = fact.get("claims") or []
        roster = fact.get("artifacts") or []
        if not is_edge(fact) and not claims and not roster:
            frontier.append(f"- stub `{fact.get('id')}` ({fact.get('type')}) — no claims, "
                            "no roster")
            continue
        schema = ontology.effective_schema(fact, schemas, domain_schemas)
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
        lines += ["", "### Frontier (stubs + schema conformance + extension chains)",
                  "", *frontier]

    rules, _ = demands_mod.load_demand_rules(ledger_root)
    kinds, _ = values_mod.load_kinds(ledger_root)
    interp_list = list(interps.values())
    by_fact: dict[str, list[str]] = {}
    for fact in sorted(live, key=lambda f: str(f.get("id", ""))):
        for d in demands_mod.evaluate_demands(
            fact, rules=rules, schemas=schemas, kinds=kinds,
            facts_by_id=facts_by_id, edges=edges, interps=interp_list,
            lineage=lineage, domain_schemas=domain_schemas, domains=domains,
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
