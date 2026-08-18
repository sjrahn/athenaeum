"""`materialize()`'s attached-location route + `canonical_index_path()`'s
corpus-root selection (spec/ledger.md §6.5, custody amendment v21 —
spec/corpus.md §12.1.1). Neither function opens an archive, so no optional
adapter dependency is needed here.
"""

from __future__ import annotations

from pathlib import Path

import blake3

from ath.manifest import Reference, Snapshot
from corpus import config as config_mod
from corpus import locationindex
from refdata import canonical_index_path, materialize


def _corpus(tmp_path: Path, name: str = "corpus") -> Path:
    root = tmp_path / name
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _ref(tag: str, artifact: str, *, latest: str | None = None) -> Reference:
    return Reference(
        dataset="testloc", description="test mirror", adapter="zim",
        latest=latest or tag, snapshots={tag: Snapshot(artifact=artifact)},
    )


def _attach(root: Path, data_dir: Path, mirror_bytes: bytes) -> tuple[Path, str]:
    """Registers `data_dir` as an attached location on `root`, drops one
    mirror file into it, and attests it into the location index — no
    `artifacts/` copy anywhere. Returns `(mirror path, its blake3)`."""
    data_dir.mkdir(parents=True, exist_ok=True)
    mirror = data_dir / "mirror.bin"
    mirror.write_bytes(mirror_bytes)
    (root / "corpus.toml").write_text(
        f'[[corpus.location]]\nname = "data"\nkind = "attached"\npath = "{data_dir}"\n',
        encoding="utf-8",
    )
    cfg = config_mod.load_config(root)
    (loc,) = cfg.locations
    locationindex.attest_location(root, loc)
    digest = blake3.blake3(mirror_bytes).hexdigest()
    return mirror, digest


# --- materialize: attached-location route -----------------------------------


def test_materialize_resolves_through_location_index(tmp_path: Path) -> None:
    root = _corpus(tmp_path)
    mirror, digest = _attach(root, tmp_path / "data", b"attached mirror bytes")
    ref = _ref("t", digest)
    resolved = materialize(ref, "t", corpora_roots=(root,))
    assert resolved == mirror


def test_materialize_prefers_artifacts_store_over_location_route(tmp_path: Path) -> None:
    """Both an `artifacts/` copy and a location-indexed copy exist for the
    same hash (distinct content each, so which one served is provable) — the
    co-located store wins, exactly matching `_materialize_with_root`'s
    documented try-order."""
    root = _corpus(tmp_path)
    digest = "a" * 64
    store_file = root / "artifacts" / digest[:2] / f"{digest}.bin"
    store_file.parent.mkdir(parents=True)
    store_file.write_bytes(b"store bytes")

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    attached = data_dir / "mirror.bin"
    attached.write_bytes(b"attached bytes")
    (root / "corpus.toml").write_text(
        f'[[corpus.location]]\nname = "data"\nkind = "attached"\npath = "{data_dir}"\n',
        encoding="utf-8",
    )
    cfg = config_mod.load_config(root)
    (loc,) = cfg.locations
    locationindex.attest_location(root, loc)
    # Force the location row onto the store's hash (mismatched real bytes is
    # fine — route_for only reads its own row + stat pins, never opens the
    # store file).
    with locationindex.open_index(root) as conn:
        conn.execute("UPDATE locations SET hash = ? WHERE relpath = 'mirror.bin'", (digest,))

    ref = _ref("t", digest)
    assert materialize(ref, "t", corpora_roots=(root,)) == store_file


def test_materialize_unresolved_hash_is_a_miss(tmp_path: Path) -> None:
    root = _corpus(tmp_path)
    _attach(root, tmp_path / "data", b"attached mirror bytes")
    ref = _ref("t", "b" * 64)  # a hash nothing attests
    assert materialize(ref, "t", corpora_roots=(root,)) is None


# --- canonical_index_path: corpus-root selection -----------------------------


def test_canonical_index_path_under_location_resolved_root(tmp_path: Path) -> None:
    root = _corpus(tmp_path)
    _mirror, digest = _attach(root, tmp_path / "data", b"attached mirror bytes")
    ref = _ref("t", digest)
    path = canonical_index_path(ref, "t", corpora_roots=(root,))
    assert path == root / "cache" / "refidx" / f"{digest}.sqlite"


def test_canonical_index_path_falls_back_to_first_root_for_path_override(
    tmp_path: Path,
) -> None:
    """A mirror materialized only via the deprecated `path:` override — no
    corpus root holds the bytes — still homes its sidecar under the FIRST
    registered corpus root regardless (spec/ledger.md §6.5 v21: "the
    deployment's corpus cache is the right home even while bytes read in
    place")."""
    root1 = _corpus(tmp_path, name="c1")
    root2 = _corpus(tmp_path, name="c2")
    override = tmp_path / "override.bin"
    override.write_bytes(b"whatever")
    ref = Reference(
        dataset="testloc", description="test", adapter="zim", latest="t",
        snapshots={"t": Snapshot(artifact="c" * 64, path=str(override))},
    )
    path = canonical_index_path(ref, "t", corpora_roots=(root1, root2))
    assert path == root1 / "cache" / "refidx" / f"{'c' * 64}.sqlite"


def test_canonical_index_path_none_with_no_corpora_roots() -> None:
    ref = _ref("t", "d" * 64)
    assert canonical_index_path(ref, "t", corpora_roots=()) is None


def test_canonical_index_path_never_creates_refidx_dir(tmp_path: Path) -> None:
    root = _corpus(tmp_path)
    ref = _ref("t", "e" * 64)  # nothing materialized anywhere
    canonical_index_path(ref, "t", corpora_roots=(root,))
    assert not (root / "cache" / "refidx").exists()
