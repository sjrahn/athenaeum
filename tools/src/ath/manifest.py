"""`athenaeum.yaml` — the member manifest.

The manifest at the orchestrator repo root is the single registry of the
system's member repos (corpora and codices) and the runtime join the tooling
reads. Members are keyed by name under a `corpora:` or `codices:` mapping;
paths and remotes derive by convention — `corpora/<name>` / `codices/<name>`
and `{org}/{name}.git` — unless a member overrides `path:` / `remote:`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

MANIFEST_NAME = "athenaeum.yaml"

_LAYER_DIRS = {"corpora": "corpora", "codices": "codices"}


class ManifestError(RuntimeError):
    """The manifest is missing or malformed."""


@dataclass(frozen=True)
class Member:
    name: str
    layer: str  # "corpora" | "codices"
    path: Path  # absolute working-tree location
    remote: str
    description: str


def find_root(start: Path | None = None) -> Path:
    """Walk up from *start* (default: cwd) to the directory holding the manifest."""
    cur = (start or Path.cwd()).resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / MANIFEST_NAME).is_file():
            return candidate
    raise ManifestError(f"no {MANIFEST_NAME} found walking up from {cur}")


def load(root: Path) -> list[Member]:
    """Parse the manifest at *root* into the member list, manifest order preserved."""
    data = yaml.safe_load((root / MANIFEST_NAME).read_text(encoding="utf-8")) or {}
    org = str(data.get("org") or "").rstrip("/")
    members: list[Member] = []
    for layer, dirname in _LAYER_DIRS.items():
        entries = data.get(layer) or {}
        if not isinstance(entries, dict):
            raise ManifestError(f"manifest {layer}: expected a name-keyed mapping")
        for name, spec in entries.items():
            spec = spec or {}
            remote = str(spec.get("remote") or "")
            if not remote:
                if not org:
                    raise ManifestError(f"{layer}/{name}: no remote and no org to derive one from")
                remote = f"{org}/{name}.git"
            members.append(
                Member(
                    name=str(name),
                    layer=layer,
                    path=(root / str(spec.get("path") or f"{dirname}/{name}")).resolve(),
                    remote=remote,
                    description=str(spec.get("description") or ""),
                )
            )
    return members
