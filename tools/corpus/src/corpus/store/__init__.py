"""ArtifactStore — pluggable byte storage for the corpus.

Artifacts live at `artifacts/<shard>/<id>.<ext>` on the local filesystem (the canonical
layout per spec §12.1/§12.2). A pluggable store lets a corpus mirror those bytes to a
remote backend (Azure Blob, S3) with lazy hydration on demand, while leaving the local
filesystem layout untouched.

The Protocol surface mirrors what the resolver and drafters need:

- `local_path(record_id, ext)` — the canonical on-disk path.
- `is_local(record_id, ext)` — file present locally.
- `exists(record_id, ext)` — file present locally OR available remotely.
- `ensure_local(record_id, ext)` — return the local path, downloading from remote if
  needed; raise `ArtifactMissing` if absent everywhere.
- `put(record_id, ext, src)` — persist new bytes (ingest path).
- `list_local()` / `list_remote()` — `<shard>/<file>` names.

`LocalArtifactStore` (P2) is the default. `AzureBlobStore` and `S3Store` (P3, opt-in
extras) plug into the same Protocol.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from .local import LocalArtifactStore

__all__ = ["ArtifactMissing", "ArtifactStore", "LocalArtifactStore", "get_store"]


class ArtifactMissing(Exception):
    """Artifact bytes are absent locally and cannot be retrieved from the backing
    store. Message is operator-actionable — callers may surface it directly."""


@runtime_checkable
class ArtifactStore(Protocol):
    """Pluggable byte storage. Implementations are bound to a specific corpus_root
    at construction."""

    def local_path(self, record_id: str, ext: str) -> Path:
        """Canonical on-disk path under `artifacts/<shard>/<id>.<ext>`."""
        ...

    def is_local(self, record_id: str, ext: str) -> bool:
        ...

    def exists(self, record_id: str, ext: str) -> bool:
        """Local OR remote. Equal to `is_local` for local-only stores."""
        ...

    def ensure_local(self, record_id: str, ext: str) -> Path:
        """Return the local path, hydrating from the remote backing store if needed.

        Raises `ArtifactMissing` if the bytes are absent both locally and remotely
        (or the remote is unreachable on a local-only configuration).
        """
        ...

    def put(self, record_id: str, ext: str, src: Path) -> None:
        """Persist `src` as the artifact's bytes — used by the ingest path."""
        ...

    def list_local(self) -> set[str]:
        """`<shard>/<file>` names of artifacts present on the local filesystem."""
        ...

    def list_remote(self) -> set[str]:
        """`<shard>/<file>` names available remotely. Empty set for local-only stores."""
        ...


def get_store(corpus_root: Path) -> ArtifactStore:
    """Resolve the configured store for `corpus_root`.

    P2: always returns `LocalArtifactStore`. P3 will read `<corpus_root>/corpus.toml`
    + env (`CORPUS_STORE`, `CORPUS_AZURE_*`, etc.) and dispatch to the appropriate
    adapter.
    """
    return LocalArtifactStore(corpus_root)
