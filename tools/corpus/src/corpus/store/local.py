"""LocalArtifactStore — the default `ArtifactStore` implementation.

Reads and writes `artifacts/<shard>/<id>.<ext>` on the corpus's local filesystem.
No remote backing; `list_remote()` returns empty; `ensure_local()` raises
`ArtifactMissing` when bytes are absent.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from corpus import paths


class LocalArtifactStore:
    """Filesystem-backed `ArtifactStore`. The default."""

    def __init__(self, corpus_root: Path):
        self._root = corpus_root

    @property
    def root(self) -> Path:
        return self._root

    def local_path(self, record_id: str, ext: str) -> Path:
        return paths.artifact_path(self._root, record_id, ext)

    def is_local(self, record_id: str, ext: str) -> bool:
        return self.local_path(record_id, ext).is_file()

    def exists(self, record_id: str, ext: str) -> bool:
        # Local-only store: exists ≡ is_local.
        return self.is_local(record_id, ext)

    def ensure_local(self, record_id: str, ext: str) -> Path:
        # Import here to avoid circular import (store/__init__ imports this module).
        from . import ArtifactMissing

        p = self.local_path(record_id, ext)
        if not p.is_file():
            raise ArtifactMissing(
                f"artifact {paths.shard(record_id)}/{record_id}.{ext.lstrip('.')} "
                f"not present under {self._root}/artifacts/ and no remote store "
                f"is configured."
            )
        return p

    def put(self, record_id: str, ext: str, src: Path) -> None:
        dst = paths.ensure_parent(self.local_path(record_id, ext))
        shutil.copyfile(src, dst)

    def list_local(self) -> set[str]:
        artifacts_root = self._root / "artifacts"
        if not artifacts_root.is_dir():
            return set()
        out: set[str] = set()
        for shard_dir in artifacts_root.iterdir():
            if not shard_dir.is_dir() or len(shard_dir.name) != paths.SHARD_LEN:
                continue
            for f in shard_dir.iterdir():
                if f.is_file():
                    out.add(f"{shard_dir.name}/{f.name}")
        return out

    def list_remote(self) -> set[str]:
        return set()
