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

from ledger.model import CORPUS_REF_RE, is_edge, is_redirect

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
)

_HEADER = """\
# Vocabulary registry — GENERATED

Every concept type, edge type, claim predicate, qualifier key, and roster
role in use, with counts (`spec/ledger.md` §8). Rows and counts are computed
by `ath ledger regen`; the **definition column** and the **Retired** section
are this file's only hand-curated content and are preserved across
regenerations. Reuse before minting — a new term lands here as a visible
diff. Using a retired term is a validation error.
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
            if isinstance(entry, dict) and entry.get("role"):
                c["roster-roles"][str(entry["role"])] += 1
        for claim in fact.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            c["predicates"][str(claim.get("predicate", "?"))] += 1
            for qk in claim.get("qualifiers") or {}:
                c["qualifiers"][str(qk)] += 1
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
            cells[0].strip("`") not in ("type", "predicate", "qualifier", "role", "term")
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
                 retired: list[list[str]]) -> str:
    parts = [_HEADER]
    for section, heading, label in _SECTIONS:
        start, end = (m.format(section) for m in _SECTION_MARKS)
        lines = [f"| {label} | count | definition |", "|---|---:|---|"]
        for term, n in sorted(counters.get(section, Counter()).items()):
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
    return render_vocab(collect_vocab(facts), parse_definitions(old), parse_retired(old))


def retired_terms(ledger_root: Path) -> set[str]:
    path = ledger_root / VOCAB_PATH
    if not path.is_file():
        return set()
    return {row[0] for row in parse_retired(path.read_text(encoding="utf-8"))}


# ---------------------------------------------------------------- open questions


def render_worklist(facts: dict[Path, dict], interps: dict[Path, dict],
                    schemas: dict[str, dict]) -> str:
    """The generated open-questions block: live interpretations + the frontier."""
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
    for fact in sorted(facts.values(), key=lambda f: str(f.get("id", ""))):
        if is_redirect(fact) or is_edge(fact):
            continue
        claims = fact.get("claims") or []
        roster = fact.get("artifacts") or []
        if not claims and not roster:
            frontier.append(f"- stub `{fact.get('id')}` ({fact.get('type')}) — no claims, "
                            "no roster")
            continue
        schema = schemas.get(str(fact.get("type")))
        if schema:
            declared = set((schema.get("fields") or {}).keys())
            carried = {str(c.get("predicate")) for c in claims if isinstance(c, dict)}
            missing = sorted(declared - carried)
            if missing:
                frontier.append(f"- `{fact.get('id')}` ({fact.get('type')}) — schema fields "
                                f"not yet attested: {', '.join(missing)}")
    if frontier:
        lines += ["", "### Frontier (stubs + schema conformance)", "", *frontier]
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
    block = render_worklist(facts, interps, schemas)
    pre, rest = text.split(start, 1)
    _, post = rest.split(end, 1)
    return f"{pre}{start}\n{block}\n{end}{post}"
