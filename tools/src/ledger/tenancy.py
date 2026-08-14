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
from pathlib import Path

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
