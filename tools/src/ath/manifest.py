"""`athenaeum.yaml` — the member manifest.

The manifest at the orchestrator repo root is the single registry of the
system's member repos (corpora, the ledger, codices) and the runtime join the
tooling reads. Members are keyed by name under a `corpora:` / `ledger:` /
`codices:` mapping; paths and remotes derive by convention — `corpora/<name>`,
`<name>` at the root for the ledger, `codices/<name>`, and `{org}/{name}.git`
— unless a member overrides `path:` / `remote:`. There is exactly one ledger
per deployment (`spec/ledger.md` §1.2).

Reference datasets (`spec/ledger.md` §6.5) register under `references:` —
locally-mirrored external databases cited as `ref://` evidence. They are
mirrors pinned by snapshot version, not git members.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

MANIFEST_NAME = "athenaeum.yaml"

# layer key → default parent directory ("" = the workspace root)
_LAYER_DIRS = {"corpora": "corpora", "ledger": "", "codices": "codices"}


class ManifestError(RuntimeError):
    """The manifest is missing or malformed."""


@dataclass(frozen=True)
class Member:
    name: str
    layer: str  # "corpora" | "ledger" | "codices"
    path: Path  # absolute working-tree location
    remote: str
    description: str
    # Declared tenancy — meaningful for corpora, where it drives derived
    # sensitivity (spec/ledger.md §6.4). Default private: fail closed.
    visibility: str = "private"


@dataclass(frozen=True)
class Reference:
    """A registered reference dataset — a local mirror, not a git member."""

    dataset: str
    description: str
    mirror: str  # the local mirror source (a ZIM file, a dump, an extract)
    snapshot: str  # the pinned snapshot version cited by evidence verification


def find_root(start: Path | None = None) -> Path:
    """Walk up from *start* (default: cwd) to the directory holding the manifest."""
    cur = (start or Path.cwd()).resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / MANIFEST_NAME).is_file():
            return candidate
    raise ManifestError(f"no {MANIFEST_NAME} found walking up from {cur}")


def _read(root: Path) -> dict:
    return yaml.safe_load((root / MANIFEST_NAME).read_text(encoding="utf-8")) or {}


def load(root: Path) -> list[Member]:
    """Parse the manifest at *root* into the member list, manifest order preserved."""
    data = _read(root)
    org = str(data.get("org") or "").rstrip("/")
    members: list[Member] = []
    for layer, dirname in _LAYER_DIRS.items():
        entries = data.get(layer) or {}
        if not isinstance(entries, dict):
            raise ManifestError(f"manifest {layer}: expected a name-keyed mapping")
        if layer == "ledger" and len(entries) > 1:
            raise ManifestError(
                "manifest ledger: exactly one ledger per deployment (spec/ledger.md §1.2)"
            )
        for name, spec in entries.items():
            spec = spec or {}
            remote = str(spec.get("remote") or "")
            if not remote:
                if not org:
                    raise ManifestError(f"{layer}/{name}: no remote and no org to derive one from")
                remote = f"{org}/{name}.git"
            default_path = f"{dirname}/{name}" if dirname else str(name)
            visibility = str(spec.get("visibility") or "private")
            if visibility not in ("public", "private"):
                raise ManifestError(
                    f"{layer}/{name}: visibility must be 'public' or 'private', got {visibility!r}"
                )
            members.append(
                Member(
                    name=str(name),
                    layer=layer,
                    path=(root / str(spec.get("path") or default_path)).resolve(),
                    remote=remote,
                    description=str(spec.get("description") or ""),
                    visibility=visibility,
                )
            )
    return members


def load_references(root: Path) -> list[Reference]:
    """Parse the manifest's `references:` section — registered reference datasets."""
    entries = _read(root).get("references") or {}
    if not isinstance(entries, dict):
        raise ManifestError("manifest references: expected a dataset-keyed mapping")
    return [
        Reference(
            dataset=str(name),
            description=str((spec or {}).get("description") or ""),
            mirror=str((spec or {}).get("mirror") or ""),
            snapshot=str((spec or {}).get("snapshot") or ""),
        )
        for name, spec in entries.items()
    ]
