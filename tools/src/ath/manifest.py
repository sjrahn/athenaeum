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
corpus store (Part IV). `spine: true` (spec/ledger.md §15.2) admits a
dataset as an extension-chain root for the ledger's ontology layer — the
distribution ships the format adapters (`bfo-2020`, `cco-release`); which
release an instance trusts is this registration, same as any other.

Tool assets (`spec/corpus.md` §12.3.6) register under `assets:` — payloads
the tooling injects or executes (the web capturer's SingleFile bundle),
pinned exactly as a reference snapshot is: the same tag-keyed `snapshots:` /
`latest:` grammar (`load_assets`), carrying none of `references:`'s
adapter/citation machinery — an asset's bytes are never a `ref://` surface.

The issue tracker registers under `tracker:` — the forge repo whose issues
carry the instance's backlog, the forge `host:`, and the in-repo path of the
snapshot `ath issue sync` writes.

Tenancy (`spec/ledger.md` §6.4) registers under `tenancy:` — the instance's
declared tier set beside the reserved `public`/`private`, and named
`audiences:` (grant sets the read surface serves, `spec/athenaeum.md` §2.3).
Absent the block, an instance carries the `public | private` binary,
byte-identically to every pre-tier instance. `visibility:` generalizes
alongside it: the tier silence falls to — `public`, `private`, or a declared
tier.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml

MANIFEST_NAME = "athenaeum.yaml"
ROOT_ENV = "ATHENAEUM_ROOT"
# Deployment state beside the config by default; point it somewhere tracked
# (e.g. corpus/runbooks/tickets.md) so the backlog's movement stays in history.
_DEFAULT_SNAPSHOT = "tickets.md"

_RETIRED_MEMBER_KEYS = ("corpora", "ledger")

# Duplicated from `ledger.model.SLUG_RE` — manifest.py must not import from
# ledger (the layers are read-only downstream of the config, never the other
# way). Tier and audience names live in this same readable-slug shape.
_SLUG_RE = re.compile(r"^[a-z0-9]+(--?[a-z0-9]+)*$")

# The two tenancy tiers every instance carries regardless of declaration —
# `public` (the publishable tier, spec/ledger.md §6.4) and `private` (the
# floor, the owner's alone, never grantable). An instance's declared `tiers:`
# may name no others.
RESERVED_TIERS = ("public", "private")


class ManifestError(RuntimeError):
    """The instance config is missing or malformed."""


@dataclass(frozen=True)
class Instance:
    """The instance the tooling operates in (spec Part I §2.2)."""

    root: Path
    name: str = ""
    # The tenancy floor — the fail-closed default for records whose origins
    # declare no `tenancy:` (spec/ledger.md §6.4). Names `public`, `private`,
    # or a declared tier. Default private.
    visibility: str = "private"
    # The instance's declared tiers beside the reserved public/private
    # (spec/athenaeum.md §2.3, spec/ledger.md §6.4). Empty = the binary.
    tiers: tuple[str, ...] = ()
    # Named grant sets the read surface serves: audience name -> declared
    # tiers granted (never `private`; `public` is implicit in every audience
    # and not stored here — see `grants_for`).
    audiences: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def corpus_root(self) -> Path:
        return self.root / "corpus"

    @property
    def ledger_root(self) -> Path:
        return self.root / "ledger"

    @property
    def declared_tiers(self) -> frozenset[str]:
        """Every tier this instance recognizes: the reserved pair plus its
        own declared `tiers:` (spec/ledger.md §6.4)."""
        return frozenset(RESERVED_TIERS) | frozenset(self.tiers)

    def grants_for(self, audience: str) -> frozenset[str]:
        """The effective grant set for a named audience: its declared grants
        plus the `public` tier every audience carries implicitly
        (spec/athenaeum.md §2.3). An unknown audience name grants only
        `public`."""
        return frozenset(self.audiences.get(audience, ())) | {"public"}


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

    `spine` (spec/ledger.md §15.2) admits this dataset as an extension-chain
    root for the ledger's ontology layer — the flag `refdata.spine` checks
    before resolving an `extends:`/spine reference form against it. Default
    False: an ordinary reference dataset carries no ontology role.
    """

    dataset: str
    description: str
    latest: str  # the default snapshot tag — a key of snapshots
    snapshots: dict[str, Snapshot]  # tag -> Snapshot
    adapter: str | None = None  # explicit override; None derives from the mirror's mime overlay
    spine: bool = False  # admits this dataset as a spine extension-chain root (§15.2)


@dataclass(frozen=True)
class Asset:
    """A registered tool asset (spec/athenaeum.md §2.3, spec/corpus.md
    §12.3.6) — a payload the tooling injects or executes (the web capturer's
    SingleFile bundle), pinned exactly as a reference snapshot is: the same
    tag-keyed `snapshots`/`latest` grammar as `Reference`, none of its
    adapter or citation semantics — an asset's bytes are never a `ref://`
    surface, so this carries no `adapter` field at all.
    """

    name: str
    description: str
    latest: str  # the default snapshot tag — a key of snapshots
    snapshots: dict[str, Snapshot]  # tag -> Snapshot


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


def _load_tenancy(data: dict) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    """Parse the config's optional `tenancy:` block (spec/athenaeum.md §2.3):
    `tiers:` (a list of slugs beside the reserved public/private) and
    `audiences:` (name -> granted tiers, never `private`, `public` implicit).
    Absent block -> ((), {}) — the pre-tier binary, byte-identical."""
    tenancy = data.get("tenancy")
    if tenancy is None:
        return (), {}
    if not isinstance(tenancy, dict):
        raise ManifestError("manifest tenancy: expected a mapping")
    unknown = set(tenancy) - {"tiers", "audiences"}
    if unknown:
        raise ManifestError(f"manifest tenancy: unknown keys {sorted(unknown)}")

    tiers_raw = tenancy.get("tiers") or []
    if not isinstance(tiers_raw, list):
        raise ManifestError("manifest tenancy.tiers: expected a list of tier slugs")
    tiers: list[str] = []
    for t in tiers_raw:
        t = str(t)
        if not _SLUG_RE.match(t):
            raise ManifestError(f"manifest tenancy.tiers: {t!r} is not a slug")
        if t in RESERVED_TIERS:
            raise ManifestError(
                f"manifest tenancy.tiers: {t!r} collides with the reserved "
                f"{'/'.join(RESERVED_TIERS)} tier — declare a different name"
            )
        if t in tiers:
            raise ManifestError(f"manifest tenancy.tiers: duplicate tier {t!r}")
        tiers.append(t)
    declared = frozenset(RESERVED_TIERS) | frozenset(tiers)

    audiences_raw = tenancy.get("audiences") or {}
    if not isinstance(audiences_raw, dict):
        raise ManifestError("manifest tenancy.audiences: expected a name-keyed mapping")
    audiences: dict[str, tuple[str, ...]] = {}
    for name, grants in audiences_raw.items():
        name = str(name)
        if not _SLUG_RE.match(name):
            raise ManifestError(f"manifest tenancy.audiences: {name!r} is not a slug")
        # Plane names double as token-resolution results on the read surface
        # (Part I §5.1): an audience literally named `owner` or `public` would
        # shadow those planes — `private` is barred for symmetry with tiers.
        if name in ("public", "private", "owner"):
            raise ManifestError(
                f"manifest tenancy.audiences: {name!r} is reserved — "
                "plane names are never audience names (Part I §5.1)"
            )
        if name in audiences:
            raise ManifestError(f"manifest tenancy.audiences: duplicate audience {name!r}")
        grants = grants or []
        if not isinstance(grants, list):
            raise ManifestError(
                f"manifest tenancy.audiences.{name}: expected a list of tiers"
            )
        granted: list[str] = []
        for g in grants:
            g = str(g)
            if g == "private":
                raise ManifestError(
                    f"audience {name!r} granted 'private' — the floor is the owner's "
                    "alone, never grantable (Part III §6.4)"
                )
            if g not in declared:
                raise ManifestError(
                    f"manifest tenancy.audiences.{name}: {g!r} is not a declared tier "
                    "— declare it under tenancy.tiers, or grant 'public'"
                )
            granted.append(g)
        audiences[name] = tuple(granted)
    return tuple(tiers), audiences


def load_instance(root: Path) -> Instance:
    """Parse the instance config at *root*."""
    data = _read(root)
    tiers, audiences = _load_tenancy(data)
    declared = frozenset(RESERVED_TIERS) | frozenset(tiers)
    visibility = str(data.get("visibility") or "private")
    if visibility not in declared:
        raise ManifestError(
            f"visibility must be 'public', 'private', or a declared tier, got "
            f"{visibility!r}"
        )
    return Instance(root=root, name=str(data.get("name") or ""), visibility=visibility,
                    tiers=tiers, audiences=audiences)


def _parse_snapshots(context: str, snapshots_raw: object) -> dict[str, Snapshot]:
    """The tag-keyed `snapshots:` grammar shared by `references:` and
    `assets:` (spec/athenaeum.md §2.3): tag -> `Snapshot` (a 64-hex blake3
    `artifact`, plus the deprecated deployment-local `path:` override).
    `context` names the owning entry for error messages (e.g.
    `"references/{name}"` or `"assets/{name}"`)."""
    if not isinstance(snapshots_raw, dict) or not snapshots_raw:
        raise ManifestError(f"{context}: snapshots must be a non-empty tag-keyed mapping")
    snapshots: dict[str, Snapshot] = {}
    for tag, snap in snapshots_raw.items():
        tag = str(tag)
        if not _TAG_RE.match(tag):
            raise ManifestError(f"{context}: snapshot tag {tag!r} must match "
                                "^[a-z0-9][a-z0-9._-]*$")
        snap = snap or {}
        artifact = str(snap.get("artifact") or "")
        if not _ARTIFACT_RE.match(artifact):
            raise ManifestError(f"{context}/{tag}: artifact must be a 64-hex "
                                f"lowercase blake3, got {artifact!r}")
        # No existence check here — a declared path may live on a mount
        # that isn't up; presence is a resolver/status concern.
        path = snap.get("path")
        snapshots[tag] = Snapshot(artifact=artifact, path=str(path) if path else None)
    return snapshots


def _parse_latest(context: str, spec: dict, snapshots: dict[str, Snapshot]) -> str:
    """The `latest:` grammar shared by `references:` and `assets:`: declared,
    never inferred, and must name a key of the entry's own `snapshots`."""
    latest = str(spec.get("latest") or "")
    if not latest or latest not in snapshots:
        raise ManifestError(f"{context}: latest {latest!r} must name a key of snapshots")
    return latest


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
        spine_raw = spec.get("spine")
        if spine_raw is not None and not isinstance(spine_raw, bool):
            raise ManifestError(f"references/{name}: spine must be a boolean, got {spine_raw!r}")
        context = f"references/{name}"
        snapshots = _parse_snapshots(context, spec.get("snapshots") or {})
        latest = _parse_latest(context, spec, snapshots)
        refs.append(
            Reference(
                dataset=str(name),
                description=str(spec.get("description") or ""),
                adapter=adapter,
                spine=bool(spine_raw),
                latest=latest,
                snapshots=snapshots,
            )
        )
    return refs


def load_assets(root: Path) -> list[Asset]:
    """Parse the config's `assets:` section — registered tool assets
    (spec/athenaeum.md §2.3, spec/corpus.md §12.3.6): name-keyed entries
    sharing `references:`'s snapshot grammar (tag-keyed `snapshots:`, an
    explicit `latest:`), carrying no adapter or citation semantics — an
    unknown key (`adapter:`, `spine:`, the retired `mirror:`/`snapshot:`)
    is a load-time error rather than silently ignored."""
    entries = _read(root).get("assets") or {}
    if not isinstance(entries, dict):
        raise ManifestError("manifest assets: expected a name-keyed mapping")
    assets: list[Asset] = []
    for name, spec in entries.items():
        spec = spec or {}
        unknown = set(spec) - {"description", "latest", "snapshots"}
        if unknown:
            raise ManifestError(
                f"assets/{name}: unknown keys {sorted(unknown)} — assets carry no "
                "adapter/citation semantics (spec/athenaeum.md §2.3)"
            )
        context = f"assets/{name}"
        snapshots = _parse_snapshots(context, spec.get("snapshots") or {})
        latest = _parse_latest(context, spec, snapshots)
        assets.append(
            Asset(
                name=str(name),
                description=str(spec.get("description") or ""),
                latest=latest,
                snapshots=snapshots,
            )
        )
    return assets


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
