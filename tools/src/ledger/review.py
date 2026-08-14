"""The merge-review page — `ath ledger dedupe --review` (#182).

Renders `dedupe.propose()`'s CONCEPTS section as a self-contained HTML page
for a human judgment pass: side-by-side fact cards per candidate group, full
claims + evidence, so a merge/keep verdict can be reached without leaving the
browser. Read-only, like `dedupe` itself — this module never writes to the
ledger, only to the page path the caller gives it.

Numbering: groups are numbered by their 1-based position in
`proposal["concepts"]`, matching the order `ath ledger dedupe --section
concepts` prints — a reply like "merge 31 32; keep 12" is only unambiguous
because both surfaces share this one ordering. Adjudicated groups are sorted
after open ones for display, but keep their original number.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from ledger.model import is_redirect, load_json_dir, source_target

_MAX_VALUE_CHARS = 200

_CSS = """
:root {
  --bg:#fff; --fg:#1a1a1a; --mut:#666; --line:#ddd; --card:#f7f7f5;
  --acc:#0b6e4f; --q:#7a4b00; --bad:#9a1f1f;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg:#191919; --fg:#e8e8e8; --mut:#9a9a9a; --line:#3a3a3a; --card:#222;
    --acc:#5bd6a9; --q:#e0b36a; --bad:#e08a8a;
  }
}
:root[data-theme="dark"] {
  --bg:#191919; --fg:#e8e8e8; --mut:#9a9a9a; --line:#3a3a3a; --card:#222;
  --acc:#5bd6a9; --q:#e0b36a; --bad:#e08a8a;
}
body {
  background:var(--bg); color:var(--fg); font:15px/1.5 system-ui,sans-serif;
  max-width:1200px; margin:2rem auto; padding:0 1rem;
}
h1 { font-size:1.4rem }
h2 {
  font-size:1.15rem; margin:2.2rem 0 .3rem;
  border-top:1px solid var(--line); padding-top:1.2rem;
}
.b { color:var(--mut); font-weight:400; font-size:.85em }
.badge {
  color:var(--mut); font-size:.75em; border:1px solid var(--line);
  border-radius:1em; padding:.1em .6em; margin-left:.5em;
}
.pair { display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:1rem }
.group.adjudicated { opacity:.55 }
.card {
  background:var(--card); border:1px solid var(--line); border-radius:8px;
  padding:.8rem; overflow-x:auto;
}
.card.err { border-color:var(--bad); color:var(--bad) }
.card h3 { margin:.1rem 0 }
.nm { font-weight:600 }
.meta { color:var(--mut); font-size:.85em; margin:.3rem 0 .6rem; white-space:pre-wrap }
table { border-collapse:collapse; width:100%; font-size:.85em }
th, td {
  text-align:left; padding:.3rem .45rem;
  border-top:1px solid var(--line); vertical-align:top;
}
.p { white-space:nowrap; color:var(--acc); font-family:ui-monospace,monospace; font-size:.92em }
.st { color:var(--mut); white-space:nowrap }
.ev { margin-top:.15rem }
.q { color:var(--q); font-style:italic }
.n { color:var(--mut) }
.r { color:var(--mut); font-family:ui-monospace,monospace; font-size:.85em }
.footer {
  color:var(--mut); font-size:.8em; margin-top:3rem;
  border-top:1px solid var(--line); padding-top:1rem;
}
code { font-family:ui-monospace,monospace }
"""


def _load_facts(ledger_root: Path) -> dict[str, dict]:
    """id -> fact, tolerant (unparseable/redirect files are simply absent —
    callers render a missing id as an inline error card, never crash)."""
    facts, _errors = load_json_dir(ledger_root, "facts/*/*.json")
    by_id: dict[str, dict] = {}
    for fact in facts.values():
        if is_redirect(fact):
            continue
        fid = fact.get("id")
        if isinstance(fid, str) and fid:
            by_id[fid] = fact
    return by_id


def _is_adjudicated(ids: list[str], facts_by_id: dict[str, dict]) -> bool:
    """A group is adjudicated when some member's `meta` string names another
    member's id verbatim (the house pattern: "distinct from X", "NOT the
    same person as Y")."""
    for fid in ids:
        meta = (facts_by_id.get(fid) or {}).get("meta")
        if not isinstance(meta, str):
            continue
        if any(other != fid and other in meta for other in ids):
            return True
    return False


def classify_groups(ledger_root: Path, concepts: list[dict]) -> tuple[int, int]:
    """(open_count, adjudicated_count) over *concepts* — the same rule
    `render_review` renders by, exposed so callers (the CLI) can report
    counts without re-parsing the page."""
    facts_by_id = _load_facts(ledger_root)
    open_n = adjudicated_n = 0
    for group in concepts:
        ids = [i for i in (group.get("ids") or []) if isinstance(i, str)]
        if _is_adjudicated(ids, facts_by_id):
            adjudicated_n += 1
        else:
            open_n += 1
    return open_n, adjudicated_n


def _clip(text: str) -> str:
    if len(text) > _MAX_VALUE_CHARS:
        return text[:_MAX_VALUE_CHARS] + "…"
    return text


def _render_compact(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ": "))
    return html.escape(_clip(text))


def _render_meta(meta: object) -> str:
    if meta in (None, ""):
        return ""
    if isinstance(meta, str):
        return html.escape(_clip(meta))
    return _render_compact(meta)


def _render_claim_value(claim: dict) -> str:
    value = claim.get("value")
    if value in (None, ""):
        value = claim.get("object")
    if value in (None, ""):
        return ""
    if isinstance(value, (dict, list)):
        return _render_compact(value)
    return html.escape(_clip(str(value)))


def _evidence_ref(ev: dict, sources: dict) -> str | None:
    key = ev.get("source")
    if key is None:
        return None
    target = source_target(sources.get(str(key)))
    if target is None:
        return None
    kind, value = target
    return value[:8] if kind == "record" else f"ref:{value}"


def _render_evidence(evidence: object, sources: dict) -> str:
    if not isinstance(evidence, list):
        return ""
    items = []
    for ev in evidence:
        if not isinstance(ev, dict):
            continue
        parts = []
        quote = ev.get("quote")
        if isinstance(quote, str) and quote:
            parts.append(f'<span class="q">“{html.escape(quote)}”</span>')
        note = ev.get("note")
        if isinstance(note, str) and note:
            parts.append(f'<span class="n">{html.escape(note)}</span>')
        ref = _evidence_ref(ev, sources)
        if ref:
            parts.append(f'<span class="r">{html.escape(ref)}</span>')
        if parts:
            items.append(" ".join(parts))
    if not items:
        return ""
    return '<div class="ev">' + "<br>".join(items) + "</div>"


def _render_claims_table(fact: dict) -> str:
    sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
    rows = []
    for claim in fact.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        pred = html.escape(str(claim.get("predicate", "")))
        status = html.escape(str(claim.get("status", "")))
        value_html = _render_claim_value(claim)
        evidence_html = _render_evidence(claim.get("evidence"), sources)
        rows.append(
            f"<tr><td class=p>{pred}</td><td>{value_html}{evidence_html}</td>"
            f"<td class=st>{status}</td></tr>"
        )
    for art in fact.get("artifacts") or []:
        if not isinstance(art, dict):
            continue
        role = art.get("role")
        if not isinstance(role, str) or not role:
            continue
        note = art.get("note")
        note_html = html.escape(_clip(str(note))) if isinstance(note, str) and note else ""
        rows.append(f"<tr><td class=p>roster/{html.escape(role)}</td>"
                    f"<td colspan=2>{note_html}</td></tr>")
    return "".join(rows)


def _render_card(fid: str, fact: dict | None) -> str:
    if fact is None:
        return (
            f'<div class="card err"><h3><code>{html.escape(fid)}</code></h3>'
            f"<div class=meta>fact file not found or unreadable</div></div>"
        )
    name = fact.get("name") or fact.get("title") or fid
    aliases = [a for a in (fact.get("aliases") or []) if isinstance(a, str)]
    alias_html = f" — aka {html.escape(', '.join(aliases))}" if aliases else ""
    return (
        f'<div class="card"><h3><code>{html.escape(fid)}</code></h3>'
        f'<div class="nm">{html.escape(str(name))}{alias_html}</div>'
        f'<div class="meta">{_render_meta(fact.get("meta"))}</div>'
        f"<table><tr><th>predicate</th><th>value + evidence</th><th>status</th></tr>"
        f"{_render_claims_table(fact)}</table></div>"
    )


def _render_group(n: int, group: dict, facts_by_id: dict[str, dict], *, adjudicated: bool) -> str:
    basis = html.escape(str(group.get("basis", "")))
    label = html.escape(str(group.get("key") or group.get("type") or ""))
    badge = ' <span class="badge">adjudicated — see meta</span>' if adjudicated else ""
    section_class = " class=\"group adjudicated\"" if adjudicated else " class=group"
    ids = [i for i in (group.get("ids") or []) if isinstance(i, str)]
    cards = "".join(_render_card(fid, facts_by_id.get(fid)) for fid in ids)
    return (
        f"<section{section_class}><h2>#{n} <span class=b>[{basis} · {label}]</span>"
        f"{badge}</h2><div class=pair>{cards}</div></section>"
    )


def render_review(ledger_root: Path, proposal: dict) -> str:
    """The full merge-review HTML page for `proposal["concepts"]` — pure,
    reads only the fact files those groups cite. See module docstring for the
    numbering contract and the adjudication rule."""
    concepts = proposal.get("concepts") or []
    facts_by_id = _load_facts(ledger_root)

    classified = []
    for n, group in enumerate(concepts, start=1):
        ids = [i for i in (group.get("ids") or []) if isinstance(i, str)]
        classified.append((n, group, _is_adjudicated(ids, facts_by_id)))
    open_groups = [c for c in classified if not c[2]]
    adjudicated_groups = [c for c in classified if c[2]]

    sections = "".join(
        _render_group(n, group, facts_by_id, adjudicated=adjudicated)
        for n, group, adjudicated in open_groups + adjudicated_groups
    )

    return (
        "<!doctype html><html><head><meta charset=utf-8>"
        f"<title>Merge review</title><style>{_CSS}</style></head><body>"
        "<h1>Merge review</h1>"
        f"<p>{len(open_groups)} open · {len(adjudicated_groups)} adjudicated. "
        "Numbered as <code>ath ledger dedupe --section concepts</code> prints. Quotes are "
        "verbatim evidence spans from the cited corpus records (8-hex prefix shown). "
        "Reply with group numbers: e.g. “merge 31 32; keep 12”.</p>"
        f"{sections}"
        '<p class="footer">private working page — generated by '
        "<code>ath ledger dedupe --review</code>; regenerate any time, do not publish</p>"
        "</body></html>"
    )
