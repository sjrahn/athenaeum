"""The reference-dataset resolver (spec/ledger.md §6.5) — "resolution is
downward": `(dataset, tag)` -> the snapshot's mirror-artifact blake3 ->
bytes materialized on local disk -> the dataset's adapter renders the
requested entry (title, plain text, content type) for quote verification.

Two entry points:

- `materialize(reference, tag, corpora_roots)` — the snapshot's bytes on
  local disk, or None. Tries the snapshot's declared `path:` override first
  *(v18, spec/athenaeum.md §2.3)*, then each given corpus root's artifact
  store by blake3. A declared-but-absent `path:` is simply a miss, not an
  error — it falls through to the store.
- `resolve(reference, native_id, tag, corpora_roots)` — the full resolution:
  tag -> snapshot -> materialize -> adapter -> `ResolvedEntry`. Raises the
  typed `errors.RefdataError` hierarchy on any failure a caller needs to
  branch on (§6.5: content resolution absent is *unverifiable*, never a
  crash — callers catch these and report accordingly, they are not meant to
  propagate to a user-facing traceback).

Archive handles are expensive to open and verification resolves many
entries against one snapshot, so open handles are cached per absolute
mirror path, process-lifetime (no TTL — a corpus artifact's bytes are
content-addressed and immutable, so a cached handle never goes stale).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ath.manifest import Reference
from corpus import paths as corpus_paths

from .adapters import ADAPTERS, AdapterResult, adapter_available
from .errors import (
    AdapterUnavailable,
    EntryNotFound,
    MirrorUnavailable,
    RefdataError,
    UnknownTag,
)

__all__ = [
    "ADAPTERS",
    "AdapterResult",
    "AdapterUnavailable",
    "EntryNotFound",
    "MirrorUnavailable",
    "RefdataError",
    "ResolvedEntry",
    "UnknownTag",
    "adapter_available",
    "materialize",
    "resolve",
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


def materialize(
    reference: Reference, tag: str, corpora_roots: Sequence[Path] = ()
) -> Path | None:
    """The bytes of `reference`'s `tag` snapshot on local disk, or None if
    nowhere materialized (§6.5 "Resolution is downward"). An unregistered
    `tag` is itself a miss — this function reports presence, not
    registration; `resolve()` is where an unknown tag is a typed error."""
    snapshot = reference.snapshots.get(tag)
    if snapshot is None:
        return None
    if snapshot.path is not None:
        # (v18) interim deployment-local override, tried first. No existence
        # check at manifest-load time (spec/athenaeum.md §2.3) — a declared
        # path may be on a mount that isn't up, so a miss here just falls
        # through to the corpus store rather than erroring.
        p = Path(snapshot.path)
        if p.is_file():
            return p
    for root in corpora_roots:
        p = _corpus_store_path(root, snapshot.artifact)
        if p is not None:
            return p
    return None


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


# (adapter name, absolute mirror path) -> open handle. Process-lifetime, no
# TTL: mirror bytes are content-addressed and immutable, so a handle can
# never go stale under a fixed path.
_HANDLES: dict[tuple[str, str], Any] = {}


def _open_handle(adapter_name: str, mirror_path: Path) -> Any:
    key = (adapter_name, str(mirror_path.resolve()))
    handle = _HANDLES.get(key)
    if handle is None:
        handle = ADAPTERS[adapter_name].open_archive(mirror_path)
        _HANDLES[key] = handle
    return handle


def resolve(
    reference: Reference,
    native_id: str,
    tag: str | None = None,
    corpora_roots: Sequence[Path] = (),
) -> ResolvedEntry:
    """Resolve one `ref://` citation's native id. `tag` None tracks
    `reference.latest` (a bare citation, §6.5); an explicit tag is a pin.

    Raises `UnknownTag` if the resolved tag names no registered snapshot,
    `AdapterUnavailable` if `reference.adapter` is unregistered or its
    optional dependency is missing, `MirrorUnavailable` if `materialize()`
    finds no local bytes, and `EntryNotFound` if the mirror opens but
    `native_id` isn't in it.
    """
    resolved_tag = reference.latest if tag is None else tag
    snapshot = reference.snapshots.get(resolved_tag)
    if snapshot is None:
        raise UnknownTag(
            f"{reference.dataset}: {resolved_tag!r} is not a registered snapshot"
        )
    if not adapter_available(reference.adapter):
        raise AdapterUnavailable(
            f"{reference.dataset}: adapter {reference.adapter!r} is unregistered or its "
            "optional dependency is not installed in this environment"
        )
    mirror_path = materialize(reference, resolved_tag, corpora_roots)
    if mirror_path is None:
        raise MirrorUnavailable(
            f"{reference.dataset}@{resolved_tag}: no local bytes (neither the declared "
            "path: override nor any given corpus root's artifact store)"
        )
    handle = _open_handle(reference.adapter, mirror_path)
    result = ADAPTERS[reference.adapter].resolve_entry(handle, native_id)
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
