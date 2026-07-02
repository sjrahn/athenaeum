"""Back-compat facade — delegates to the configured `ArtifactStore`.

The reference's `artifacts.py` exposed module-level functions
(`local_path`, `is_local`, `ensure_local`, `list_local`, …) taking
`(corpus_root, record_id, ext)`. This module mirrors that surface so any caller
ported in a hurry continues to work, while routing each call through
`store.get_store(corpus_root)` so the storage backend is whatever the corpus
configured.

New code should call `store.get_store(corpus_root)` directly and use the
`ArtifactStore` Protocol — this facade exists for convenience, not as the
preferred path.
"""

from __future__ import annotations

from pathlib import Path

from .store import ArtifactMissing, get_store  # re-exported

__all__ = [
    "ArtifactMissing",
    "ensure_local",
    "exists",
    "is_local",
    "list_local",
    "list_remote",
    "local_path",
    "put",
]


def local_path(corpus_root: Path, record_id: str, ext: str) -> Path:
    return get_store(corpus_root).local_path(record_id, ext)


def is_local(corpus_root: Path, record_id: str, ext: str) -> bool:
    return get_store(corpus_root).is_local(record_id, ext)


def exists(corpus_root: Path, record_id: str, ext: str) -> bool:
    return get_store(corpus_root).exists(record_id, ext)


def ensure_local(corpus_root: Path, record_id: str, ext: str) -> Path:
    return get_store(corpus_root).ensure_local(record_id, ext)


def put(corpus_root: Path, record_id: str, ext: str, src: Path) -> None:
    get_store(corpus_root).put(record_id, ext, src)


def list_local(corpus_root: Path) -> set[str]:
    return get_store(corpus_root).list_local()


def list_remote(corpus_root: Path) -> set[str]:
    return get_store(corpus_root).list_remote()
