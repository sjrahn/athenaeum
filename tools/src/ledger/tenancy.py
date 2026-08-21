"""Record tenancy — the §6.4 sensitivity input, derived per record.

Tenancy at the knowledge layer is computed, not partitioned. The tier set is
instance-declared: two tiers are reserved with fixed semantics — `public`
(the publishable tier the §12 wall keys on) and `private` (the floor, the
owner's alone, never grantable) — and the instance MAY declare further tiers
(`family`, `accountant`, …) in its config (`spec/athenaeum.md` §2.3). An
instance declaring nothing has exactly the `public | private` binary — every
pre-tier instance is already conformant, byte-identically.

A record's tenancy is the **union** of the tiers its origins declare (an
origin overlay MAY declare `tenancy: {tier}` from the declared set —
deployment metadata the ledger reads schema-first; the corpus itself never
consumes it) plus every tier inherited through an origin's `corpus://`
lineage (a promoted member takes its container's tenancy, chased
transitively). A record whose origins declare nothing falls closed to the
`default` the caller passes — the holding corpus's manifest `visibility:`
floor. A declared value not in the instance's tier set contributes nothing
(fail closed — `ledger.check` reports the mismatch; derivation just ignores
it). Union generalizes any-public-wins: bytes demonstrably public are public
evidence even if also captured privately — an additional capture only ever
*widens* a record's disclosure, never narrows it.

Visibility is grant intersection: a reader holds a grant set of tiers; a
record is visible to grant set G iff its tier set intersects G. `evidence_*`,
`claim_*`, and `fact_*` below compute this per §6.4's claim/file rules;
`*_private`/`*_private_backed` are the `G = {public}` specialization every
existing caller (`ledger.check`, `ath.serve`) already rides.

Everything here is a read-only library call into the corpus package (ledger
depends on corpus — never a re-implementation), tolerant by contract: an
unreadable record, a malformed origin, a missing overlay, or an unresolved
citation contributes nothing — visible/absent facts never invent a lock, and
the fail-closed default (or the empty set) carries the answer.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from ledger.model import FULL_HASH_RE, SOURCE_REF_RE

if TYPE_CHECKING:
    from ath.manifest import Reference
    from ledger.corpora import CorpusJoin

_CORPUS_URI_HASH_RE = re.compile(r"^corpus://([0-9a-f]{64})")
_MAX_LINEAGE_HOPS = 8  # containers nest shallowly; a cycle or runaway stops cold

# `declared=None` means "no instance tier declarations reachable" — the
# pre-tier binary every undeclared caller (and every existing test) rides.
_BINARY_TIERS = frozenset({"public", "private"})
_PUBLIC_GRANTS = frozenset({"public"})


def _origin_uris(origin: dict) -> list[str]:
    fields = origin.get("fields") if isinstance(origin.get("fields"), dict) else {}
    uri = fields.get("uri")
    if isinstance(uri, list):
        return [u for u in uri if isinstance(u, str)]
    return [uri] if isinstance(uri, str) else []


def record_tiers(
    corpus_root: Path,
    hash_: str,
    *,
    default: str = "private",
    declared: frozenset[str] | None = None,
    _seen: set[str] | None = None,
) -> frozenset[str]:
    """The set of tiers the record at `hash_` in `corpus_root` carries (§6.4).

    The union of: the most specific origin-overlay `tenancy:` declaration per
    origin (subtype-first ladder — `youtube.com/unlisted` may answer
    `private` under a `youtube.com` base that answers `public`), and every
    tier reachable through an origin's `corpus://` lineage, chased
    transitively (a promoted member takes its container's tenancy). A
    declared value outside `declared` contributes nothing for that rung — the
    ladder keeps walking to the next, less-specific one, exactly as an
    unrecognized value always has.

    `declared` is the instance's tier set; `None` means the binary
    `{public, private}` (every value-kind caller not yet tier-aware). `default`
    is the holding corpus's manifest visibility floor — the fail-closed
    answer for a record whose reachable declarations are empty. Lineage
    recursion carries the same `default` and `declared`: a member chain that
    never meets a declaration lands on the floor, exactly like a standalone
    undeclared record.
    """
    seen = _seen if _seen is not None else set()
    if hash_ in seen or len(seen) > _MAX_LINEAGE_HOPS:
        return frozenset({default})
    seen.add(hash_)

    from corpus import paths, records  # heavy import, deferred
    from corpus.schemas import load_origin_overlay_by_id

    try:
        post = records.load(paths.record_path(corpus_root, hash_))
    except Exception:  # tolerant by contract: unreadable → the floor answers
        return frozenset({default})

    valid = declared if declared is not None else _BINARY_TIERS
    tiers: set[str] = set()
    lineage_parents: list[str] = []
    for origin in records.iter_origin_blocks(post):
        if not isinstance(origin, dict):
            continue
        oid = origin.get("id")
        subtype = origin.get("subtype")
        if isinstance(oid, str) and oid:
            # subtype-first, matching the overlay ladder (corpus §7.2): the most
            # specific declaration wins — `youtube.com/unlisted` may answer
            # `private` under a `youtube.com` base that answers `public`.
            ladder = ([f"{oid}/{subtype}"] if isinstance(subtype, str) and subtype
                      else []) + [oid]
            for rung in ladder:
                overlay = load_origin_overlay_by_id(corpus_root, rung) or {}
                tenancy = overlay.get("tenancy")
                if isinstance(tenancy, str) and tenancy in valid:
                    tiers.add(tenancy)
                    break
        for u in _origin_uris(origin):
            m = _CORPUS_URI_HASH_RE.match(u)
            if m:
                lineage_parents.append(m.group(1))

    for parent in lineage_parents:
        tiers |= record_tiers(corpus_root, parent, default=default, declared=declared,
                               _seen=seen)

    return frozenset(tiers) if tiers else frozenset({default})


def record_tenancy(
    corpus_root: Path,
    hash_: str,
    *,
    default: str = "private",
    _seen: set[str] | None = None,
) -> str:
    """``"public"`` or ``"private"`` for the record at `hash_` in `corpus_root`
    — the pre-v30 binary compatibility wrapper over `record_tiers` (always
    `declared=None`, the binary tier set). Byte-identical to the pre-tier
    scalar derivation for every binary instance."""
    return "public" if "public" in record_tiers(
        corpus_root, hash_, default=default, _seen=_seen) else "private"


# --------------------------------------------------------------- claim/fact §6.4
#
# Shared by `ledger.check` (the validation counts) and the read surface
# (`ath.serve`, spec Part I §5.1) — the ONE place a claim's/fact's derived
# sensitivity computes, so a consumer's publication filter and `ath ledger
# check`'s note never disagree. Tolerant throughout: a malformed sources
# entry or an unresolvable citation contributes nothing (dangling citations
# are `check`'s to flag, not this module's) — never raises on ordinary
# ledger data.


def _held_tiers(
    hash_: str, join: CorpusJoin, *, declared: frozenset[str] | None,
) -> frozenset[str]:
    """The union of tier sets `hash_` carries across every corpus holding it
    — §6.4's any-public-wins generalized to any-tier-wins, mirroring
    `CorpusJoin.is_private`'s own holder loop (recomputed here rather than
    read from its cache, since that cache answers the binary question only).
    Empty when `hash_` resolves nowhere — an unresolved citation is `check`'s
    dangle to flag, not this module's."""
    tiers: set[str] = set()
    for c in join.holders(hash_):
        tiers |= record_tiers(c.root, hash_, default=("private" if c.private else "public"),
                              declared=declared)
    return frozenset(tiers)


def evidence_entry_visible(
    entry: object, join: CorpusJoin, datasets: Mapping[str, Reference],
    grants: frozenset[str], *, declared: frozenset[str] | None = None,
) -> bool:
    """True iff one fact `sources` entry (`{record: <hash>}` or `{ref: …}`)
    is visible to grant set `grants` — its resolved record's tier set
    intersects `grants` (§6.4). A `ref://` entry's tiers are the resolved
    snapshot's mirror-artifact record's — the same lookup a bare `corpus://`
    citation gets, keyed through the dataset registry instead of a direct
    hash. A malformed entry, an unresolved citation (unregistered dataset,
    dangling snapshot tag, a hash that resolves nowhere), or a dangling pin
    answers True here — vacuously visible, contributing nothing either way;
    `check` flags the dangle itself, elsewhere."""
    if not isinstance(entry, dict):
        return True
    record = entry.get("record")
    if record is not None:
        h = str(record)
        if not (FULL_HASH_RE.match(h) and join.resolves(h)):
            return True
        return bool(_held_tiers(h, join, declared=declared) & grants)
    ref = entry.get("ref")
    if ref is not None:
        m = SOURCE_REF_RE.match(str(ref))
        if not m:
            return True
        dataset, tag, _id = m.group(1), m.group(2), m.group(3)
        reference = datasets.get(dataset)
        if reference is None:
            return True
        resolved_tag = tag if tag is not None else reference.latest
        snapshot = reference.snapshots.get(resolved_tag)
        if snapshot is None:
            return True
        h = snapshot.artifact
        if not join.resolves(h):
            return True
        return bool(_held_tiers(h, join, declared=declared) & grants)
    return True  # neither record nor ref — malformed, contributes nothing


def claim_visible(
    claim: dict, sources: Mapping[str, object], join: CorpusJoin,
    datasets: Mapping[str, Reference], grants: frozenset[str], *,
    declared: frozenset[str] | None = None,
) -> bool:
    """A claim is visible to `grants` iff every evidence entry it carries is
    visible to `grants` and it asserts no `sensitivity: private` (§6.4, the
    owner-only restriction — upward only, unconditional)."""
    if not isinstance(claim, dict):
        return True
    if claim.get("sensitivity") == "private":
        return False
    for e in claim.get("evidence") or []:
        if not isinstance(e, dict):
            continue
        skey = e.get("source")
        if not isinstance(skey, str):
            continue
        entry = sources.get(skey) if isinstance(sources, Mapping) else None
        if entry is not None and not evidence_entry_visible(
                entry, join, datasets, grants, declared=declared):
            return False
    return True


def fact_visible(
    fact: dict, join: CorpusJoin, datasets: Mapping[str, Reference],
    grants: frozenset[str], *, declared: frozenset[str] | None = None,
) -> bool:
    """A fact file is visible to `grants` iff any claim or roster entry it
    carries is visible to `grants` and the file asserts no `sensitivity:
    private` (§6.4) — existence itself can be the leak. A fact with no claims
    and no roster (a bare stub) carries nothing to derive visibility FROM, so
    it is never hidden by this rule alone."""
    if not isinstance(fact, dict):
        return True
    if fact.get("sensitivity") == "private":
        return False
    sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
    carried: list[bool] = []
    for c in fact.get("claims") or []:
        if isinstance(c, dict):
            carried.append(claim_visible(c, sources, join, datasets, grants,
                                         declared=declared))
    for entry in fact.get("artifacts") or []:
        if isinstance(entry, dict):
            m = _CORPUS_URI_HASH_RE.match(str(entry.get("uri", "")))
            if m and join.resolves(m.group(1)):
                carried.append(bool(_held_tiers(m.group(1), join, declared=declared)
                                    & grants))
            else:
                carried.append(True)  # no match, or unresolved — contributes nothing
    if not carried:
        return True
    return any(carried)


def evidence_entry_private(
    entry: object, join: CorpusJoin, datasets: Mapping[str, Reference], *,
    declared: frozenset[str] | None = None,
) -> bool:
    """Private-backed iff not visible to {public} (§6.4) — the binary
    specialization of `evidence_entry_visible`, kept for existing callers."""
    return not evidence_entry_visible(entry, join, datasets, _PUBLIC_GRANTS,
                                       declared=declared)


def claim_private_backed(
    claim: dict, sources: Mapping[str, object], join: CorpusJoin,
    datasets: Mapping[str, Reference], *, declared: frozenset[str] | None = None,
) -> bool:
    """A claim is private-backed iff it is not visible to {public} — it
    asserts `sensitivity: private`, or any of its evidence resolves privately
    (§6.4). The binary specialization of `claim_visible`."""
    return not claim_visible(claim, sources, join, datasets, _PUBLIC_GRANTS,
                             declared=declared)


def fact_is_private(
    fact: dict, join: CorpusJoin, datasets: Mapping[str, Reference], *,
    declared: frozenset[str] | None = None,
) -> bool:
    """A fact file is private iff it is not visible to {public} — every claim
    and roster entry it carries is private-backed, or it asserts
    `sensitivity: private` (§6.4). The binary specialization of
    `fact_visible`."""
    return not fact_visible(fact, join, datasets, _PUBLIC_GRANTS, declared=declared)
