"""`ath ref index` — the sidecar-index CLI verb for adapters that need one
(`osm-pbf`; spec/ledger.md §6.5), plus the `MirrorUnindexed` handling it
motivates in `resolve`/`search` and the `status` verb's `index=` column.
Needs the optional `osmium` dependency — gated at module scope, mirroring
`tests/test_refdata_osm.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

osmium = pytest.importorskip("osmium")

from ath._cli import main  # noqa: E402

_HASH_OSM = "a" * 64
_HASH_ZIM = "b" * 64

# One tagged node WITH a name, one tagged node WITHOUT a name, one UNTAGGED
# node (dropped by EmptyTagFilter — never reaches the index), one tagged way
# with a name, one tagged relation with no name: 4 tagged elements, 2 named
# (matches `tests/test_refdata_osm.py`'s fixture, kept as a local copy here
# per dispatch — own file, own copy).
_NODE_NAMED = (1, -79.123456, 43.654321, {"name": "Test Location", "amenity": "cafe"})
_NODE_UNNAMED = (2, -79.5, 43.5, {"amenity": "bench"})
_NODE_UNTAGGED = (3, -79.6, 43.6, {})


def _build_pbf(path: Path) -> None:
    writer = osmium.SimpleWriter(str(path))
    try:
        for node_id, lon, lat, tags in (_NODE_NAMED, _NODE_UNNAMED, _NODE_UNTAGGED):
            writer.add_node(
                osmium.osm.mutable.Node(id=node_id, location=(lon, lat), tags=tags)
            )
        writer.add_way(
            osmium.osm.mutable.Way(
                id=10, nodes=[1, 2], tags={"name": "Test Way", "highway": "residential"}
            )
        )
        writer.add_relation(
            osmium.osm.mutable.Relation(
                id=100, members=[("w", 10, "outer")], tags={"type": "multipolygon"}
            )
        )
    finally:
        writer.close()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A manifest registering two datasets: `osm-test` (adapter `osm-pbf`, a
    path-materialized fixture pbf, born unindexed — the sidecar hasn't been
    built yet) and `zim-test` (adapter `zim`, no real mirror bytes needed:
    `ath ref index` on it is expected to fail before ever materializing
    anything, since zim carries no `build_index` at all — it is born
    indexed)."""
    pbf_path = tmp_path / "mirror.osm.pbf"
    _build_pbf(pbf_path)

    manifest = f"""\
org: https://x.test/athenaeum
ledger:
  ledger: {{}}
references:
  osm-test:
    description: test osm mirror
    adapter: osm-pbf
    latest: t
    snapshots:
      t: {{ artifact: {_HASH_OSM}, path: {pbf_path} }}
  zim-test:
    description: zim dataset, born indexed, no sidecar
    adapter: zim
    latest: t
    snapshots:
      t: {{ artifact: {_HASH_ZIM} }}
"""
    (tmp_path / "athenaeum.yaml").write_text(manifest, encoding="utf-8")
    return tmp_path


def _sidecar_path(pbf_path: Path) -> Path:
    """Local knowledge of the adapter's sidecar suffix, for asserting the
    file landed — the CLI itself never hardcodes this (§6.5, the adapter's
    business alone)."""
    return Path(str(pbf_path) + ".refidx")


def _status_rows(out: str) -> dict[str, list[str]]:
    """Group `ath ref status` output into dataset -> [snapshot row, …]."""
    blocks: dict[str, list[str]] = {}
    current = ""
    for line in out.splitlines():
        if not line.startswith(" "):
            current = line.split()[0]
            blocks[current] = []
        else:
            blocks[current].append(line.strip())
    return blocks


# --- resolve/search before indexing: MirrorUnindexed ------------------------


def test_resolve_before_indexing_reports_unindexed(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["ref", "resolve", "ref://osm-test/node/1", "--root", str(root)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "mirror not indexed" in err
    assert "ath ref index" in err


def test_search_before_indexing_reports_unindexed(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["ref", "search", "osm-test", "Location", "--root", str(root)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "mirror not indexed" in err
    assert "ath ref index" in err


# --- ath ref index ------------------------------------------------------------


def test_index_builds_and_reports_counts(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["ref", "index", "osm-test", "--root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip() == "osm-test@t: indexed 4 element(s) (2 named)"
    assert _sidecar_path(root / "mirror.osm.pbf").is_file()


def test_index_idempotent(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ref", "index", "osm-test", "--root", str(root)]) == 0
    capsys.readouterr()
    assert main(["ref", "index", "osm-test", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "indexed 4 element(s) (2 named)" in out


def test_index_adapter_needs_no_sidecar(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["ref", "index", "zim-test", "--root", str(root)])
    assert rc == 1
    assert "needs no sidecar index" in capsys.readouterr().err


def test_index_unregistered_dataset(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["ref", "index", "unknown-dataset", "--root", str(root)])
    assert rc == 1
    assert "unregistered dataset" in capsys.readouterr().err


# --- resolve/search after indexing -------------------------------------------


def test_resolve_and_search_after_indexing(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["ref", "index", "osm-test", "--root", str(root)]) == 0
    capsys.readouterr()

    rc = main(["ref", "resolve", "ref://osm-test/node/1", "--root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0].startswith("osm-test@t")
    body_lines = out.split("\n\n", 1)[1].splitlines()
    assert body_lines[0] == "node 1"
    assert "name=Test Location" in body_lines

    rc = main(["ref", "search", "osm-test", "Location", "--root", str(root)])
    assert rc == 0
    captured = capsys.readouterr()
    # Three columns: node/1 carries context (amenity=cafe + rounded coords) —
    # this is the search-hit disambiguation column (athenaeum#203).
    assert captured.out.splitlines() == ["node/1\tTest Location\tamenity=cafe @43.654,-79.123"]


# --- status --------------------------------------------------------------


def test_status_index_state_before_and_after(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["ref", "status", "--root", str(root)]) == 0
    before = _status_rows(capsys.readouterr().out)
    assert any("index=missing" in row for row in before["osm-test"])
    assert not any("index=" in row for row in before["zim-test"])

    assert main(["ref", "index", "osm-test", "--root", str(root)]) == 0
    capsys.readouterr()

    assert main(["ref", "status", "--root", str(root)]) == 0
    after = _status_rows(capsys.readouterr().out)
    assert any("index=indexed" in row for row in after["osm-test"])
    assert not any("index=" in row for row in after["zim-test"])


# --- canonical cache/refidx/ path via a registered corpus root (21) --------
#
# `root` (above) registers no `corpora:` at all — its sidecar lands beside
# the mirror, the legacy/bare-library path. These fixtures instead register
# a corpus root with an ATTACHED LOCATION holding the mirror (no `artifacts/`
# copy, no `path:` override) — the real v21 shape: `ath ref index` must build
# the sidecar at that corpus root's `cache/refidx/<artifact>.sqlite`, and
# `status`/`resolve`/`search` must read it from there.


@pytest.fixture
def root_with_corpus(tmp_path: Path) -> tuple[Path, Path, str]:
    """Returns (workspace root, corpus root, mirror artifact blake3)."""
    import blake3

    from corpus import config as config_mod
    from corpus import locationindex

    corpus_root = tmp_path / "corpus"
    (corpus_root / "records").mkdir(parents=True)
    (corpus_root / "schema").mkdir()

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    mirror = data_dir / "extract.osm.pbf"
    _build_pbf(mirror)
    digest = blake3.blake3(mirror.read_bytes()).hexdigest()

    (corpus_root / "corpus.toml").write_text(
        f'[[corpus.location]]\nname = "data"\nkind = "attached"\npath = "{data_dir}"\n',
        encoding="utf-8",
    )
    cfg = config_mod.load_config(corpus_root)
    (loc,) = cfg.locations
    locationindex.attest_location(corpus_root, loc)

    manifest = f"""\
org: https://x.test/athenaeum
corpora:
  corpus:
    visibility: public
    path: corpus
ledger:
  ledger: {{}}
references:
  osm-loc:
    description: osm mirror resolved through an attached location
    adapter: osm-pbf
    latest: t
    snapshots:
      t: {{ artifact: {digest} }}
"""
    (tmp_path / "athenaeum.yaml").write_text(manifest, encoding="utf-8")
    return tmp_path, corpus_root, digest


def test_index_builds_at_canonical_cache_refidx_path(
    root_with_corpus: tuple[Path, Path, str],
) -> None:
    workspace, corpus_root, digest = root_with_corpus
    assert main(["ref", "index", "osm-loc", "--root", str(workspace)]) == 0
    canonical = corpus_root / "cache" / "refidx" / f"{digest}.sqlite"
    assert canonical.is_file()
    # never beside the mirror for a location-resolved snapshot
    assert not (corpus_root / "data" / "extract.osm.pbf.refidx").exists()


def test_resolve_after_indexing_via_location_route(
    root_with_corpus: tuple[Path, Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    workspace, _corpus_root, _digest = root_with_corpus
    assert main(["ref", "index", "osm-loc", "--root", str(workspace)]) == 0
    capsys.readouterr()
    rc = main(["ref", "resolve", "ref://osm-loc/node/1", "--root", str(workspace)])
    assert rc == 0
    assert "Test Location" in capsys.readouterr().out


def test_status_shows_store_for_location_resolved_mirror(
    root_with_corpus: tuple[Path, Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    workspace, _corpus_root, _digest = root_with_corpus
    assert main(["ref", "status", "--root", str(workspace)]) == 0
    rows = _status_rows(capsys.readouterr().out)
    fields = [row.split("  ") for row in rows["osm-loc"]]
    assert any("store" in f for f in fields)
