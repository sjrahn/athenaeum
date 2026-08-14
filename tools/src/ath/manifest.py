"""`athenaeum.yaml` — the member manifest.

The manifest at the orchestrator repo root is the single registry of the
system's member repos (corpora and the ledger) and the runtime join the
tooling reads. Members are keyed by name under a `corpora:` / `ledger:`
mapping; paths and remotes derive by convention — `corpora/<name>`, `<name>`
at the root for the ledger, and `{org}/{name}.git` — unless a member
overrides `path:` / `remote:`. There is exactly one ledger per deployment
(`spec/ledger.md` §1.2). Consumers of the system's product (codices, expert
agents) are NOT members: the system holds no registry of them (spec
athenaeum.md §5, v15).

Reference datasets (`spec/ledger.md` §6.5) register under `references:` —
locally-mirrored external databases cited as `ref://` evidence. They are
mirrors pinned by snapshot version, not git members.

The issue tracker registers under `tracker:` — the Forgejo repo whose issues
carry the system's backlog, and the in-repo path of the snapshot `ath issue
sync` writes. Host derives from `org:`, so no tooling hardcodes an instance.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

MANIFEST_NAME = "athenaeum.yaml"
# Deployment state beside the manifest by default; deployments SHOULD point it
# into a member repo (e.g. corpus/runbooks/tickets.md) so the backlog's movement
# stays committed — the orchestrator repo itself tracks no deployment state.
_DEFAULT_SNAPSHOT = "tickets.md"

# layer key → default parent directory ("" = the workspace root)
_LAYER_DIRS = {"corpora": "corpora", "ledger": ""}


class ManifestError(RuntimeError):
    """The manifest is missing or malformed."""


@dataclass(frozen=True)
class Member:
    name: str
    layer: str  # "corpora" | "ledger"
    path: Path  # absolute working-tree location
    remote: str
    description: str
    # Declared tenancy — meaningful for corpora, where it drives derived
    # sensitivity (spec/ledger.md §6.4). Default private: fail closed.
    visibility: str = "private"


@dataclass(frozen=True)
class Tracker:
    """The issue tracker holding the system's backlog.

    One tracker for the whole system, on the orchestrator repo: tickets cross
    members constantly (a corpus migration owes a ledger re-anchor), and
    splitting them per member would re-create the isolation this vantage point
    exists to avoid. The member a ticket touches is a label, not a repo.
    """

    base: str  # API root, e.g. https://host/api/v1
    owner: str
    repo: str
    snapshot: Path  # in-repo path of the generated offline snapshot

    @property
    def issues_path(self) -> str:
        return f"/repos/{self.owner}/{self.repo}/issues"

    @property
    def web(self) -> str:
        return f"{self.base.removesuffix('/api/v1')}/{self.owner}/{self.repo}/issues"


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


def load_tracker(root: Path) -> Tracker:
    """Parse the manifest's `tracker:` section.

    The host derives from `org:` rather than being spelled again, so a fork or a
    moved instance changes one line. `repo:` is `owner/name`.
    """
    data = _read(root)
    spec = data.get("tracker") or {}
    if not isinstance(spec, dict):
        raise ManifestError("manifest tracker: expected a mapping")
    org = str(data.get("org") or "").rstrip("/")
    if not org:
        raise ManifestError("manifest tracker: no org to derive the instance host from")
    slug = str(spec.get("repo") or "")
    if slug.count("/") != 1:
        raise ManifestError(f"manifest tracker.repo: expected 'owner/name', got {slug!r}")
    owner, repo = slug.split("/")
    # org is https://host/org — the API lives at the instance root, not under the org.
    scheme, _, rest = org.partition("://")
    host = rest.split("/", 1)[0]
    return Tracker(
        base=f"{scheme}://{host}/api/v1",
        owner=owner,
        repo=repo,
        snapshot=root / str(spec.get("snapshot") or _DEFAULT_SNAPSHOT),
    )
