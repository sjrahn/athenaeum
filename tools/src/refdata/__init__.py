"""The reference-dataset resolver (spec/ledger.md §6.5) — "resolution is
downward": `(dataset, tag)` -> the snapshot's mirror-artifact blake3 ->
bytes materialized on local disk -> the dataset's adapter renders the
requested entry (title, plain text, content type) for quote verification.

Three entry points:

- `materialize(reference, tag, corpora_roots)` — the snapshot's bytes on
  local disk, or None. Tries the snapshot's declared `path:` override first
  *(v18, DEPRECATED v21, spec/athenaeum.md §2.3)* — read tolerantly, since
  not every registered snapshot has migrated off it yet — then, per given
  corpus root, the artifact store (`artifacts/<shard>/`) and *(21)* the
  attached-location route (`corpus.locationindex.route_for`, spec/corpus.md
  §12.1.1), the `path:` override's successor. A declared-but-absent `path:`
  is simply a miss, not an error — it falls through to the corpus routes.
- `resolve_adapter_name(reference, corpora_roots)` — *(21)* the format
  adapter name for `reference`: an explicit `reference.adapter` wins; else
  it's derived from the latest snapshot's mirror record's mime overlay
  `ref_adapter` (spec/corpus.md §7.1). Raises `AdapterUnavailable` naming
  exactly what link in that chain is missing.
- `resolve(reference, native_id, tag, corpora_roots)` — the full resolution:
  tag -> snapshot -> materialize -> adapter -> `ResolvedEntry`. Raises the
  typed `errors.RefdataError` hierarchy on any failure a caller needs to
  branch on (§6.5: content resolution absent is *unverifiable*, never a
  crash — callers catch these and report accordingly, they are not meant to
  propagate to a user-facing traceback).
- `search(reference, query, tag, corpora_roots, limit, mode)` — the discovery
  step ahead of `resolve`: ids aren't guessable, so a scribe searches a
  dataset by words first and pastes a hit's `native_id` into `resolve` (or
  straight into a `ref://` citation). Same tag/adapter/mirror preamble and
  typed errors as `resolve`; an empty result list is a normal answer (no
  hits, or the mirror carries no index for the requested tier), never one of
  those errors. `mode` (default `"blend"`) picks title-index hits, full-text
  hits, or both blended together — see `adapters.search_entries`'s
  docstring for the tier semantics; an unrecognized mode is `ValueError`.

A mirror whose bytes exist but fail to open as the adapter's format
(truncated mid-download, or corrupted) surfaces as `MirrorCorrupt` from both
`resolve` and `search` — distinct from `MirrorUnavailable` (no bytes at
all), but the same honestly-unverifiable-never-a-crash contract every other
`RefdataError` subclass carries.

Archive handles are expensive to open and verification resolves many
entries against one snapshot, so open handles are cached per absolute
mirror path, process-lifetime (no TTL — a corpus artifact's bytes are
content-addressed and immutable, so a cached handle never goes stale).

Some formats (e.g. `osm-pbf`) need a one-time sidecar index before they can
resolve or search at all — absent or stale, that adapter raises
`MirrorUnindexed`, joining the same honestly-unverifiable-never-a-crash
`RefdataError` hierarchy as every other resolution failure here. *(21)* The
sidecar's canonical home is cache-mold derived state under the resolving
corpus root's `cache/refidx/<artifact>.sqlite` (`canonical_index_path`),
never beside a mirror that may not even be locally writable (an attached
location can be read-only) — `_resolve_handle` computes it and threads it
through `open_archive`; a legacy beside-the-mirror sidecar (pre-21) is still
honored as migration grace when the canonical path carries none yet.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ath.manifest import Reference, Snapshot
from corpus import locationindex as corpus_locationindex
from corpus import paths as corpus_paths
from corpus import records as corpus_records
from corpus import schemas as corpus_schemas

from .adapters import ADAPTERS, AdapterResult, adapter_available
from .errors import (
    AdapterUnavailable,
    EntryNotFound,
    MirrorCorrupt,
    MirrorUnavailable,
    MirrorUnindexed,
    RefdataError,
    UnknownTag,
)

__all__ = [
    "ADAPTERS",
    "AdapterResult",
    "AdapterUnavailable",
    "EntryNotFound",
    "MirrorCorrupt",
    "MirrorUnavailable",
    "MirrorUnindexed",
    "RefdataError",
    "ResolvedEntry",
    "SearchHit",
    "UnknownTag",
    "adapter_available",
    "canonical_index_path",
    "materialize",
    "resolve",
    "resolve_adapter_name",
    "search",
]


@dataclass(frozen=True)
class ResolvedEntry:
    """One `ref://{dataset}[@{tag}]/{native_id}` citation, resolved."""

    dataset: str
    tag: str
    artifact: str  # the resolved snapshot's mirror-artifact blake3 (§13.2 stamp)
    native_id: str  # as requested
    canonical_id: str  # post-redirect entry path; == native_id when no redirect
    title: str | None
    text: str | None  # plain-text rendering for quote matching; None if no text projection
    content_type: str | None


@dataclass(frozen=True)
class SearchHit:
    """One `search()` hit — a native id ready to paste into `resolve` or a
    `ref://{dataset}[@{tag}]/{id}` citation, plus a display title and an
    optional short `context` hint for disambiguating same-titled hits."""

    native_id: str
    title: str | None
    context: str | None = None


def materialize(
    reference: Reference, tag: str, corpora_roots: Sequence[Path] = ()
) -> Path | None:
    """The bytes of `reference`'s `tag` snapshot on local disk, or None if
    nowhere materialized (§6.5 "Resolution is downward"). An unregistered
    `tag` is itself a miss — this function reports presence, not
    registration; `resolve()` is where an unknown tag is a typed error."""
    path, _ = _materialize_with_root(reference, tag, corpora_roots)
    return path


def _materialize_with_root(
    reference: Reference, tag: str, corpora_roots: Sequence[Path]
) -> tuple[Path | None, Path | None]:
    """`materialize()`'s implementation — also reports *which* given corpus
    root (if any) the bytes resolved through, feeding `canonical_index_path`
    below. `None` for the root half means either the deprecated `path:`
    override served the bytes, or nothing resolved at all.

    Per corpus root, tries — in order — the co-located artifact store
    (`artifacts/<shard>/`) then *(21)* the attached-location route
    (`corpus.locationindex.route_for`, spec/corpus.md §12.1.1). The `path:`
    override is tried first, ahead of every corpus root, exactly as before
    *(v18, DEPRECATED v21)*."""
    snapshot = reference.snapshots.get(tag)
    if snapshot is None:
        return None, None
    if snapshot.path is not None:
        # (v18, deprecated v21) interim deployment-local override, tried
        # first. No existence check at manifest-load time (spec/athenaeum.md
        # §2.3) — a declared path may be on a mount that isn't up, so a miss
        # here just falls through to the corpus routes rather than erroring.
        p = Path(snapshot.path)
        if p.is_file():
            return p, None
    for root in corpora_roots:
        p = _corpus_store_path(root, snapshot.artifact)
        if p is not None:
            return p, root
        p = corpus_locationindex.route_for(root, snapshot.artifact)
        if p is not None:
            return p, root
    return None, None


def _fallback_root(resolved_root: Path | None, corpora_roots: Sequence[Path]) -> Path | None:
    """The corpus root cache-mold derived state (the sidecar index) should
    live under: whichever root the mirror actually resolved through, or —
    when it resolved only via the deprecated `path:` override — the FIRST
    registered corpus root regardless (§6.5: the deployment's corpus cache
    is the right home even while bytes read in place). `None` only when
    there are no corpora roots at all."""
    if resolved_root is not None:
        return resolved_root
    return corpora_roots[0] if corpora_roots else None


def _corpus_store_path(corpus_root: Path, artifact_hash: str) -> Path | None:
    """A mirror snapshot is registered as an ordinary standalone corpus
    artifact (§6.5: "the mirror bytes themselves are corpus artifacts") —
    `artifacts/<shard>/<hash>.<ext>` on the corpus's local filesystem
    (`corpus/paths.py`). The extension isn't known ahead of time (a ZIM's
    `.zim`, a dump's `.jsonl`, …), so — mirroring the resolver's own
    `_find_cached_by_stem` lookup (`corpus/resolver.py`) — this globs the
    hash's shard directory for any file with that stem. Local-filesystem
    lookup only, matching the "explore the local store" scope of this
    resolver; a cloud-backed corpus store would need hydration this
    function doesn't attempt."""
    shard_dir = corpus_root / "artifacts" / corpus_paths.shard(artifact_hash)
    if not shard_dir.is_dir():
        return None
    for p in sorted(shard_dir.glob(f"{artifact_hash}.*")):
        if p.is_file():
            return p
    return None


def canonical_index_path(
    reference: Reference, tag: str, corpora_roots: Sequence[Path] = ()
) -> Path | None:
    """*(21)* The canonical sidecar-index path for `reference`'s `tag`
    snapshot (spec/ledger.md §6.5): `<corpus root>/cache/refidx/
    <artifact>.sqlite` under whichever given corpus root the mirror actually
    resolved through (store or attached location). When the mirror resolved
    only through the deprecated `path:` override — no corpus root holding
    the bytes — the sidecar still lands under the FIRST registered corpus
    root regardless: the deployment's corpus cache is the right home for
    derived state even while the mirror's own bytes read in place. `None`
    only when there are no corpora roots at all (bare library use), where
    the adapter's own legacy beside-the-mirror fallback applies instead.

    Never creates `cache/refidx/` — directory creation is the build side's
    job (`ath ref index`), lazily, never a read-path side effect."""
    snapshot = reference.snapshots.get(tag)
    if snapshot is None:
        return None
    _, resolved_root = _materialize_with_root(reference, tag, corpora_roots)
    root = _fallback_root(resolved_root, corpora_roots)
    if root is None:
        return None
    return root / "cache" / "refidx" / f"{snapshot.artifact}.sqlite"


def resolve_adapter_name(reference: Reference, corpora_roots: Sequence[Path] = ()) -> str:
    """*(21)* The format adapter name for `reference` (spec/corpus.md §7.1,
    spec/athenaeum.md §2.3): an explicit `reference.adapter` wins outright.
    Otherwise, derived from the **latest** snapshot's mirror-artifact record
    — schema-first, in the tenancy mold (spec/ledger.md §6.4) — by reading
    its artifact mime and looking up that mime's overlay `ref_adapter`.
    Derivation is per-dataset, keyed to `reference.latest` regardless of
    which tag a caller is actually resolving: the latest snapshot's record
    is the adapter's source of truth, not whichever snapshot happens to be
    requested.

    Raises `AdapterUnavailable` naming exactly what link in that chain is
    missing — no registered latest snapshot, no mirror record found in any
    given corpus root, the record carries no artifact mime, no mime schema
    claims that mime, or the mime schema declares no `ref_adapter` — always
    noting that an explicit manifest `adapter:` is the override.
    """
    if reference.adapter:
        return reference.adapter

    snapshot = reference.snapshots.get(reference.latest)
    if snapshot is None:
        raise AdapterUnavailable(
            f"{reference.dataset}: no adapter declared and latest tag "
            f"{reference.latest!r} names no registered snapshot to derive one from — "
            "declare an explicit manifest adapter: instead"
        )

    record_post = None
    record_root: Path | None = None
    for root in corpora_roots:
        shard = corpus_paths.shard(snapshot.artifact)
        record_path = root / "records" / shard / f"{snapshot.artifact}.md"
        if record_path.is_file():
            record_post = corpus_records.load(record_path)
            record_root = root
            break
    if record_post is None:
        raise AdapterUnavailable(
            f"{reference.dataset}: no adapter declared and no mirror record for artifact "
            f"{snapshot.artifact} was found in any given corpus root — cannot derive "
            "ref_adapter from a mime overlay; declare an explicit manifest adapter: instead"
        )

    mime = corpus_records.media_type_for(record_post)
    if not mime:
        raise AdapterUnavailable(
            f"{reference.dataset}: no adapter declared and mirror record {snapshot.artifact} "
            "carries no artifact mime — cannot derive ref_adapter; declare an explicit "
            "manifest adapter: instead"
        )

    assert record_root is not None
    schema = corpus_schemas.load_mime_schema(record_root, mime)
    if schema is None:
        raise AdapterUnavailable(
            f"{reference.dataset}: no adapter declared and mime {mime!r} (mirror record "
            f"{snapshot.artifact}) matches no mime schema — cannot derive ref_adapter; "
            "declare an explicit manifest adapter: instead"
        )

    ref_adapter = schema.get("ref_adapter")
    if not ref_adapter:
        raise AdapterUnavailable(
            f"{reference.dataset}: no adapter declared and the mime schema for {mime!r} "
            f"(mirror record {snapshot.artifact}) declares no ref_adapter — cannot derive "
            "an adapter; declare an explicit manifest adapter: instead"
        )
    return str(ref_adapter)


# (adapter name, absolute mirror path) -> open handle. Process-lifetime, no
# TTL: mirror bytes are content-addressed and immutable, so a handle can
# never go stale under a fixed path.
_HANDLES: dict[tuple[str, str], Any] = {}


def _open_handle(adapter_name: str, mirror_path: Path, index_path: Path | None) -> Any:
    """Cache lookup around `open_archive`. A failed open (`MirrorCorrupt` —
    truncated or corrupted bytes) propagates straight out of
    `open_archive()`, before the assignment into `_HANDLES` below runs — so
    a bad path is never cached as a live handle, and a later retry (e.g.
    after a download finishes) opens fresh rather than replaying the
    failure. `index_path` — the canonical sidecar location (21) — is only
    passed to adapters that carry the optional index API (`build_index`);
    a plain adapter (e.g. `zim`) needs no sidecar at all."""
    key = (adapter_name, str(mirror_path.resolve()))
    handle = _HANDLES.get(key)
    if handle is None:
        adapter = ADAPTERS[adapter_name]
        kwargs = {"index_path": index_path} if hasattr(adapter, "build_index") else {}
        handle = adapter.open_archive(mirror_path, **kwargs)
        _HANDLES[key] = handle
    return handle


def _resolve_handle(
    reference: Reference, tag: str | None, corpora_roots: Sequence[Path]
) -> tuple[str, Snapshot, str, Any]:
    """Shared preamble of `resolve()` and `search()`: tag -> registered
    snapshot -> adapter name (21: derived when unset) -> adapter
    availability -> materialized mirror -> canonical sidecar path (21) ->
    open handle. Raises the same typed errors both callers document
    (`UnknownTag`, `AdapterUnavailable`, `MirrorUnavailable`, and
    `MirrorCorrupt` from `_open_handle` when bytes exist but aren't a valid
    archive) — the remaining one, `EntryNotFound`, is `resolve_entry`'s
    alone, since "no hits" is `search`'s normal `[]`, not a failure."""
    resolved_tag = reference.latest if tag is None else tag
    snapshot = reference.snapshots.get(resolved_tag)
    if snapshot is None:
        raise UnknownTag(
            f"{reference.dataset}: {resolved_tag!r} is not a registered snapshot"
        )
    adapter_name = resolve_adapter_name(reference, corpora_roots)
    if not adapter_available(adapter_name):
        raise AdapterUnavailable(
            f"{reference.dataset}: adapter {adapter_name!r} is unregistered or its "
            "optional dependency is not installed in this environment"
        )
    mirror_path, resolved_root = _materialize_with_root(reference, resolved_tag, corpora_roots)
    if mirror_path is None:
        raise MirrorUnavailable(
            f"{reference.dataset}@{resolved_tag}: no local bytes (neither the declared "
            "path: override nor any given corpus root's artifact store or attached "
            "location)"
        )
    root = _fallback_root(resolved_root, corpora_roots)
    index_path = root / "cache" / "refidx" / f"{snapshot.artifact}.sqlite" if root else None
    handle = _open_handle(adapter_name, mirror_path, index_path)
    return resolved_tag, snapshot, adapter_name, handle


def resolve(
    reference: Reference,
    native_id: str,
    tag: str | None = None,
    corpora_roots: Sequence[Path] = (),
) -> ResolvedEntry:
    """Resolve one `ref://` citation's native id. `tag` None tracks
    `reference.latest` (a bare citation, §6.5); an explicit tag is a pin.

    Raises `UnknownTag` if the resolved tag names no registered snapshot,
    `AdapterUnavailable` if the adapter (explicit or *(21)* derived from the
    mirror record's mime overlay) is unregistered or its optional dependency
    is missing — or if derivation itself fails — `MirrorUnavailable` if
    `materialize()` finds no local bytes, `MirrorCorrupt` if bytes exist but
    the adapter can't open them as its format, `MirrorUnindexed` if the
    adapter needs a sidecar index (e.g. `osm-pbf`) and none exists or it's
    stale, and `EntryNotFound` if the mirror opens but `native_id` isn't in
    it.
    """
    resolved_tag, snapshot, adapter_name, handle = _resolve_handle(reference, tag, corpora_roots)
    result = ADAPTERS[adapter_name].resolve_entry(handle, native_id)
    return ResolvedEntry(
        dataset=reference.dataset,
        tag=resolved_tag,
        artifact=snapshot.artifact,
        native_id=native_id,
        canonical_id=result.canonical_id,
        title=result.title,
        text=result.text,
        content_type=result.content_type,
    )


def search(
    reference: Reference,
    query: str,
    tag: str | None = None,
    corpora_roots: Sequence[Path] = (),
    limit: int = 10,
    mode: str = "blend",
) -> list[SearchHit]:
    """Discovery step ahead of `resolve()` (spec/ledger.md §6.5): native ids
    aren't guessable, so a scribe searches a dataset by words and pastes a
    hit's `native_id` onward. `tag` and error semantics match `resolve()`
    exactly (`UnknownTag`, `AdapterUnavailable`, `MirrorUnavailable`,
    `MirrorCorrupt`); an empty return is a normal outcome (no hits, or the
    mirror has no index for the requested tier — §6.5 "absence … is
    honestly unverifiable, never a crash"), not one of those errors.
    `MirrorUnindexed` is raised instead when the adapter itself needs a
    sidecar index to search at all (e.g. `osm-pbf`) and none exists or it's
    stale — distinct from a mirror that opens fine but lacks a given tier.

    `mode` (default `"blend"`) is passed straight through to the adapter's
    `search_entries`: `"blend"` returns title-index hits first, then
    full-text hits appended and deduplicated (an archive missing one tier
    degrades gracefully within blend rather than erroring — every
    registered mirror in this deployment happens to carry both, but the
    contract doesn't assume it); `"suggest"` is title-index only (the old
    default, still available for exact-title lookups); `"fulltext"` is
    full-text-index only. An unrecognized mode is `ValueError`, raised by
    the adapter.
    """
    _, _, adapter_name, handle = _resolve_handle(reference, tag, corpora_roots)
    hits = ADAPTERS[adapter_name].search_entries(handle, query, limit, mode=mode)
    return [
        SearchHit(native_id=hit.native_id, title=hit.title, context=hit.context)
        for hit in hits
    ]
