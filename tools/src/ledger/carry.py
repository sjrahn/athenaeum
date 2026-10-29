"""`ath ledger carry CLAIM --revision R` — upgrade carried elements to attested (spec/
ledger.md v47.1, §5.6 Derived views, non-normative tooling).

At a `diffed` revision, an element the diff left unchanged is **carried**: it holds there
without evidence from the revision's record, and its bar result comes from `against`.
`carry` re-anchors each carried element's unchanged quote in the revision's record.

The quote is the one the element's nearest attesting revision carries. It must match
exactly one stored, addressed segment of the revision's record. That segment's address
becomes the anchor of a new evidence entry from the revision's source, so the element
is then attested. A quote that matches no segment or several, or a record with no
formed segments, goes back to the author untouched. `carry` never guesses.

`plan_carry` writes nothing. `apply_carry` writes a plan behind the same `ath ledger
check` gate `merge` uses.
"""

from __future__ import annotations

from pathlib import Path

from corpus import textnorm
from ledger import ranged as ranged_mod
from ledger.corpora import CorpusJoin
from ledger.merge import MergeError, _dump, apply_merge
from ledger.model import is_redirect, load_json_dir
from ledger.verify import load_record_content

CarryError = MergeError


def plan_carry(ledger_root: Path, join: CorpusJoin, claim_id: str, revision: str) -> dict:
    """Plan re-anchoring every carried element of *claim_id* at *revision*."""
    plan: dict = {"claim": claim_id, "revision": revision, "errors": [], "carried": [],
                  "to_author": []}
    fid = claim_id.split(":", 1)[0]
    facts, _ = load_json_dir(ledger_root, "facts/*/*.json")
    found = [(p, o) for p, o in facts.items()
             if isinstance(o, dict) and o.get("id") == fid and not is_redirect(o)]
    if not found:
        plan["errors"].append(f"no living fact {fid!r}")
        return plan
    path, fact = found[0]
    claim = next((c for c in fact.get("claims") or []
                  if isinstance(c, dict) and c.get("id") == claim_id), None)
    if claim is None or not ranged_mod.is_folded(claim):
        plan["errors"].append(f"no folded ranged claim {claim_id!r}")
        return plan
    rr = ranged_mod.read_roster(fact)
    h = ranged_mod.compute_holding(claim, fact, rr)
    if revision not in h.entries:
        plan["errors"].append(f"{revision!r} is not reconciled on {claim_id!r}")
        return plan
    skey = h.entries[revision].get("source")
    sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
    record = (sources.get(skey) or {}).get("record") if isinstance(skey, str) else None
    content = load_record_content(join, str(record)) if record else None
    if content is None or not content.addressed:
        plan["errors"].append(
            f"{revision!r}'s record ({str(record)[:12]}…) has no formed, addressed "
            "segments to re-anchor into — form it first, or attest by hand")
        return plan
    carried = sorted(i for i, m in h.modes[revision].items() if m == ranged_mod.CARRIED)
    additions: list[dict] = []
    for i in carried:
        prior = next((r for r in h.chain(revision)[1:]
                      if i in h.attested.get(r, set())), None)
        quotes = [e for e in claim.get("evidence") or []
                  if isinstance(e, dict) and e.get("element") == i and e.get("quote")
                  and ranged_mod.source_revision(fact, rr, e.get("source")) == prior]
        if not quotes:
            plan["to_author"].append({"element": i, "why": "no quote to carry"})
            continue
        for e in quotes:
            hits = [addr for addr, texts in content.addressed.items()
                    if textnorm.quote_found(str(e["quote"]), "\n".join(texts))]
            if len(hits) != 1:
                plan["to_author"].append({
                    "element": i, "quote": str(e["quote"])[:120],
                    "why": "no segment prints it" if not hits
                    else f"{len(hits)} segments print it"})
                continue
            new = {"source": skey, "element": i, "kind": e.get("kind", "authoritative"),
                   "anchor": hits[0], "quote": e["quote"],
                   "note": f"carried from {prior} by `ath ledger carry`"}
            additions.append(new)
            plan["carried"].append({"element": i, "anchor": hits[0]})
    if not additions:
        plan["errors"].append("nothing to carry: no carried element's quote matched "
                              "exactly one segment")
        return plan
    claim["evidence"] = [*(claim.get("evidence") or []), *additions]
    rel = str(path.relative_to(ledger_root))
    plan["_writes"] = {rel: _dump(fact)}
    plan["_originals"] = {rel: path.read_text(encoding="utf-8")}
    return plan


def apply_carry(ledger_root: Path, plan: dict, join=None, datasets=None) -> None:
    apply_merge(ledger_root, plan, join, datasets, verb="carry")
