"""Content-continuity between two records — the supersession safety check.

When a logical artifact is re-captured into a new, more-complete record — a Claude Code
session that grew by a few turns, `A → B` — its content-address changes (identity is the
blake3, spec §2), but the OLD content should survive intact inside the new capture.
`continuity(A, B)` PROVES that: every addressable unit of A is still present in B, either
byte-identical or as a prefix B extends (the append-only growth case). One check answers
both questions supersession asks:

- **"Does B supersede A?"** — keep the more complete version: B may retire A only when B
  contains all of A (`Continuity.contains_a`). A compacted / truncated re-capture that
  dropped content fails this and is NOT allowed to clobber the fuller copy.
- **"Is a citation of A still valid against B?"** — a ledger evidence `corpus://A?<addr>`
  may be rewritten to `corpus://B?<addr>` only when that address's content is preserved
  (`member_status`); a diverged address is reported, never silently rewritten.

Scope: the container (`zip-manifest`) shape sessions and archives take — compared by their
`path=<member>` embeds. Equal `transport` blake3 ⇒ preserved with zero I/O (the immutable
members: completed sub-agent transcripts, tool results); only a member whose hash differs
(the growing main transcript) is resolved and checked for byte-prefix containment. A record
with no such embeds is compared by whole-artifact identity (its id IS the artifact blake3,
so continuity holds iff `A == B`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from . import mime, paths, records, ziparchive
from .containment import ArtifactMissing, ensure_local_bytes

log = logging.getLogger("corpus.continuity")

# Member-continuity verdicts.
IDENTICAL = "identical"  # same transport blake3 — preserved, no I/O
CONTAINED = "contained"  # A's bytes are a prefix of B's (append-only growth) — preserved
DIVERGED = "diverged"  # present in B but neither identical nor a prefix — content changed
ABSENT = "absent"  # the address exists in A but not in B — dropped

_PRESERVED = frozenset({IDENTICAL, CONTAINED})


@dataclass(frozen=True)
class MemberStatus:
    """One addressable unit of A and how it fared in B."""

    address: str  # the embed address, e.g. `path=<rel>` (or `` for a whole-artifact record)
    status: str  # IDENTICAL | CONTAINED | DIVERGED | ABSENT


@dataclass
class Continuity:
    """The result of comparing record A's addressable content against record B."""

    a: str
    b: str
    members: list[MemberStatus] = field(default_factory=list)

    @property
    def contains_a(self) -> bool:
        """True iff every addressable unit of A is preserved in B (identical or contained).
        The green light for `B supersedes A` and for rewriting citations of A to B."""
        return bool(self.members) and all(m.status in _PRESERVED for m in self.members)

    @property
    def diverged(self) -> list[MemberStatus]:
        """The addresses whose content did NOT survive into B — the citations a rewrite must
        leave alone and report."""
        return [m for m in self.members if m.status not in _PRESERVED]

    def status_for(self, address: str) -> str:
        """The verdict for one `path=<rel>` address (ABSENT if A never carried it)."""
        for m in self.members:
            if m.address == address:
                return m.status
        return ABSENT


def _embed_map(post) -> dict[str, str]:
    """`{address: transport}` for a record's `path=`-addressed embeds. A list-valued address
    (rare — a member reachable by more than one rendered path) contributes each path."""
    out: dict[str, str] = {}
    for e in records.iter_embed_blocks(post):
        transport = str(e.get("transport") or "")
        addr = e.get("address")
        addrs = addr if isinstance(addr, list) else [addr]
        for a in addrs:
            a = str(a or "").strip()
            if a.startswith("path=") and transport:
                out[a] = transport
    return out


def continuity(corpus_root: Path, a_id: str, b_id: str) -> Continuity:
    """Prove whether record B preserves all of record A's addressable content.

    `a_id` / `b_id` are full record ids (64-hex blake3). Loads both records, compares their
    `path=` embeds, and — only for a member whose transport hash differs — resolves the two
    members' bytes to test byte-prefix containment. Records with no `path=` embeds fall back
    to whole-artifact identity (`a_id == b_id`)."""
    result = Continuity(a=a_id, b=b_id)
    if a_id == b_id:
        result.members.append(MemberStatus("", IDENTICAL))
        return result

    post_a = records.load(paths.record_path(corpus_root, a_id))
    post_b = records.load(paths.record_path(corpus_root, b_id))
    map_a = _embed_map(post_a)
    map_b = _embed_map(post_b)

    if not map_a:
        # A is not a container manifest — its whole-artifact identity is its id, which
        # already differs from B (checked above), so nothing of A is preserved.
        result.members.append(MemberStatus("", DIVERGED))
        return result

    ext_a = mime.extension_for(records.media_type_for(post_a))
    ext_b = mime.extension_for(records.media_type_for(post_b))
    for address, transport_a in map_a.items():
        transport_b = map_b.get(address)
        if transport_b is None:
            result.members.append(MemberStatus(address, ABSENT))
            continue
        if transport_b == transport_a:
            result.members.append(MemberStatus(address, IDENTICAL))
            continue
        # Hash differs — the one member that grows. Resolve both and test prefix containment.
        rel = address[len("path=") :]
        status = _prefix_status(corpus_root, a_id, ext_a, b_id, ext_b, rel)
        result.members.append(MemberStatus(address, status))
    return result


def _prefix_status(
    corpus_root: Path, a_id: str, ext_a: str, b_id: str, ext_b: str, rel: str
) -> str:
    """CONTAINED iff A's member bytes are a prefix of B's; else DIVERGED. Any resolution
    failure is conservatively DIVERGED — continuity is never claimed for content we could
    not read."""
    try:
        zip_a = ensure_local_bytes(corpus_root, a_id, ext_a)
        zip_b = ensure_local_bytes(corpus_root, b_id, ext_b)
        bytes_a = ziparchive.resolve_member(zip_a, rel)
        bytes_b = ziparchive.resolve_member(zip_b, rel)
    except (ArtifactMissing, KeyError, ValueError, OSError, RuntimeError) as e:
        log.debug("continuity: could not resolve member %r for prefix check: %s", rel, e)
        return DIVERGED
    return CONTAINED if bytes_b.startswith(bytes_a) else DIVERGED
