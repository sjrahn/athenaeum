"""The plane projection — spec/athenaeum.md §5.1, spec/ledger.md §12.

One place a plane's fail-closed filter computes, parameterized by the
reader's grant set (§6.4): the public plane is exactly the `grants =
{"public"}` specialization every audience plane rides through the same code
path — "the planes are the grant sets" (spec/athenaeum.md §5.1). Built
entirely on `ledger.tenancy`'s shared derivation (never reimplemented here):
a fact invisible to the grant set is 404/omitted everywhere; a
partially-visible fact strips claims the grant set can't see, sources-table
entries no surviving claim references (or that themselves resolve outside
the grant set), and roster entries whose derived tier set doesn't intersect
it. Every predicate here is a `try/except` away from its answer defaulting
to "not visible" — an exception during derivation omits the item rather
than risking a leak (§5.1: "any error path fails CLOSED").
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ledger import tenancy as tenancy_mod
from ledger.model import CORPUS_URI_RE, derived_uri

if TYPE_CHECKING:
    from ath.manifest import Reference
    from ledger.corpora import CorpusJoin


def claim_is_visible(
    claim: dict, sources: Mapping[str, object], join: CorpusJoin,
    datasets: Mapping[str, Reference], grants: frozenset[str], *,
    declared: frozenset[str] | None = None,
) -> bool:
    try:
        return tenancy_mod.claim_visible(claim, sources, join, datasets, grants,
                                         declared=declared)
    except Exception:
        return False


def fact_is_visible(
    fact: dict, join: CorpusJoin, datasets: Mapping[str, Reference],
    grants: frozenset[str], *, declared: frozenset[str] | None = None,
) -> bool:
    try:
        return tenancy_mod.fact_visible(fact, join, datasets, grants, declared=declared)
    except Exception:
        return False


def _roster_tiers(
    uri: str, join: CorpusJoin, *, declared: frozenset[str] | None,
) -> frozenset[str]:
    """The tier set a roster `corpus://` uri's resolved record carries — the
    union across every corpus holding it, mirroring `CorpusJoin.is_private`'s
    own holder loop generalized to the tier set the way
    `ledger.tenancy._held_tiers` does for evidence entries: `record_tiers`
    does the actual derivation, this only unions it across holders. Empty
    when the uri doesn't match `corpus://` or resolves nowhere — unresolved
    contributes no tier, so it fails CLOSED against any grant set."""
    m = CORPUS_URI_RE.match(uri)
    if not m:
        return frozenset()
    h = m.group(1)
    held = join.holders(h)
    if not held:
        return frozenset()
    tiers: set[str] = set()
    for c in held:
        tiers |= tenancy_mod.record_tiers(c.root, h, default=c.floor, declared=declared)
    return frozenset(tiers)


def roster_entry_is_visible(
    entry: dict, join: CorpusJoin, grants: frozenset[str], *,
    declared: frozenset[str] | None = None,
) -> bool:
    """A roster (`artifacts[]`) entry is visible to `grants` iff its
    `corpus://` uri resolves to a record whose derived tier set intersects
    `grants`. Unresolved fails CLOSED — an ambiguous answer is not a visible
    one."""
    try:
        return bool(_roster_tiers(str(entry.get("uri", "")), join, declared=declared) & grants)
    except Exception:
        return False


def project_fact(
    fact: dict, join: CorpusJoin, datasets: Mapping[str, Reference], *,
    owner: bool, grants: frozenset[str], declared: frozenset[str] | None = None,
) -> dict[str, Any] | None:
    """*fact*, plane-filtered — the full object on the owner plane, the
    projection for `grants` (or None, meaning 404/omit) on every other
    plane. The public plane is exactly `grants=frozenset({"public"})`.

    The projection strips claims invisible to `grants`, sources-table
    entries no surviving claim's evidence references (or that themselves
    resolve outside `grants`), and roster entries whose derived tier set
    doesn't intersect `grants` — claims keep their `status` and evidence
    intact (the epistemic ladder survives into transport, §12).
    """
    if owner:
        return fact
    if not fact_is_visible(fact, join, datasets, grants, declared=declared):
        return None
    sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}

    kept_claims: list[dict] = []
    used_source_keys: set[str] = set()
    for c in fact.get("claims") or []:
        if not isinstance(c, dict):
            continue
        if not claim_is_visible(c, sources, join, datasets, grants, declared=declared):
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
            visible = tenancy_mod.evidence_entry_visible(entry, join, datasets, grants,
                                                          declared=declared)
        except Exception:
            continue  # fail closed: an unresolvable derivation is not servable
        if visible:
            kept_sources[skey] = entry

    kept_roster = [
        e for e in (fact.get("artifacts") or [])
        if isinstance(e, dict) and roster_entry_is_visible(e, join, grants, declared=declared)
    ]

    out = dict(fact)
    out["claims"] = kept_claims
    out["artifacts"] = kept_roster
    if sources or "sources" in fact:
        out["sources"] = kept_sources
    return out


def visible_evidence_uris(
    fact: dict, join: CorpusJoin, datasets: Mapping[str, Reference],
    grants: frozenset[str], *, declared: frozenset[str] | None = None,
) -> list[str]:
    """The `derived_uri`s a `grants`-plane consumer of *fact* may see (§12):
    only from claims that pass `claim_is_visible`, and only through sources
    entries that themselves resolve within `grants` — the same two gates
    `project_fact` applies to the fact object itself, applied here to
    `/scope`'s `evidence: references` URI expansion so it can never emit a
    citation outside `grants` for a fact that also carries claims visible to
    it (a whole-fact filter alone is not enough — a visible fact can still
    carry claims whose evidence must not surface to this grant set)."""
    sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
    uris: set[str] = set()
    for c in fact.get("claims") or []:
        if not isinstance(c, dict) or not claim_is_visible(c, sources, join, datasets, grants,
                                                            declared=declared):
            continue
        for e in c.get("evidence") or []:
            if not isinstance(e, dict):
                continue
            skey = e.get("source")
            entry = sources.get(skey) if isinstance(skey, str) else None
            if entry is None:
                continue
            try:
                if not tenancy_mod.evidence_entry_visible(entry, join, datasets, grants,
                                                           declared=declared):
                    continue
            except Exception:
                continue  # fail closed: an unresolvable derivation is not servable
            uri = derived_uri(sources, e.get("source"), e.get("anchor"))
            if uri is not None:
                uris.add(uri)
    return sorted(uris)


def visible_roster_uris(
    fact: dict, join: CorpusJoin, grants: frozenset[str], *,
    declared: frozenset[str] | None = None,
) -> list[str]:
    """The roster `corpus://` uris of *fact* a `grants`-plane consumer may
    see — `/scope`'s roster-follow expansion, filtered the same way
    `project_fact` filters a fact's own `artifacts[]`."""
    uris = {
        e["uri"] for e in fact.get("artifacts") or []
        if isinstance(e, dict) and isinstance(e.get("uri"), str)
        and roster_entry_is_visible(e, join, grants, declared=declared)
    }
    return sorted(uris)
