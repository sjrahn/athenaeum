"""Mechanical promotion + challenge-pin stamping (`spec/ledger.md` §7.2—§7.3).

`promote` moves a claim-shaped hypothesis's `proposes` draft into its target
fact file at the highest status the authentication bar allows, stamps the
interpretation's `resolution` with the claim id, and sets `status: promoted`.
`stamp` (re-)pins a correction's `challenges.state` to the challenged claim's
canonical content state — run it when filing a challenge, and again after
re-reviewing a flagged edit.
"""

from __future__ import annotations

import json
from pathlib import Path

from ledger.model import (
    CLAIM_ID_RE,
    CORPUS_URI_RE,
    REF_URI_RE,
    canonical_claim_state,
    ensure_source,
)


class PromoteError(RuntimeError):
    pass


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _find_fact(ledger_root: Path, fact_id: str) -> Path:
    hits = [p for p in ledger_root.glob("facts/*/*.json") if p.stem == fact_id]
    if not hits:
        raise PromoteError(f"no fact file for {fact_id!r}")
    return hits[0]


def bar_status(claim: dict) -> str:
    """The highest status the §5.4 bar allows for this evidence set."""
    evs = [e for e in claim.get("evidence") or [] if isinstance(e, dict)]
    has_auth = any(e.get("kind") == "authoritative" for e in evs)
    hashes = {e.get("uri", "")[9:9 + 64] for e in evs
              if str(e.get("uri", "")).startswith("corpus://")}
    return "confirmed" if (has_auth or len(hashes) >= 2) else "provisional"


def promote(ledger_root: Path, interp_id: str) -> str:
    """Promote interpretation *interp_id*; returns the landed claim id."""
    ipath = ledger_root / "interpretations" / f"{interp_id}.json"
    if not ipath.is_file():
        raise PromoteError(f"no interpretation {interp_id!r}")
    interp = _load(ipath)
    if interp.get("kind") != "hypothesis":
        raise PromoteError("only hypotheses promote (assessments/corrections retire)")
    if interp.get("status") != "open":
        raise PromoteError(f"status is {interp.get('status')!r}, not open")
    proposes = interp.get("proposes")
    if not isinstance(proposes, dict):
        raise PromoteError("no proposes draft claim — promotion is manual authoring")
    m = CLAIM_ID_RE.match(str(proposes.get("id", "")))
    if not m:
        raise PromoteError(f"proposes.id {proposes.get('id')!r} is not a claim id")
    fpath = _find_fact(ledger_root, m.group(1))
    fact = _load(fpath)
    if any(c.get("id") == proposes["id"] for c in fact.get("claims") or []):
        raise PromoteError(f"claim {proposes['id']!r} already exists on {m.group(1)!r}")
    if not proposes.get("evidence"):
        raise PromoteError("proposes carries no evidence — a claim cannot land bare")
    claim = dict(proposes)
    claim["status"] = bar_status(claim)  # computed on the pre-landing uri shape, below
    # `proposes` predates the fact it targets, so it has no sources table of
    # its own — it still carries the pre-reforge inline `uri` (design corner:
    # interpretations are unchanged, so this shape stays until landing);
    # promotion is where it hoists into the target fact's sources table,
    # reusing an entry already targeting the same record/ref.
    claim["evidence"] = _land_evidence(fact, claim.get("evidence") or [])
    if "asof" not in claim and interp.get("asof"):
        claim["asof"] = interp["asof"]
    fact.setdefault("claims", []).append(claim)
    _save(fpath, fact)
    interp["status"] = "promoted"
    interp["resolution"] = claim["id"]
    _save(ipath, interp)
    return f"{claim['id']} ({claim['status']})"


def _land_evidence(fact: dict, evidence: list) -> list:
    """Translate `proposes`-shaped (inline `uri`) evidence into the sources-table
    shape as it lands on *fact*, minting/reusing sources entries as needed."""
    landed = []
    for e in evidence:
        if not isinstance(e, dict):
            landed.append(e)
            continue
        uri = str(e.get("uri", ""))
        cm = CORPUS_URI_RE.match(uri)
        rm = REF_URI_RE.match(uri)
        e2 = {k: v for k, v in e.items() if k != "uri"}
        if cm:
            tail = cm.group(2) or ""
            # strip a leading '?' (query-param anchor); a '#fragment' anchor
            # keeps its '#' — it's a different addressing form, not a query
            anchor = tail[1:] if tail[:1] == "?" else tail
            e2["source"] = ensure_source(fact, record=cm.group(1))
            if anchor:
                e2["anchor"] = anchor
        elif rm:
            e2["source"] = ensure_source(fact, ref=f"{rm.group(1)}/{rm.group(2)}")
        landed.append(e2)
    return landed


def stamp(ledger_root: Path, interp_id: str) -> str:
    """(Re-)pin a correction's challenge to the current claim content state."""
    ipath = ledger_root / "interpretations" / f"{interp_id}.json"
    if not ipath.is_file():
        raise PromoteError(f"no interpretation {interp_id!r}")
    interp = _load(ipath)
    challenges = interp.get("challenges")
    if not isinstance(challenges, dict) or not challenges.get("claim"):
        raise PromoteError("no challenges.claim to pin")
    target = str(challenges["claim"])
    m = CLAIM_ID_RE.match(target)
    if not m:
        raise PromoteError(f"challenges.claim {target!r} is not a claim id")
    fact = _load(_find_fact(ledger_root, m.group(1)))
    claim = next((c for c in fact.get("claims") or [] if c.get("id") == target), None)
    if claim is None:
        raise PromoteError(f"claim {target!r} not found on {m.group(1)!r}")
    sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
    challenges["state"] = canonical_claim_state(claim, sources)
    _save(ipath, interp)
    return challenges["state"]
