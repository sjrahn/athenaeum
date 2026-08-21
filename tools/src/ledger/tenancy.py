"""Record tenancy — the §6.4 *(1.9)* sensitivity input, derived per record.

A record's tenancy is **public** iff any of its origins says so: an origin
whose overlay declares `tenancy: public` (deployment metadata the ledger reads
schema-first — the corpus itself never consumes it), or an origin whose
`corpus://` lineage reaches a public record (a promoted member takes its
container's tenancy, chased transitively). A record whose origins declare
nothing falls closed to the holding corpus's manifest `visibility:` — the
`default` the caller passes. Any-public-wins, because demonstrably-public
bytes cannot be made private by an additional private capture.

Everything here is a read-only library call into the corpus package (ledger
depends on corpus — never a re-implementation), tolerant by contract: an
unreadable record, a malformed origin, or a missing overlay contributes
nothing, and the fail-closed default carries the answer.
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


def _origin_uris(origin: dict) -> list[str]:
    fields = origin.get("fields") if isinstance(origin.get("fields"), dict) else {}
    uri = fields.get("uri")
    if isinstance(uri, list):
        return [u for u in uri if isinstance(u, str)]
    return [uri] if isinstance(uri, str) else []


def record_tenancy(
    corpus_root: Path,
    hash_: str,
    *,
    default: str = "private",
    _seen: set[str] | None = None,
) -> str:
    """``"public"`` or ``"private"`` for the record at `hash_` in `corpus_root`.

    `default` is the holding corpus's manifest visibility — the fail-closed
    floor for records whose origins declare nothing (§6.4). Lineage recursion
    carries the same default: a member chain that never meets a declaration
    lands on the floor, exactly like a standalone undeclared record.
    """
    seen = _seen if _seen is not None else set()
    if hash_ in seen or len(seen) > _MAX_LINEAGE_HOPS:
        return default
    seen.add(hash_)

    from corpus import paths, records  # heavy import, deferred
    from corpus.schemas import load_origin_overlay_by_id

    try:
        post = records.load(paths.record_path(corpus_root, hash_))
    except Exception:  # tolerant by contract: unreadable → the floor answers
        return default

    declared: list[str] = []
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
                if tenancy in ("public", "private"):
                    declared.append(tenancy)
                    break
        for u in _origin_uris(origin):
            m = _CORPUS_URI_HASH_RE.match(u)
            if m:
                lineage_parents.append(m.group(1))

    if "public" in declared:
        return "public"
    for parent in lineage_parents:
        if record_tenancy(corpus_root, parent, default=default, _seen=seen) == "public":
            return "public"
    if declared:  # every declaration reached said private — an answer, not the floor
        return "private"
    return default


# --------------------------------------------------------------- claim/fact §6.4
#
# Shared by `ledger.check` (the validation counts) and the read surface
# (`ath.serve`, spec Part I §5.1) — the ONE place a claim's/fact's derived
# sensitivity computes, so a consumer's publication filter and `ath ledger
# check`'s note never disagree. Tolerant throughout: a malformed sources
# entry or an unresolvable citation contributes nothing (dangling citations
# are `check`'s to flag, not this module's) — never raises on ordinary
# ledger data.


def evidence_entry_private(
    entry: object, join: CorpusJoin, datasets: Mapping[str, Reference],
) -> bool:
    """True iff one fact `sources` entry (`{record: <hash>}` or `{ref: …}`)
    resolves privately (§6.4). A `ref://` entry's sensitivity is the tenancy
    of the resolved snapshot's mirror-artifact record — the same lookup a
    bare `corpus://` citation gets, keyed through the dataset registry
    instead of a direct hash. An unresolved citation (unregistered dataset,
    dangling snapshot tag, a hash that resolves nowhere) answers False here —
    it contributes nothing to privacy, exactly as an unresolved `record`
    citation always has; `check` flags the dangle itself, elsewhere."""
    if not isinstance(entry, dict):
        return False
    record = entry.get("record")
    if record is not None:
        h = str(record)
        return bool(FULL_HASH_RE.match(h) and join.resolves(h) and join.is_private(h))
    ref = entry.get("ref")
    if ref is not None:
        m = SOURCE_REF_RE.match(str(ref))
        if not m:
            return False
        dataset, tag, _id = m.group(1), m.group(2), m.group(3)
        reference = datasets.get(dataset)
        if reference is None:
            return False
        resolved_tag = tag if tag is not None else reference.latest
        snapshot = reference.snapshots.get(resolved_tag)
        if snapshot is None:
            return False
        h = snapshot.artifact
        return bool(join.resolves(h) and join.is_private(h))
    return False


def claim_private_backed(
    claim: dict, sources: Mapping[str, object], join: CorpusJoin,
    datasets: Mapping[str, Reference],
) -> bool:
    """A claim is private-backed iff it asserts `sensitivity: private` or any
    of its evidence resolves privately (§6.4, "A claim is private-backed iff
    any of its evidence is private, or it asserts sensitivity: private")."""
    if not isinstance(claim, dict):
        return False
    if claim.get("sensitivity") == "private":
        return True
    for e in claim.get("evidence") or []:
        if not isinstance(e, dict):
            continue
        skey = e.get("source")
        if not isinstance(skey, str):
            continue
        entry = sources.get(skey) if isinstance(sources, Mapping) else None
        if entry is not None and evidence_entry_private(entry, join, datasets):
            return True
    return False


def fact_is_private(
    fact: dict, join: CorpusJoin, datasets: Mapping[str, Reference],
) -> bool:
    """A fact file is private iff every claim and roster entry it carries is
    private-backed, or it asserts `sensitivity: private` (§6.4) — existence
    itself can be the leak. A fact with no claims and no roster (a bare stub)
    carries nothing to derive privacy FROM, so it is never private by this
    rule alone (mirrors `carried and all(carried)`: an empty `carried` is
    falsy)."""
    if not isinstance(fact, dict):
        return False
    if fact.get("sensitivity") == "private":
        return True
    sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
    carried: list[bool] = []
    for c in fact.get("claims") or []:
        if isinstance(c, dict):
            carried.append(claim_private_backed(c, sources, join, datasets))
    for entry in fact.get("artifacts") or []:
        if isinstance(entry, dict):
            m = _CORPUS_URI_HASH_RE.match(str(entry.get("uri", "")))
            carried.append(bool(m and join.is_private(m.group(1))))
    return bool(carried) and all(carried)
