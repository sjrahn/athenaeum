"""`athenaeum.yaml` — the instance config (spec Part I §2.3, v26).

The config at the instance root is TRACKED instance state: the tenancy floor
(`visibility:`), the issue tracker, and the reference-dataset registry. The
layers are fixed directories of the instance — `corpus/` and `ledger/` — so
the config registers no members; the pre-v26 member manifest (a `corpora:` /
`ledger:` roster of separate repos) is retired, and a manifest still carrying
those keys is refused with a migration pointer.

Discovery is upward: `find_root` walks from the current directory to the
nearest `athenaeum.yaml`; the `ATHENAEUM_ROOT` environment variable overrides.
The distribution's own checkout location is irrelevant to operation — the
tooling points at an instance and works inside it (spec Part I §2.2).

Reference datasets (`spec/ledger.md` §6.5) register under `references:` —
locally-mirrored external databases cited as `ref://` evidence. A dataset
registers multiple snapshots — a tag-keyed `snapshots:` map (tag → a
`Snapshot`: the mirror's blake3 `artifact`, plus a deprecated deployment-local
`path:` override) and an explicit `latest:` default naming one of those tags.
`adapter:` — the format resolving native ids — is OPTIONAL: an explicit
declaration wins, but when absent it derives at resolution time from the
latest snapshot's mirror record's mime overlay `ref_adapter`
(`refdata.resolve_adapter_name`, spec/corpus.md §7.1). A snapshot's mirror
bytes are a corpus artifact, distributed and integrity-checked through the
corpus store (Part IV).

The issue tracker registers under `tracker:` — the forge repo whose issues
carry the instance's backlog, the forge `host:`, and the in-repo path of the
snapshot `ath issue sync` writes.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

MANIFEST_NAME = "athenaeum.yaml"
ROOT_ENV = "ATHENAEUM_ROOT"
# Deployment state beside the config by default; point it somewhere tracked
# (e.g. corpus/runbooks/tickets.md) so the backlog's movement stays in history.
_DEFAULT_SNAPSHOT = "tickets.md"

_RETIRED_MEMBER_KEYS = ("corpora", "ledger")


class ManifestError(RuntimeError):
    """The instance config is missing or malformed."""


@dataclass(frozen=True)
class Instance:
    """The instance the tooling operates in (spec Part I §2.2)."""

    root: Path
    name: str = ""
    # The tenancy floor — the fail-closed default for records whose origins
    # declare no `tenancy:` (spec/ledger.md §6.4). Default private.
    visibility: str = "private"

    @property
    def corpus_root(self) -> Path:
        return self.root / "corpus"

    @property
    def ledger_root(self) -> Path:
        return self.root / "ledger"


@dataclass(frozen=True)
class Tracker:
    """The issue tracker holding the instance's backlog."""

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


_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_ARTIFACT_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Snapshot:
    """One registered snapshot of a reference dataset (spec Part I §2.3).

    `artifact` is identity — the blake3 pin verification stamps (§13.2); it
    never changes meaning. `path` is the DEPRECATED deployment-local
    materialization override: a mirror file read in place, tried before the
    corpus store's routes — superseded by an attached location over the
    mirrors directory (Part IV §3.2), read tolerantly until every registered
    snapshot store-resolves. Presence isn't checked at load time — the file
    may live on a mount that isn't up; that's a resolver/status concern.
    """

    artifact: str  # 64-hex blake3 — the pin verification stamps
    path: str | None = None  # deprecated in-place materialization override


@dataclass(frozen=True)
class Reference:
    """A registered reference dataset — a local mirror, not a repo.

    Multi-snapshot: `snapshots` maps tag → `Snapshot`, `latest` names the
    default tag. `ref://{dataset}@{tag}/{id}` (spec/ledger.md §6.5) pins a
    snapshot; bare `ref://{dataset}/{id}` tracks `latest`.

    `adapter` is optional — an explicit declaration wins (the bootstrap and
    override path), but when absent the format adapter is derived from the
    latest snapshot's mirror record's mime overlay `ref_adapter`
    (spec/corpus.md §7.1) via `refdata.resolve_adapter_name`.
    """

    dataset: str
    description: str
    latest: str  # the default snapshot tag — a key of snapshots
    snapshots: dict[str, Snapshot]  # tag -> Snapshot
    adapter: str | None = None  # explicit override; None derives from the mirror's mime overlay


def find_root(start: Path | None = None) -> Path:
    """The instance root: $ATHENAEUM_ROOT when set, else walk up from *start*
    (default: cwd) to the directory holding the config."""
    env = os.environ.get(ROOT_ENV)
    if env and start is None:
        root = Path(env).resolve()
        if not (root / MANIFEST_NAME).is_file():
            raise ManifestError(f"{ROOT_ENV}={env} does not contain {MANIFEST_NAME}")
        return root
    cur = (start or Path.cwd()).resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / MANIFEST_NAME).is_file():
            return candidate
    raise ManifestError(f"no {MANIFEST_NAME} found walking up from {cur}")


def _read(root: Path) -> dict:
    data = yaml.safe_load((root / MANIFEST_NAME).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ManifestError(f"{root / MANIFEST_NAME}: expected a mapping")
    retired = [k for k in _RETIRED_MEMBER_KEYS if k in data]
    if retired:
        raise ManifestError(
            f"{root / MANIFEST_NAME} declares member repos ({', '.join(retired)}:) — "
            "the pre-v26 workspace shape. v26 merges the members into one instance "
            "repo (corpus/ + ledger/ directories) with a tracked config; see "
            "spec/athenaeum.md §2 and spec/CHANGELOG.md v26 for the migration."
        )
    return data


def load_instance(root: Path) -> Instance:
    """Parse the instance config at *root*."""
    data = _read(root)
    visibility = str(data.get("visibility") or "private")
    if visibility not in ("public", "private"):
        raise ManifestError(
            f"visibility must be 'public' or 'private', got {visibility!r}"
        )
    return Instance(root=root, name=str(data.get("name") or ""), visibility=visibility)


def load_references(root: Path) -> list[Reference]:
    """Parse the config's `references:` section — registered reference datasets
    (`spec/ledger.md` §6.5)."""
    entries = _read(root).get("references") or {}
    if not isinstance(entries, dict):
        raise ManifestError("manifest references: expected a dataset-keyed mapping")
    refs: list[Reference] = []
    for name, spec in entries.items():
        spec = spec or {}
        if "mirror" in spec or "snapshot" in spec:
            raise ManifestError(
                f"references/{name}: 'mirror:'/'snapshot:' are retired — register "
                "'adapter:', 'latest:', and a tag-keyed 'snapshots:' map "
                "(spec/athenaeum.md §2.3)"
            )
        # adapter: optional — a missing/empty declaration derives at resolution
        # time from the mirror record's mime overlay ref_adapter
        # (refdata.resolve_adapter_name); not a load-time error.
        adapter = str(spec.get("adapter") or "") or None
        snapshots_raw = spec.get("snapshots") or {}
        if not isinstance(snapshots_raw, dict) or not snapshots_raw:
            raise ManifestError(f"references/{name}: snapshots must be a non-empty "
                                "tag-keyed mapping")
        snapshots: dict[str, Snapshot] = {}
        for tag, snap in snapshots_raw.items():
            tag = str(tag)
            if not _TAG_RE.match(tag):
                raise ManifestError(f"references/{name}: snapshot tag {tag!r} must match "
                                    "^[a-z0-9][a-z0-9._-]*$ (rides in ref:// URIs after '@')")
            snap = snap or {}
            artifact = str(snap.get("artifact") or "")
            if not _ARTIFACT_RE.match(artifact):
                raise ManifestError(f"references/{name}/{tag}: artifact must be a 64-hex "
                                    f"lowercase blake3, got {artifact!r}")
            # No existence check here — a declared path may live on a mount
            # that isn't up; presence is a resolver/status concern.
            path = snap.get("path")
            snapshots[tag] = Snapshot(artifact=artifact, path=str(path) if path else None)
        latest = str(spec.get("latest") or "")
        if not latest or latest not in snapshots:
            raise ManifestError(f"references/{name}: latest {latest!r} must name a key "
                                "of snapshots")
        refs.append(
            Reference(
                dataset=str(name),
                description=str(spec.get("description") or ""),
                adapter=adapter,
                latest=latest,
                snapshots=snapshots,
            )
        )
    return refs


def load_tracker(root: Path) -> Tracker:
    """Parse the config's `tracker:` section.

    `host:` names the forge instance (`https://host`); the legacy `org:` key
    (`https://host/org`) is read as a fallback so a pre-v26 config's tracker
    still resolves during migration. `repo:` is `owner/name`.
    """
    data = _read(root)
    spec = data.get("tracker") or {}
    if not isinstance(spec, dict):
        raise ManifestError("manifest tracker: expected a mapping")
    host_url = str(spec.get("host") or data.get("org") or "").rstrip("/")
    if not host_url:
        raise ManifestError("manifest tracker: no host to derive the forge API from")
    slug = str(spec.get("repo") or "")
    if slug.count("/") != 1:
        raise ManifestError(f"manifest tracker.repo: expected 'owner/name', got {slug!r}")
    owner, repo = slug.split("/")
    # host may be https://host or (legacy org) https://host/org — the API
    # lives at the instance root either way.
    scheme, _, rest = host_url.partition("://")
    host = rest.split("/", 1)[0]
    return Tracker(
        base=f"{scheme}://{host}/api/v1",
        owner=owner,
        repo=repo,
        snapshot=root / str(spec.get("snapshot") or _DEFAULT_SNAPSHOT),
    )
