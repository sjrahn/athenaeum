"""Mechanical promotion + challenge-pin stamping (`spec/ledger.md` §7.2—§7.3).

`promote` moves a claim-shaped hypothesis's `proposes` draft into its target
fact file at the highest status the authentication bar allows, stamps the
interpretation's `resolution` with the claim id, and sets `status: promoted`.
*(v47)* A hypothesis carrying `proposes_new` first MINTS the concept it names
(`facts/{type}/{id}.json`) and lands that block's draft claims on it; a `proposes`
beside it may target the new fact or name it as its `object`. Everything is
validated before anything is written — a promotion lands whole or not at all.
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
    SLUG_RE,
    canonical_claim_state,
    ensure_source,
    load_lineage,
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
    """Promote interpretation *interp_id*; returns what landed (claim ids with status,
    and the minted fact when `proposes_new` minted one)."""
    ipath = ledger_root / "interpretations" / f"{interp_id}.json"
    if not ipath.is_file():
        raise PromoteError(f"no interpretation {interp_id!r}")
    interp = _load(ipath)
    if interp.get("kind") != "hypothesis":
        raise PromoteError("only hypotheses promote (assessments/corrections retire)")
    if interp.get("status") != "open":
        raise PromoteError(f"status is {interp.get('status')!r}, not open")
    proposes = interp.get("proposes")
    proposes_new = interp.get("proposes_new")
    if not isinstance(proposes, dict) and not isinstance(proposes_new, dict):
        raise PromoteError(
            "no proposes / proposes_new draft — promotion is manual authoring"
        )

    # validate the whole promotion before writing any of it
    facts: dict[str, tuple[Path, dict]] = {}  # fact id -> (path, fact object)
    drafts: list[tuple[str, dict]] = []  # (target fact id, draft claim)
    minted: str | None = None
    if isinstance(proposes_new, dict):
        minted = _plan_mint(ledger_root, proposes_new, facts)
        for dc in proposes_new.get("claims") or []:
            drafts.append((_draft_target(dc, "proposes_new claim", only=minted), dc))
    if isinstance(proposes, dict):
        drafts.append((_draft_target(proposes, "proposes"), proposes))
    for target, dc in drafts:
        if target not in facts:
            fpath = _find_fact(ledger_root, target)
            facts[target] = (fpath, _load(fpath))
        fact = facts[target][1]
        if any(c.get("id") == dc["id"] for c in fact.get("claims") or []):
            raise PromoteError(f"claim {dc['id']!r} already exists on {target!r}")
        if sum(1 for _, other in drafts if other.get("id") == dc["id"]) > 1:
            raise PromoteError(f"claim id {dc['id']!r} is proposed twice")
        if not dc.get("evidence"):
            raise PromoteError(f"{dc['id']}: no evidence — a claim cannot land bare")

    landed = [_land_claim(facts[target][1], dc, interp) for target, dc in drafts]
    for fpath, fact in facts.values():
        fpath.parent.mkdir(parents=True, exist_ok=True)
        _save(fpath, fact)
    interp["status"] = "promoted"
    interp["resolution"] = proposes["id"] if isinstance(proposes, dict) else minted
    _save(ipath, interp)
    out = ", ".join(f"{c['id']} ({c['status']})" for c in landed)
    if minted:
        out = f"minted {minted}" + (f"; {out}" if out else "")
    return out


def _plan_mint(ledger_root: Path, spec: dict, facts: dict[str, tuple[Path, dict]]) -> str:
    """The concept `proposes_new` names, as a fact file not yet written — refused when its
    id is taken by a fact, an interpretation, or a lineage key (§4.1: one namespace)."""
    nid, ntype = str(spec.get("id") or ""), str(spec.get("type") or "")
    name = str(spec.get("name") or "").strip()
    if not SLUG_RE.match(nid) or not SLUG_RE.match(ntype) or not name:
        raise PromoteError("proposes_new needs a slug `id`, a slug `type`, and a `name`")
    lineage, _errors = load_lineage(ledger_root)
    if (
        any(ledger_root.glob(f"facts/*/{nid}.json"))
        or (ledger_root / "interpretations" / f"{nid}.json").is_file()
        or nid in lineage
    ):
        raise PromoteError(f"proposes_new.id {nid!r} is already taken — propose on it instead")
    facts[nid] = (
        ledger_root / "facts" / ntype / f"{nid}.json",
        {"id": nid, "type": ntype, "name": name, "claims": []},
    )
    return nid


def _draft_target(dc: object, label: str, *, only: str | None = None) -> str:
    """The fact id a draft claim's `{fact-id}:{short}` id targets."""
    if not isinstance(dc, dict):
        raise PromoteError(f"{label} is not a draft Claim object")
    m = CLAIM_ID_RE.match(str(dc.get("id", "")))
    if not m:
        raise PromoteError(f"{label}.id {dc.get('id')!r} is not a claim id")
    if only is not None and m.group(1) != only:
        raise PromoteError(f"{label}.id {dc['id']!r} must target the minted fact {only!r}")
    return m.group(1)


def _land_claim(fact: dict, draft: dict, interp: dict) -> dict:
    """Append *draft* to *fact* as a claim, at the status the §5.4 bar allows."""
    claim = dict(draft)
    claim["status"] = bar_status(claim)  # computed on the pre-landing uri shape, below
    # a draft predates the fact it targets, so it has no sources table of its own — it
    # still carries the pre-reforge inline `uri` (design corner: interpretations are
    # unchanged, so this shape stays until landing); promotion is where it hoists into
    # the target fact's sources table, reusing an entry already targeting the same
    # record/ref.
    claim["evidence"] = _land_evidence(fact, claim.get("evidence") or [])
    if "asof" not in claim and interp.get("asof"):
        claim["asof"] = interp["asof"]
    fact.setdefault("claims", []).append(claim)
    return claim


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
            # group(2) is the optional pinned tag (§6.5) — carry it through so a
            # pinned inline uri lands as a pinned sources-table ref, not a bare one.
            pin = f"@{rm.group(2)}" if rm.group(2) else ""
            e2["source"] = ensure_source(fact, ref=f"{rm.group(1)}{pin}/{rm.group(3)}")
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
