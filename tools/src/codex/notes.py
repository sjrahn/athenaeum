"""Note generation — the default scaffold template (`spec/codex.md` §4).

Deterministic first-cut notes from the scoped facts: every rendered assertion
carries its epistemic state and footnotes its evidence; interpretations are
visibly marked; frontmatter is the provenance contract. The codex's voice
refines templates on top of this — the scaffold guarantees the vault is
always regenerable and never unbacked.

Profiles apply here (§6): under a public profile, private-backed claims are
excluded or stubbed per the manifest, fully-private facts are omitted (or
stubbed) id-and-all, and links to private facts redact.
"""

from __future__ import annotations

from ledger.corpora import CorpusJoin
from ledger.model import CLAIM_ID_RE, CORPUS_URI_RE, derived_uri, is_edge

PRIVATE_MARK = "*(private evidence)*"


def _evidence_private(uri: str, join: CorpusJoin) -> bool:
    m = CORPUS_URI_RE.match(uri)
    if not m:
        return False  # ref:// is public; malformed is check's problem
    private = join.is_private(m.group(1))
    # None = resolves in no corpus (dangling, or a corpus missing on disk):
    # sensitivity is underivable, so the tenancy wall fails CLOSED (§6.4)
    return True if private is None else bool(private)


def claim_private(claim: dict, join: CorpusJoin, sources: dict) -> bool:
    if claim.get("sensitivity") == "private":
        return True
    return any(
        _evidence_private(derived_uri(sources, e.get("source"), e.get("anchor")) or "", join)
        for e in claim.get("evidence") or [] if isinstance(e, dict)
    )


def roster_private(entry: dict, join: CorpusJoin) -> bool:
    return _evidence_private(str(entry.get("uri", "")), join)


def fact_private(fact: dict, join: CorpusJoin) -> bool:
    if fact.get("sensitivity") == "private":
        return True
    sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
    carried = [claim_private(c, join, sources) for c in fact.get("claims") or []
               if isinstance(c, dict)]
    carried += [roster_private(e, join) for e in fact.get("artifacts") or []
                if isinstance(e, dict)]
    return bool(carried) and all(carried)


def interp_private(interp: dict, join: CorpusJoin, claims_by_id: dict[str, dict],
                   scoped: dict[str, dict]) -> bool:
    """`based_on` may cite corpus URIs, ref:// entries, or claim ids (§7.2) —
    a claim-id basis inherits that claim's privacy (resolved through the
    claim's OWNING fact's sources table, via the `{fact-id}:{short}` prefix);
    anything unresolvable fails closed."""
    for b in interp.get("based_on") or []:
        s = str(b)
        if CORPUS_URI_RE.match(s):
            if _evidence_private(s, join):
                return True
        elif s.startswith("ref://"):
            continue  # reference datasets are public mirrors
        else:
            m = CLAIM_ID_RE.match(s)
            c = claims_by_id.get(s) if m else None
            if c is None:
                return True  # unrecognized or dangling basis — underivable, fail closed
            sources = scoped.get(m.group(1), {}).get("sources") or {}
            if claim_private(c, join, sources):
                return True
    return False


def _render_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "; ".join(_render_value(v) for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k}: {_render_value(v)}" for k, v in value.items())
    return str(value)


def generate(
    scoped: dict[str, dict],
    riding: dict[str, dict],
    join: CorpusJoin,
    *,
    profile: str = "private",
    redact: str = "exclude",
    today: str = "",
) -> dict[str, str]:
    """→ {vault-relative path: markdown}. The private profile renders all."""
    public = profile != "private"
    out: dict[str, str] = {}
    claims_by_id = {
        c["id"]: c
        for o in scoped.values()
        for c in o.get("claims") or []
        if isinstance(c, dict) and c.get("id")
    }

    def link(ref: str | None) -> str:
        if not ref:
            return ""
        if ref in scoped and not (public and fact_private(scoped[ref], join)):
            return f"[[{ref}]]"
        return PRIVATE_MARK if public else str(ref)

    for fid, fact in scoped.items():
        private_file = fact_private(fact, join)
        if public and private_file:
            if redact == "exclude":
                continue
            out[f"{fact.get('type')}/{fid}.md"] = (
                f"---\nconcept: {fid}\ngenerated_from:\n"
                f"  - ledger/facts/{fact.get('type')}/{fid}.json\n"
                f"updated: {today}\n---\n\n# {PRIVATE_MARK}\n\n"
                "This entry derives entirely from private evidence.\n"
            )
            continue

        fact_sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
        gen_from = [f"ledger/facts/{fact.get('type')}/{fid}.json"]
        mine = [o for o in riding.values() if fid in (o.get("about") or [])]
        if public:
            mine = [o for o in mine if not interp_private(o, join, claims_by_id, scoped)]
        gen_from += [f"ledger/interpretations/{o.get('id')}.json"
                    for o in sorted(mine, key=lambda o: str(o.get("id")))]

        title = fact.get("name") or fact.get("title") or fid
        lines = [
            "---",
            f"concept: {fid}",
            "generated_from:",
            *[f"  - {s}" for s in gen_from],
            f"updated: {today}",
            "---",
            "",
            f"# {title}",
            "",
        ]
        subtitle = f"*{fact.get('type')}*"
        if fact.get("aliases"):
            subtitle += " — also: " + ", ".join(fact["aliases"])
        if is_edge(fact):
            members = [m for m in [fact.get("subject"), *(fact.get("participants") or [])]
                       if m]
            if members:
                subtitle += " — concerns " + ", ".join(
                    dict.fromkeys(link(str(m)) for m in members))
        if fact.get("period"):
            subtitle += f" — {fact['period']}"
        lines += [subtitle, ""]

        notes_idx = 0
        footnotes: list[str] = []
        embeds: list[str] = []

        def cite(evidence: list, notes: list[str] = footnotes,
                 gallery: list[str] = embeds, sources: dict = fact_sources) -> str:
            nonlocal notes_idx
            marks = []
            for e in evidence or []:
                if not isinstance(e, dict):
                    continue
                notes_idx += 1
                marks.append(f"[^{notes_idx}]")
                quote = f' — "{e["quote"]}"' if e.get("quote") else ""
                uri = derived_uri(sources, e.get("source"), e.get("anchor")) or ""
                notes.append(f"[^{notes_idx}]: `{uri}` "
                             f"({e.get('kind', '?')}){quote}")
                # a visual anchor (a PDF page, a video frame, a region) embeds —
                # the build rasters it through the corpus resolver
                if any(f"{p}=" in uri for p in ("page", "bbox", "frame")):
                    gallery.append(f"![[{uri}|evidence [{notes_idx}]]]")
            return "".join(marks)

        claims = [c for c in fact.get("claims") or [] if isinstance(c, dict)]
        rendered_claims = []
        for c in claims:
            if public and claim_private(c, join, fact_sources):
                if redact == "stub":
                    rendered_claims.append(
                        f"- **{c.get('predicate')}** — {PRIVATE_MARK}")
                continue
            parts = [f"- **{c.get('predicate')}**"]
            value = _render_value(c.get("value"))
            obj = link(c.get("object"))
            body = " — ".join(p for p in (value, obj) if p)
            if body:
                parts.append(f"— {body}")
            quals = {k: v for k, v in (c.get("qualifiers") or {}).items()}
            if quals:
                parts.append("(" + "; ".join(f"{k}: {_render_value(v)}"
                                             for k, v in quals.items()) + ")")
            when = c.get("period") or c.get("asof")
            if when:
                parts.append(f"*{when}*")
            parts.append(f"`{c.get('status')}`")
            line = " ".join(parts) + cite(c.get("evidence") or [])
            rendered_claims.append(line)
            if c.get("reasoning"):
                rendered_claims.append(f"  - *reasoning:* {c['reasoning']}")
        if rendered_claims:
            lines += ["## Facts", "", *rendered_claims, ""]

        roster = [e for e in fact.get("artifacts") or [] if isinstance(e, dict)]
        if public:
            roster = [e for e in roster if not roster_private(e, join)]
        if roster:
            lines += ["## Artifacts", ""]
            for e in roster:
                note = f" — {e['note']}" if e.get("note") else ""
                lines.append(f"- {e.get('role')}{note}: `{e.get('uri')}`")
            lines.append("")

        if embeds:
            lines += ["## Evidence gallery", "", *embeds, ""]

        if mine:
            lines += ["## Interpretive", "",
                      "> [!warning] Not asserted knowledge — the pre-assertion "
                      "workspace, rendered honestly.", ""]
            for o in sorted(mine, key=lambda o: str(o.get("id"))):
                conf = f" ({o['confidence']})" if o.get("confidence") else ""
                lines.append(f"- **{o.get('kind')}**{conf} `{o.get('status')}` — "
                             f"{o.get('statement')}")
            lines.append("")

        if footnotes:
            lines += [*footnotes, ""]
        out[f"{fact.get('type')}/{fid}.md"] = "\n".join(lines)
    return out
