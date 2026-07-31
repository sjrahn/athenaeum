"""Containment resolution — the member index + the store fallback (spec §2, §12.9).

An artifact's `id` need not resolve to a *standalone* file. When a container's record declares
a member as a content-addressed embed, that member's bytes are retrievable by their own blake3
**through the container**: the implementation streams them out via the container's address
scheme, recursively when containers nest (spec §2). The route from a bare blake3 to its
container is a **derived** map — `member transport hash → [(container id, member address), …]`
— built by walking every record's embed blocks, exactly as `records.build_uri_index` is built
(one pass, rebuilt-on-start, in-memory; §12.9). It is NEVER stored on the promoted record, so
bytes may move between standalone residence and containment without any record changing.

`ensure_local_bytes` is the containment-aware replacement for a bare `store.ensure_local`: it
returns a standalone file when one exists (residence wins whenever present), else materializes
the member's bytes through its container into the resolver cache (`cache/`), streaming so a
multi-GB member never loads whole, and recursing through nested containers with a cycle guard.
A promoted record's origin `uri:` (its containment lineage, §8.1) is history — **never**
consulted for byte lookup; the member index is the only route.
"""

from __future__ import annotations

import io
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

import frontmatter

from . import functional_uri as furi
from . import mime as mime_mod
from . import paths, records, tararchive, ziparchive
from .store import ArtifactMissing, ArtifactStore, get_store

_CHUNK = 1 << 20

# ISOBMFF media-container types whose members are addressed `stream_id=<n>` (spec §1.2,
# §12.20 item 4) — the track axis, dispatched to `corpus.mux.mux_stream`
# below. Matroska/WebM (EBML) is out of scope for this increment (`corpus.streams` itself
# refuses non-ISOBMFF containers, §12.20.1's deferred item).
_ISOBMFF_STREAM_CONTAINERS = frozenset({"video/mp4", "video/quicktime", "audio/mp4"})


class _IteratorReader(io.RawIOBase):
    """A read-only raw stream over an iterator of byte chunks — lets a chunked producer (here,
    `mux.mux_stream`) flow through `read()` without ever holding the whole track. The
    same adapter shape as `mboxfile._MemberReader`; wrapped in a `BufferedReader` by the caller
    for exact-length reads."""

    def __init__(self, chunks: Iterator[bytes]) -> None:
        self._chunks = chunks
        self._buf = b""
        self._eof = False

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:  # type: ignore[override]
        want = len(b)
        while len(self._buf) < want and not self._eof:
            try:
                self._buf += next(self._chunks)
            except StopIteration:
                self._eof = True
        n = min(want, len(self._buf))
        b[:n] = self._buf[:n]
        self._buf = self._buf[n:]
        return n


# ---------- the member index ---------- #


def member_hashes(post: frontmatter.Post) -> Iterator[str]:
    """Yield the bare-hex blake3 of every member (embed) `post` declares. Embed `transport:`
    is `<algo>:<hex>` (§7.6); only blake3 entries — the corpus identity algorithm — index."""
    for embed in records.iter_embed_blocks(post):
        transport = str(embed.get("transport") or "")
        algo, _, hexval = transport.partition(":")
        if algo == "blake3" and hexval:
            yield hexval


def build_member_index(corpus_root: Path) -> dict[str, list[tuple[str, str]]]:
    """Map member blake3 (bare hex) → `[(container id, member address), …]` over every
    record's embed blocks. One pass over `records/` via `load_all`, the derived-and-cached
    complement to the URI index (§12.9). A member deduped across several positions keeps its
    first address (every position yields identical bytes by construction, §2)."""
    index: dict[str, list[tuple[str, str]]] = {}
    for md, post in records.load_all(corpus_root):
        container_id = str(post.metadata.get("id") or md.stem)
        for embed in records.iter_embed_blocks(post):
            transport = str(embed.get("transport") or "")
            algo, _, hexval = transport.partition(":")
            if algo != "blake3" or not hexval:
                continue
            address = embed.get("address")
            addr = address[0] if isinstance(address, list) else address
            # A self-referential row — a single-member container whose one member IS the
            # whole artifact (transport == own id; the attested roster derives it honestly,
            # e.g. a promoted single-card vCard's `card=1`) — is an identity statement, not
            # a route: resolving through it would require the very bytes being sought
            # (#145's containment cycle).
            if addr and hexval != container_id:
                index.setdefault(hexval, []).append((container_id, str(addr)))
    return index


# ---------- member streaming (dispatch by container family) ---------- #


def _archive_family(media_type: str) -> str | None:
    """The archive family that materializes a `path=<relpath>` member — `zip` (raw zip and any
    `+zip` structured container) or `tar` (`.tar`/`.tgz`, gzip auto-detected), or None."""
    if media_type == "application/zip" or media_type.endswith("+zip"):
        return "zip"
    if media_type == "application/x-tar":
        return "tar"
    return None


@contextmanager
def open_member_stream(
    container_path: Path,
    container_media_type: str,
    address: str,
    *,
    el_addressing: dict | None = None,
) -> Iterator[IO[bytes]]:
    """Stream a container member's bytes (spec §12.9), dispatching on the container's media
    type. Yields a binary file-like for the life of the `with`; raises `ValueError` for an
    address scheme / container type this can't materialize.

    `el_addressing` is the CONTAINER record's attested `addressing:` stamp (§7.1) — required
    for an `el=` member, since the stamp's presence is what dispatches the address between the
    3.6 path space and the frozen legacy index (§6.1.1). Ignored by every other family."""
    key, _, value = str(address).partition("=")
    # *(3.8)* An HTML page is a container whose members are the assets its bytes inline —
    # addressed `el=<path>` at the carrier element (§4.3.1.4, §12.30). This is the family
    # promotion could not reach, and it holds 9,109 of the placed members across both hubs.
    # The bytes are the carrier's base64 `data:` payload decoded, which is exactly what
    # attestation hashed into the roster row — so it round-trips to the declared blake3.
    # Bounded by construction (a data URI is already resident in the parsed document), hence
    # a BytesIO rather than a stream, like the eml/vcard members.
    if container_media_type == "text/html" and key == "el":
        from .transforms import html as html_tf

        yield io.BytesIO(
            html_tf.el_member_bytes(container_path, value, el_addressing=el_addressing)[1]
        )
        return
    # An mbox is a container whose members are addressed `msg=<N>` (spec §12.11) — a
    # streaming scan yields the un-stuffed message bytes, never loading the mailbox whole.
    if container_media_type == "application/mbox" and key == "msg":
        from . import mboxfile

        try:
            ordinal = int(value)
        except ValueError as exc:
            raise ValueError(f"mbox member {address!r}: msg= needs an integer ordinal") from exc
        with mboxfile.open_member(container_path, ordinal) as fp:
            yield fp
        return
    # A vCard file is a container whose members are addressed `card=<N>` (spec §12.11, §12.18
    # step 4) — one card's exact `BEGIN:VCARD`/`END:VCARD` byte span. A `.vcf` is small and a
    # card bounded, so this yields a BytesIO over the extracted span rather than a stream.
    if container_media_type == "text/vcard" and key == "card":
        from . import vcardfile

        try:
            ordinal = int(value)
        except ValueError as exc:
            raise ValueError(f"vcard member {address!r}: card= needs an integer ordinal") from exc
        yield io.BytesIO(vcardfile.resolve_member(container_path, ordinal))
        return
    # A media container's track, addressed `stream_id=<N>` (spec §1.2, §12.20 item 4) — the
    # pinned identity bytes via `corpus.mux.mux_stream`: a single-track container of the
    # source's own family (3.12), streamed chunk by chunk through the `_IteratorReader`
    # adapter so a large track is never held whole. ISOBMFF only (`corpus.streams` refuses
    # Matroska/WebM with a clear error, which propagates here unchanged rather than being
    # swallowed into the generic "cannot stream member" message).
    if container_media_type in _ISOBMFF_STREAM_CONTAINERS and key == "stream_id":
        from . import mux

        try:
            ordinal = int(value)
        except ValueError as exc:
            raise ValueError(
                f"track member {address!r}: stream_id= needs an integer track index"
            ) from exc
        yield io.BufferedReader(_IteratorReader(mux.mux_stream(container_path, ordinal)))
        return
    # An email is a container whose members are addressed `part=<N>` (spec §12.11) — the
    # decoded MIME part's bytes. A single message is bounded (parsed whole), so this yields a
    # BytesIO rather than a scan; the mailbox it may itself live in is the unbounded thing.
    if container_media_type == "message/rfc822" and key == "part":
        from . import emlfile

        try:
            ordinal = int(value)
        except ValueError as exc:
            raise ValueError(f"eml member {address!r}: part= needs an integer ordinal") from exc
        data = emlfile.resolve_part(container_path.read_bytes(), ordinal)
        yield io.BytesIO(data)
        return
    family = _archive_family(container_media_type)
    if key != "path" or family is None:
        raise ValueError(
            f"cannot stream member {address!r} from a {container_media_type!r} container"
        )
    opener = ziparchive.open_member if family == "zip" else tararchive.open_member
    with opener(container_path, value) as fp:
        yield fp


def member_source_metadata(
    container_path: Path,
    container_media_type: str,
    address: str,
    *,
    el_addressing: dict | None = None,
) -> dict[str, str]:
    """The member's durable provenance for a promoted record's origin block (spec §7.2, §8.1):
    `filename` (member basename) and, when the archive records it, `source_modified` (mtime)."""
    key, _, value = str(address).partition("=")
    # *(3.8)* An asset inlined in an HTML page has no mtime — its `el=` path is a position in
    # a document tree, exactly like `msg=`/`card=`/`stream_id=`. It may still name itself: an
    # attachment link renders `Click to download <name> (<size>)`, and that name is a byte-fact
    # worth keeping — and is also the sniff hint that refines a zip-magic member within its
    # family (a docx inlined as `data:` sniffs as bare `application/zip` without it).
    if container_media_type == "text/html" and key == "el":
        from .transforms import html as html_tf

        name = html_tf.el_member_filename(container_path, value, el_addressing=el_addressing)
        return {"filename": name} if name else {}
    # An mbox message has no member filename and no meaningful per-member mtime (its ordinal
    # is a position, not a name) — a promoted message's origin carries the lineage uri only.
    if container_media_type == "application/mbox" and key == "msg":
        return {}
    # A vCard card, likewise: its `card=<N>` ordinal is a position, not a filename — a promoted
    # card's origin carries the containment-lineage uri only (spec §8.1).
    if container_media_type == "text/vcard" and key == "card":
        return {}
    # A media-container track, likewise: `stream_id=<N>` is a position (moov `trak` order), not
    # a filename or a meaningful mtime — a promoted track's origin carries the containment-
    # lineage uri only (spec §8.1, §12.20 item 3).
    if container_media_type in _ISOBMFF_STREAM_CONTAINERS and key == "stream_id":
        return {}
    # An email part carries its declared filename (e.g. a promoted `contract.pdf`) when it
    # names itself; no meaningful mtime.
    if container_media_type == "message/rfc822" and key == "part":
        from . import emlfile

        try:
            ordinal = int(value)
        except ValueError:
            return {}
        filename = emlfile.part_filename(container_path.read_bytes(), ordinal)
        return {"filename": filename} if filename else {}
    meta: dict[str, str] = {"filename": value.rsplit("/", 1)[-1]}
    family = _archive_family(container_media_type)
    if key == "path" and family:
        mtime_fn = (
            ziparchive.member_source_modified
            if family == "zip"
            else tararchive.member_source_modified
        )
        mtime = mtime_fn(container_path, value)
        if mtime:
            meta["source_modified"] = mtime
    return meta


# ---------- the store fallback ---------- #


def ensure_local_bytes(
    corpus_root: Path,
    record_id: str,
    ext: str,
    *,
    store: ArtifactStore | None = None,
    member_index: dict[str, list[tuple[str, str]]] | None = None,
    _seen: frozenset[str] | None = None,
) -> Path:
    """Return a local path to `record_id`'s bytes — the containment-aware replacement for a
    bare `store.ensure_local` (spec §2, §12.9). A standalone file (local, or hydrated from a
    remote store) wins whenever it exists; otherwise the bytes are materialized through the
    record's container into the resolver cache, streaming (no whole-member load) and recursing
    when the container is itself promoted. Raises `ArtifactMissing` when unresolvable by any
    route."""
    store = store or get_store(corpus_root)
    _seen = _seen if _seen is not None else frozenset()
    if record_id in _seen:
        raise ArtifactMissing(
            f"containment cycle resolving {record_id} (revisited via {sorted(_seen)})"
        )

    # Standalone residence wins whenever it exists (§2) — local first, then remote hydration.
    if store.is_local(record_id, ext):
        return store.local_path(record_id, ext)
    try:
        return store.ensure_local(record_id, ext)
    except ArtifactMissing:
        pass

    # No standalone file — resolve through the container. The member index is the ONLY route
    # (the promoted record's origin uri: is history, never consulted for lookup, §12.9).
    idx = member_index if member_index is not None else build_member_index(corpus_root)
    # Several routes may exist at once and every route yields identical bytes (§2) — "a
    # resolver may take any", so take the first VIABLE one: a route through a container
    # already on the resolution path (or through the record itself) is not a route at all.
    all_routes = idx.get(record_id) or []
    routes = [
        (cid, addr) for cid, addr in all_routes if cid != record_id and cid not in _seen
    ]
    if not routes:
        if all_routes:
            # Routes existed but every one led back into the resolution path — a genuine
            # declared cycle (or pure self-reference). Say so; "not resolvable" would bury
            # the pathology.
            raise ArtifactMissing(
                f"containment cycle resolving {record_id} "
                f"(all routes revisit {sorted({cid for cid, _ in all_routes})})"
            )
        raise ArtifactMissing(
            f"artifact {record_id} has no standalone file and is not resolvable through any "
            f"container (spec §2/§12.9)."
        )
    container_id, address = routes[0]
    container_post = _load_container(corpus_root, container_id)
    container_media_type = records.media_type_for(container_post)
    container_ext = mime_mod.extension_for(container_media_type)
    # Recurse: a promoted member may itself be a container (bounded by the cycle guard).
    container_path = ensure_local_bytes(
        corpus_root,
        container_id,
        container_ext,
        store=store,
        member_index=idx,
        _seen=_seen | {record_id},
    )
    return _materialize_member(
        corpus_root,
        record_id,
        ext,
        container_path,
        container_media_type,
        address,
        el_addressing=records.el_addressing(container_post),
    )


def _load_container(corpus_root: Path, container_id: str) -> frontmatter.Post:
    record_file = paths.record_path(corpus_root, container_id)
    if not record_file.is_file():
        raise ArtifactMissing(
            f"container record {container_id} is missing — its member index route is stale."
        )
    return records.load(record_file)


def _member_cache_path(corpus_root: Path, record_id: str, ext: str) -> Path:
    """The resolver-cache path for a promoted record's materialized bytes — keyed by the bare
    `corpus://<id>` urihash so a repeat lookup hits the cache and `gc` reclaims it by age."""
    return furi.cache_path(corpus_root, furi.urihash(f"{furi.SCHEME}://{record_id}"), ext)


def _materialize_member(
    corpus_root: Path,
    record_id: str,
    ext: str,
    container_path: Path,
    container_media_type: str,
    address: str,
    *,
    el_addressing: dict | None = None,
) -> Path:
    """Stream the member out of its container into the resolver cache and return that path.
    Content-addressed bytes are immutable, so a warm cache file is authoritative (§12.9)."""
    cache_p = _member_cache_path(corpus_root, record_id, ext)
    if cache_p.is_file():
        return cache_p
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_p.with_name(f"{cache_p.name}.tmp.{os.getpid()}")
    try:
        with open_member_stream(
            container_path, container_media_type, address, el_addressing=el_addressing
        ) as fp, tmp.open("wb") as out:
            shutil.copyfileobj(fp, out, _CHUNK)
        os.replace(tmp, cache_p)
    finally:
        tmp.unlink(missing_ok=True)
    return cache_p
