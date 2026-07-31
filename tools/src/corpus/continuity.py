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

from . import mime, paths, records, streams, ziparchive
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
        # *(3.12)* Before falling back to id comparison, try the MEDIA question. A re-framed
        # member — a track lifted out of its container under a changed pinned form — has
        # different bytes by construction, so an id comparison can only ever say DIVERGED
        # and would report a fully-sound supersession as unsafe. See `_media_continuity`.
        media = _media_continuity(corpus_root, post_a, a_id, post_b, b_id)
        if media is not None:
            result.members.extend(media)
            return result
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


def _media_continuity(
    corpus_root: Path, post_a, a_id: str, post_b, b_id: str
) -> list[MemberStatus] | None:
    """*(3.12)* Continuity between two ISOBMFF media records, by **sample sequence**.

    Returns None when this is not a media pair — the caller then falls back to whole-artifact
    identity as before.

    **Why byte containment is the wrong question here.** A record's identity is its artifact's
    blake3, so a track re-framed under a changed pinned form (3.12: elementary stream → a
    single-track container of the same family) has a different id *by construction*. Comparing
    ids reports DIVERGED for a supersession that is in fact exact, which is worse than no gate:
    a check that is always red gets ignored. §12.37 names continuity-gated supersession as the
    net for exactly this case, and until now it could not be one.

    **The invariant underneath the envelope is the sample sequence.** Re-enveloping moves every
    sample's file offset and changes none of their sizes, so `streams.sample_sizes` — engine-free,
    sample-tables only — is preserved exactly across a reframe and broken by a re-encode, a
    dropped or reordered sample, or a differently-framed payload. `CONTAINED` keeps its usual
    meaning: A's sequence is a prefix of B's, the append-only growth case.

    **Which tracks to compare** is decided by lineage, never by position, because a leaf's own
    track 0 may be its container's track 1 and comparing them by index would silently check the
    wrong pair:

    - B carries containment lineage into A (`corpus://<a_id>?stream_id=N`) — B is a promotion of
      A's track N, so compare A's track N against B's only track. This is the post-sweep check
      #133 wants and the retroactive proof the 3.12 pilot never got.
    - Otherwise both are compared track-for-track by index, which is sound when neither is a
      member of the other (two captures of the same recording, or two framings of one leaf).
      A track-count mismatch is reported rather than paired off.
    """
    ext_a = mime.extension_for(records.media_type_for(post_a))
    ext_b = mime.extension_for(records.media_type_for(post_b))
    try:
        path_a = ensure_local_bytes(corpus_root, a_id, ext_a)
        path_b = ensure_local_bytes(corpus_root, b_id, ext_b)
        tracks_a = streams.probe_streams(path_a)
        tracks_b = streams.probe_streams(path_b)
    except (ArtifactMissing, ValueError, NotImplementedError, OSError, RuntimeError) as e:
        log.debug("continuity: not a readable media pair (%s / %s): %s", a_id[:12], b_id[:12], e)
        return None
    if not tracks_a or not tracks_b:
        return None

    pairs = _track_pairs(post_b, a_id, tracks_a, tracks_b)
    out: list[MemberStatus] = []
    for address, idx_a, idx_b in pairs:
        if idx_b is None:
            out.append(MemberStatus(address, ABSENT))
            continue
        try:
            seq_a = streams.sample_sizes(path_a, idx_a)
            seq_b = streams.sample_sizes(path_b, idx_b)
        except (ValueError, NotImplementedError, OSError) as e:
            # Unreadable is never "preserved" — continuity is not claimed for what we could
            # not check, exactly as the byte path treats a resolution failure.
            log.debug("continuity: sample sequence unreadable for %s: %s", address, e)
            out.append(MemberStatus(address, DIVERGED))
            continue
        if seq_a == seq_b:
            out.append(MemberStatus(address, IDENTICAL))
        elif len(seq_b) > len(seq_a) and seq_b[: len(seq_a)] == seq_a:
            out.append(MemberStatus(address, CONTAINED))
        else:
            out.append(MemberStatus(address, DIVERGED))
    return out or None


def _track_pairs(
    post_b, a_id: str, tracks_a: list, tracks_b: list
) -> list[tuple[str, int, int | None]]:
    """`(address, a_track_index, b_track_index)` for each of A's tracks — lineage first."""
    for uri in records.iter_origin_uris(post_b):
        if not uri.startswith(f"corpus://{a_id}?"):
            continue
        _, _, query = uri.partition("?")
        for part in query.split("&"):
            if part.startswith("stream_id="):
                try:
                    n = int(part[len("stream_id=") :])
                except ValueError:
                    continue
                # B is A's track n, promoted. B holds exactly one track, so its own index is
                # whatever that single track calls itself — read it rather than assuming 0.
                if len(tracks_b) == 1 and any(t.index == n for t in tracks_a):
                    return [(f"stream_id={n}", n, tracks_b[0].index)]
    return [
        (
            f"stream_id={t.index}",
            t.index,
            next((u.index for u in tracks_b if u.index == t.index), None),
        )
        for t in tracks_a
    ]


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
