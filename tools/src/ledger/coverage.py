"""Coverage — the corpus→ledger representation ledger (`spec/ledger.md` §9).

Every in-scope record should be *represented*: cited as evidence by a fact or
interpretation, or rostered on a concept. `coverage.md` aggregates per corpus
and per source group (origin host / origin id / mime) — the record-level
backlog is queryable (`ath ledger worklist <hash>` answers the inverse), the
generated file stays readable. Regeneration sweeps every record, so it rides
`ath ledger regen --coverage`, not the default regen.

The manifestation-tier reading (§4.2, §9) adds two views on top of the
aggregate counts: **representation demand** — each backlog record's line
names the prescribed work item (identify the work it manifests; stub it if
new; roster it with representation fields) — and the **reverse read** — per
concept, rostered manifestations no claim or interpretation has ever cited.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ledger.corpora import RegisteredCorpus
from ledger.model import CORPUS_REF_RE, CORPUS_URI_RE, FULL_HASH_RE

COVERAGE_PATH = "coverage.md"


def represented_hashes(ledger_root: Path) -> set[str]:
    """Every corpus hash the ledger cites or rosters, anywhere: roster
    `artifacts[].uri` and interpretation `based_on`/`needs[].record` are still
    raw `corpus://` strings (a plain text scan finds them), but claim evidence
    now cites a bare hash under a fact's `sources[].record` — parsed from each
    fact's JSON, since no `corpus://` substring appears in the file for it."""
    out: set[str] = set()
    for pattern in ("facts/*/*.json", "interpretations/*.json"):
        for f in ledger_root.glob(pattern):
            text = f.read_text(encoding="utf-8")
            out.update(CORPUS_REF_RE.findall(text))
            if not pattern.startswith("facts"):
                continue
            try:
                fact = json.loads(text)
            except (json.JSONDecodeError, OSError):
                continue
            for entry in (fact.get("sources") or {}).values():
                if isinstance(entry, dict):
                    h = entry.get("record")
                    if isinstance(h, str) and FULL_HASH_RE.match(h):
                        out.add(h)
    return out


def cited_hashes(ledger_root: Path) -> set[str]:
    """Hashes actually **cited as evidence** — fact claim `sources[].record`
    and interpretation `based_on`/`needs[].record` — deliberately narrower
    than `represented_hashes`: it excludes roster-only presence, so a
    concept's rostered manifestation that no claim has ever leaned on can be
    told apart from one that has (§9's reverse read)."""
    out: set[str] = set()
    for f in ledger_root.glob("facts/*/*.json"):
        try:
            fact = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for entry in (fact.get("sources") or {}).values():
            if isinstance(entry, dict):
                h = entry.get("record")
                if isinstance(h, str) and FULL_HASH_RE.match(h):
                    out.add(h)
    for f in ledger_root.glob("interpretations/*.json"):
        try:
            interp = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for b in interp.get("based_on") or []:
            m = CORPUS_REF_RE.search(str(b))
            if m:
                out.add(m.group(1))
        for n in interp.get("needs") or []:
            if isinstance(n, dict):
                m = CORPUS_REF_RE.search(str(n.get("record", "")))
                if m:
                    out.add(m.group(1))
    return out


def rostered_never_cited(ledger_root: Path) -> dict[str, list[dict]]:
    """§9's reverse read: `{concept id: [stale roster entries]}` for every
    concept carrying at least one rostered manifestation no claim or
    interpretation cites — concepts with none are absent, not empty."""
    cited = cited_hashes(ledger_root)
    out: dict[str, list[dict]] = {}
    for f in ledger_root.glob("facts/*/*.json"):
        try:
            fact = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        artifacts = fact.get("artifacts")
        if not artifacts:
            continue
        stale = []
        for entry in artifacts:
            if not isinstance(entry, dict):
                continue
            m = CORPUS_URI_RE.match(str(entry.get("uri", "")))
            if m and m.group(1) not in cited:
                stale.append(entry)
        if stale:
            out[str(fact.get("id"))] = stale
    return out


def _group_key(facts: dict) -> str:
    return str(facts.get("origin.host") or facts.get("origin.id")
               or facts.get("mime") or "(no origin)")


def _backlog_line(h: str, facts: dict) -> str:
    """One representation-demand line (§9) for an uncovered record: the
    prescribed work item, plus whatever mechanical identification the corpus
    already gave it."""
    bits = [f"`{h[:12]}…`"]
    host = facts.get("origin.host")
    if host:
        bits.append(f"host `{host}`")
    mime = facts.get("mime")
    if mime:
        bits.append(f"mime `{mime}`")
    return ("- " + " · ".join(bits) + " — identify the work this record "
            "manifests; stub it if new (§4.2); roster it with representation "
            "fields.")


def render_coverage(ledger_root: Path, corpora: list[RegisteredCorpus]) -> str:
    from corpus import records
    from ledger.harvest import record_facts

    covered = represented_hashes(ledger_root)
    parts = [
        "# Coverage — GENERATED\n\n"
        "The corpus→ledger representation ledger (`spec/ledger.md` §9): a record is\n"
        "**represented** when a fact or interpretation cites it as evidence or a\n"
        "concept rosters it. Regenerated by `ath ledger regen --coverage` — never\n"
        "hand-edit. The record-level backlog is queryable per group via\n"
        "`corpus find` + `ath ledger worklist <hash>`.\n"
    ]
    for corpus in corpora:
        if not corpus.available:
            parts.append(f"\n## {corpus.name}\n\n*(not on disk — skipped)*\n")
            continue
        total = Counter()
        hit = Counter()
        n_total = n_hit = 0
        backlog: list[tuple[str, dict]] = []
        for path in records.iter_record_paths(corpus.root):
            try:
                post = records.load(path)
            except Exception:
                continue
            facts = record_facts(post)
            group = _group_key(facts)
            total[group] += 1
            n_total += 1
            h = str(post.metadata.get("id", path.stem))
            if h in covered:
                hit[group] += 1
                n_hit += 1
            else:
                backlog.append((h, facts))
        parts.append(f"\n## {corpus.name}\n\n{n_hit} of {n_total} records represented "
                     f"({(100 * n_hit // n_total) if n_total else 0}%).\n\n"
                     "| source | records | represented |\n|---|---:|---:|\n")
        for group, n in total.most_common():
            parts.append(f"| `{group}` | {n} | {hit.get(group, 0)} |\n")
        if backlog:
            parts.append("\n### Backlog — representation demand (§9)\n\n")
            for h, facts in sorted(backlog):
                parts.append(_backlog_line(h, facts) + "\n")

    parts.append(
        "\n## Rostered, never cited\n\n"
        "The reverse read (§9): per concept, rostered manifestations no claim or\n"
        "interpretation has ever cited — the representations an authoring pass has\n"
        "not leaned on yet.\n\n"
    )
    stale_by_concept = rostered_never_cited(ledger_root)
    if not stale_by_concept:
        parts.append("*(none)*\n")
    else:
        for cid in sorted(stale_by_concept):
            bits = []
            for entry in stale_by_concept[cid]:
                m = CORPUS_URI_RE.match(str(entry.get("uri", "")))
                h = f"{m.group(1)[:12]}…" if m else str(entry.get("uri"))
                tag = str(entry.get("role") or "?")
                if entry.get("modality"):
                    tag += f"/{entry['modality']}"
                bits.append(f"`{tag}` `{h}`")
            parts.append(f"- `{cid}` — " + ", ".join(bits) + "\n")
    return "".join(parts)
