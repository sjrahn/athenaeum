"""The public projection — spec/athenaeum.md §5.1, spec/ledger.md §12.

One place the public plane's fail-closed filter computes, built entirely on
`ledger.tenancy`'s shared derivation (never reimplemented here): a fully
private fact is 404/omitted everywhere; a mixed fact strips private-backed
claims, unreferenced or privately-resolving sources entries, and roster
entries deriving private tenancy. Every predicate here is a `try/except` away
from its answer defaulting to "not public" — an exception during derivation
omits the item rather than risking a leak (§5.1: "any error path fails
CLOSED").
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ledger import tenancy as tenancy_mod
from ledger.model import CORPUS_URI_RE, derived_uri

if TYPE_CHECKING:
    from ath.manifest import Reference
    from ledger.corpora import CorpusJoin


def claim_is_public(
    claim: dict, sources: Mapping[str, object], join: CorpusJoin,
    datasets: Mapping[str, Reference],
) -> bool:
    try:
        return not tenancy_mod.claim_private_backed(claim, sources, join, datasets)
    except Exception:
        return False


def fact_is_public(fact: dict, join: CorpusJoin, datasets: Mapping[str, Reference]) -> bool:
    try:
        return not tenancy_mod.fact_is_private(fact, join, datasets)
    except Exception:
        return False


def roster_entry_is_public(entry: dict, join: CorpusJoin) -> bool:
    """A roster (`artifacts[]`) entry is public iff its `corpus://` uri
    resolves to a record whose derived tenancy is public. Unresolved
    (`is_private` -> None, the hash resolves nowhere the join can see) fails
    CLOSED — an ambiguous answer is not a public one."""
    try:
        m = CORPUS_URI_RE.match(str(entry.get("uri", "")))
        if not m:
            return False
        return join.is_private(m.group(1)) is False
    except Exception:
        return False


def project_fact(
    fact: dict, join: CorpusJoin, datasets: Mapping[str, Reference], *, owner: bool,
) -> dict[str, Any] | None:
    """*fact*, plane-filtered — the full object on the owner plane, the
    public projection (or None, meaning 404/omit) on the public plane.

    The public projection strips private-backed claims, sources-table
    entries no surviving claim's evidence references (or that themselves
    resolve privately), and roster entries deriving private tenancy — claims
    keep their `status` and evidence intact (the epistemic ladder survives
    into transport, §12).
    """
    if owner:
        return fact
    if not fact_is_public(fact, join, datasets):
        return None
    sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}

    kept_claims: list[dict] = []
    used_source_keys: set[str] = set()
    for c in fact.get("claims") or []:
        if not isinstance(c, dict):
            continue
        if not claim_is_public(c, sources, join, datasets):
            continue
        kept_claims.append(c)
        for e in c.get("evidence") or []:
            if isinstance(e, dict) and isinstance(e.get("source"), str):
                used_source_keys.add(e["source"])

    kept_sources: dict[str, object] = {}
    for skey, entry in sources.items():
        if not isinstance(skey, str) or skey not in used_source_keys:
            continue
        try:
            private = tenancy_mod.evidence_entry_private(entry, join, datasets)
        except Exception:
            continue  # fail closed: an unresolvable derivation is not servable
        if not private:
            kept_sources[skey] = entry

    kept_roster = [
        e for e in (fact.get("artifacts") or [])
        if isinstance(e, dict) and roster_entry_is_public(e, join)
    ]

    out = dict(fact)
    out["claims"] = kept_claims
    out["artifacts"] = kept_roster
    if sources or "sources" in fact:
        out["sources"] = kept_sources
    return out


def public_evidence_uris(
    fact: dict, join: CorpusJoin, datasets: Mapping[str, Reference],
) -> list[str]:
    """The `derived_uri`s a public-plane consumer of *fact* may see (§12): only
    from claims that pass `claim_is_public`, and only through sources entries
    that themselves resolve publicly — the same two gates `project_fact`
    applies to the fact object itself, applied here to `/scope`'s
    `evidence: references` URI expansion so it can never emit a private
    citation for a fact that also carries public claims (a whole-fact filter
    alone is not enough — a public fact can still carry private-backed
    claims whose evidence must not surface)."""
    sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
    uris: set[str] = set()
    for c in fact.get("claims") or []:
        if not isinstance(c, dict) or not claim_is_public(c, sources, join, datasets):
            continue
        for e in c.get("evidence") or []:
            if not isinstance(e, dict):
                continue
            skey = e.get("source")
            entry = sources.get(skey) if isinstance(skey, str) else None
            if entry is None:
                continue
            try:
                if tenancy_mod.evidence_entry_private(entry, join, datasets):
                    continue
            except Exception:
                continue  # fail closed: an unresolvable derivation is not servable
            uri = derived_uri(sources, e.get("source"), e.get("anchor"))
            if uri is not None:
                uris.add(uri)
    return sorted(uris)


def public_roster_uris(fact: dict, join: CorpusJoin) -> list[str]:
    """The roster `corpus://` uris of *fact* a public-plane consumer may see —
    `/scope`'s roster-follow expansion, filtered the same way `project_fact`
    filters a fact's own `artifacts[]`."""
    uris = {
        e["uri"] for e in fact.get("artifacts") or []
        if isinstance(e, dict) and isinstance(e.get("uri"), str) and roster_entry_is_public(e, join)
    }
    return sorted(uris)
