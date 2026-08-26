"""Instance-registered tool assets (spec/athenaeum.md §2.3, spec/corpus.md §12.3.6).

An `assets:` entry in the instance config (`athenaeum.yaml`, TRACKED, at the instance
root — one level above the corpus root) registers a payload the tooling injects or
executes: its bytes are an ordinary corpus artifact — captured with provenance,
content-addressed, resolved through custody — pinned by artifact blake3 through a
`latest` tag exactly as a `references:` snapshot is, with none of the citation
semantics (`ref://` never resolves an asset).

This is a LOCAL reader, deliberately not `ath.manifest`'s: the corpus package sits
below `ath` in the reference graph (spec/athenaeum.md §2.4, "corpus ── ▶ (nothing
above it)"), and nothing under `corpus/` imports `ath` today — so this module walks
up from the corpus root to the nearest `athenaeum.yaml` itself and parses only the
`assets:` block, duplicating (deliberately, not sharing) the tag/artifact grammar
`ath.manifest.load_references` already validates for `references:`.

Two entry points, mirroring `refdata.materialize`'s "resolution is downward" shape
minus the reference-only `ref://` machinery:

- `load_asset(corpus_root, name)` — the registered entry (`latest` tag + its
  snapshots), or `None` when there is no instance config above `corpus_root` or it
  registers no asset named `name` — both ordinary misses, never raised. Raises
  `AssetError` only when `name` IS registered but malformed.
- `materialize(corpus_root, artifact_hash)` — the bytes of `artifact_hash` on local
  disk, or `None` when nowhere materialized in this environment. Same store/location
  route order the corpus store already resolves artifacts through: the co-located
  `artifacts/<shard>/` tree, every configured store location, then the attached-
  location index — read-only, never fetches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import locationindex, paths, placement

MANIFEST_NAME = "athenaeum.yaml"

_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_ARTIFACT_RE = re.compile(r"^[0-9a-f]{64}$")


class AssetError(RuntimeError):
    """A registered instance asset is declared but malformed."""


@dataclass(frozen=True)
class AssetSnapshot:
    """One registered build of an asset — `artifact` is its blake3 (spec §2.3)."""

    artifact: str  # 64-hex blake3


@dataclass(frozen=True)
class Asset:
    """A registered instance asset (`assets:` in `athenaeum.yaml`, spec §2.3)."""

    name: str
    description: str
    latest: str  # the default snapshot tag — a key of snapshots
    snapshots: dict[str, AssetSnapshot]  # tag -> AssetSnapshot


def _find_instance_root(start: Path) -> Path | None:
    """Walk up from `start` to the nearest directory holding `athenaeum.yaml`. `None`
    when none is found — e.g. a bare corpus exercised outside an instance (testdata,
    library use); that is an ordinary "no assets registered" miss, never an error."""
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / MANIFEST_NAME).is_file():
            return candidate
    return None


def load_asset(corpus_root: Path, name: str) -> Asset | None:
    """Parse the `name` entry of the instance config's `assets:` block, walking up
    from `corpus_root` to find `athenaeum.yaml`.

    `None` when there is no instance config above `corpus_root`, or the config
    registers no asset named `name` — both ordinary misses (spec/corpus.md §12.3.6:
    "with no asset registered ... capture degrades"), never raised. Raises
    `AssetError` only when `name` IS registered but malformed."""
    root = _find_instance_root(corpus_root)
    if root is None:
        return None
    manifest_path = root / MANIFEST_NAME
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise AssetError(f"{manifest_path}: expected a mapping")
    assets = data.get("assets") or {}
    if not isinstance(assets, dict):
        raise AssetError("manifest assets: expected a name-keyed mapping")
    spec = assets.get(name)
    if spec is None:
        return None
    spec = spec or {}
    snapshots_raw = spec.get("snapshots") or {}
    if not isinstance(snapshots_raw, dict) or not snapshots_raw:
        raise AssetError(f"assets/{name}: snapshots must be a non-empty tag-keyed mapping")
    snapshots: dict[str, AssetSnapshot] = {}
    for tag, snap in snapshots_raw.items():
        tag = str(tag)
        if not _TAG_RE.match(tag):
            raise AssetError(
                f"assets/{name}: snapshot tag {tag!r} must match ^[a-z0-9][a-z0-9._-]*$ "
                "(rides after '@' wherever an asset tag is cited)"
            )
        snap = snap or {}
        artifact = str(snap.get("artifact") or "")
        if not _ARTIFACT_RE.match(artifact):
            raise AssetError(
                f"assets/{name}/{tag}: artifact must be a 64-hex lowercase blake3, "
                f"got {artifact!r}"
            )
        snapshots[tag] = AssetSnapshot(artifact=artifact)
    latest = str(spec.get("latest") or "")
    if not latest or latest not in snapshots:
        raise AssetError(f"assets/{name}: latest {latest!r} must name a key of snapshots")
    return Asset(
        name=name,
        description=str(spec.get("description") or ""),
        latest=latest,
        snapshots=snapshots,
    )


def materialize(corpus_root: Path, artifact_hash: str) -> Path | None:
    """The bytes of `artifact_hash` on local disk, or `None` if nowhere materialized
    in this environment (spec/corpus.md §12.3.6: "its bytes not materialized ...
    capture degrades"). A registered asset is an ordinary corpus artifact, so this
    walks the same routes the corpus store already resolves artifact bytes through —
    the co-located `artifacts/<shard>/` tree, every configured store location, then
    the attached-location index (spec/corpus.md §12.1.1) — cheapest and most-local
    first, read-only, never fetches."""
    shard_dir = corpus_root / "artifacts" / paths.shard(artifact_hash)
    if shard_dir.is_dir():
        for p in sorted(shard_dir.glob(f"{artifact_hash}.*")):
            # `.part` is `placement.put_at`'s temp suffix for an interrupted write —
            # never servable bytes.
            if p.is_file() and p.suffix != ".part":
                return p
    for loc in placement.store_locations(corpus_root):
        loc_shard_dir = loc.path / paths.shard(artifact_hash)
        if not loc_shard_dir.is_dir():
            continue
        for p in sorted(loc_shard_dir.glob(f"{artifact_hash}.*")):
            if p.is_file() and p.suffix != ".part":
                return p
    return locationindex.route_for(corpus_root, artifact_hash)
