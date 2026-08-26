"""Instance-registered tool assets (`corpus.assets`, spec/athenaeum.md §2.3,
spec/corpus.md §12.3.6) — the local `athenaeum.yaml` `assets:` reader and the
artifact/custody materialization it feeds to the SingleFile capture loader.

This is a LOCAL reader (not `ath.manifest`'s — see `corpus/assets.py`'s module
docstring for why), so its config-parsing tests intentionally mirror
`ath.manifest`'s `references:` tests without importing that module."""

from __future__ import annotations

import yaml

from corpus import assets, paths


def _instance(tmp_path, *, manifest: dict | None = None):
    """A minimal instance: `athenaeum.yaml` at the root (dumped from `manifest`,
    or absent when `manifest` is None) + an empty `corpus/` beneath it. Returns
    `(instance_root, corpus_root)`."""
    instance = tmp_path / "instance"
    corpus_root = instance / "corpus"
    corpus_root.mkdir(parents=True)
    if manifest is not None:
        (instance / "athenaeum.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return instance, corpus_root


_DIGEST = "a1" * 32


# ---------- load_asset: ordinary misses ---------- #


def test_load_asset_no_instance_config_above_root(tmp_path):
    bare = tmp_path / "bare-corpus"
    bare.mkdir()
    assert assets.load_asset(bare, "singlefile") is None


def test_load_asset_no_assets_block(tmp_path):
    _instance_root, corpus_root = _instance(tmp_path, manifest={"name": "test"})
    assert assets.load_asset(corpus_root, "singlefile") is None


def test_load_asset_no_entry_of_that_name(tmp_path):
    _instance_root, corpus_root = _instance(
        tmp_path,
        manifest={
            "assets": {"other-tool": {"latest": "v1", "snapshots": {"v1": {"artifact": _DIGEST}}}}
        },
    )
    assert assets.load_asset(corpus_root, "singlefile") is None


# ---------- load_asset: found + parsed ---------- #


def test_load_asset_parses_latest_and_snapshots(tmp_path):
    _instance_root, corpus_root = _instance(
        tmp_path,
        manifest={
            "assets": {
                "singlefile": {
                    "description": "the SingleFile snapshot engine",
                    "latest": "v2",
                    "snapshots": {
                        "v1": {"artifact": "b2" * 32},
                        "v2": {"artifact": _DIGEST},
                    },
                }
            }
        },
    )
    asset = assets.load_asset(corpus_root, "singlefile")
    assert asset is not None
    assert asset.name == "singlefile"
    assert asset.description == "the SingleFile snapshot engine"
    assert asset.latest == "v2"
    assert asset.snapshots["v2"].artifact == _DIGEST
    assert asset.snapshots["v1"].artifact == "b2" * 32


def test_load_asset_walks_up_from_a_corpus_subdirectory(tmp_path):
    """Discovery walks up exactly like `ath.manifest.find_root` — a corpus root
    nested under the instance still finds the config above it."""
    _instance_root, corpus_root = _instance(
        tmp_path,
        manifest={
            "assets": {"singlefile": {"latest": "v1", "snapshots": {"v1": {"artifact": _DIGEST}}}}
        },
    )
    nested = corpus_root / "records" / "a1"
    nested.mkdir(parents=True)
    assert assets.load_asset(nested, "singlefile") is not None


# ---------- load_asset: malformed registrations raise AssetError ---------- #


def test_load_asset_rejects_non_mapping_assets_block(tmp_path):
    _instance_root, corpus_root = _instance(tmp_path, manifest={"assets": ["not-a-mapping"]})
    try:
        assets.load_asset(corpus_root, "singlefile")
        raise AssertionError("expected AssetError")
    except assets.AssetError:
        pass


def test_load_asset_rejects_empty_snapshots(tmp_path):
    _instance_root, corpus_root = _instance(
        tmp_path, manifest={"assets": {"singlefile": {"latest": "v1", "snapshots": {}}}}
    )
    try:
        assets.load_asset(corpus_root, "singlefile")
        raise AssertionError("expected AssetError")
    except assets.AssetError:
        pass


def test_load_asset_rejects_bad_tag(tmp_path):
    _instance_root, corpus_root = _instance(
        tmp_path,
        manifest={
            "assets": {"singlefile": {"latest": "V1", "snapshots": {"V1": {"artifact": _DIGEST}}}}
        },
    )
    try:
        assets.load_asset(corpus_root, "singlefile")
        raise AssertionError("expected AssetError")
    except assets.AssetError:
        pass


def test_load_asset_rejects_bad_artifact_hash(tmp_path):
    _instance_root, corpus_root = _instance(
        tmp_path,
        manifest={
            "assets": {"singlefile": {"latest": "v1", "snapshots": {"v1": {"artifact": "not-hex"}}}}
        },
    )
    try:
        assets.load_asset(corpus_root, "singlefile")
        raise AssertionError("expected AssetError")
    except assets.AssetError:
        pass


def test_load_asset_rejects_latest_not_naming_a_snapshot(tmp_path):
    _instance_root, corpus_root = _instance(
        tmp_path,
        manifest={
            "assets": {
                "singlefile": {"latest": "v2", "snapshots": {"v1": {"artifact": _DIGEST}}}
            }
        },
    )
    try:
        assets.load_asset(corpus_root, "singlefile")
        raise AssertionError("expected AssetError")
    except assets.AssetError:
        pass


# ---------- materialize: the corpus store/custody routes ---------- #


def test_materialize_finds_co_located_artifact(tmp_path):
    corpus_root = tmp_path / "corpus"
    shard_dir = corpus_root / "artifacts" / paths.shard(_DIGEST)
    shard_dir.mkdir(parents=True)
    dest = shard_dir / f"{_DIGEST}.js"
    dest.write_bytes(b"bundle bytes")
    assert assets.materialize(corpus_root, _DIGEST) == dest


def test_materialize_ignores_interrupted_part_write(tmp_path):
    corpus_root = tmp_path / "corpus"
    shard_dir = corpus_root / "artifacts" / paths.shard(_DIGEST)
    shard_dir.mkdir(parents=True)
    (shard_dir / f"{_DIGEST}.js.part").write_bytes(b"half-written")
    assert assets.materialize(corpus_root, _DIGEST) is None


def test_materialize_finds_configured_store_location(tmp_path):
    corpus_root = tmp_path / "corpus"
    (corpus_root / "records").mkdir(parents=True)
    (corpus_root / "schema").mkdir()
    store = tmp_path / "bulk-store"
    (corpus_root / "corpus.toml").write_text(
        f'[[corpus.location]]\nname = "bulk"\nkind = "store"\npath = "{store}"\n',
        encoding="utf-8",
    )
    dest = store / paths.shard(_DIGEST) / f"{_DIGEST}.js"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"bundle bytes")
    assert assets.materialize(corpus_root, _DIGEST) == dest


def test_materialize_nowhere_found_is_none(tmp_path):
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()
    assert assets.materialize(corpus_root, _DIGEST) is None
