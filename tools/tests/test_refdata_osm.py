"""The `osm-pbf` format adapter (spec/ledger.md §6.5): sidecar-index build,
native id resolution, and search against an OpenStreetMap PBF extract.
Needs the optional `osmium` dependency (the `osm` extra) — gated at module
scope so environments without it report a clean skip, not a failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

osmium = pytest.importorskip("osmium")

import refdata  # noqa: E402
from ath.manifest import Reference, Snapshot  # noqa: E402
from refdata import MirrorCorrupt, MirrorUnindexed  # noqa: E402
from refdata.adapters import adapter_available, osm_pbf  # noqa: E402
from refdata.errors import EntryNotFound  # noqa: E402

# --- fixture ------------------------------------------------------------
#
# One tagged node WITH a name, one tagged node WITHOUT a name, one UNTAGGED
# node (dropped by EmptyTagFilter — never reaches the index), one tagged way
# with a name, one tagged relation with no name. Node 1's name ("Test
# Location") and way 10's name ("Test Way") deliberately share the word
# "Test" — that's what the limit/search tests below exercise. Node 4 and way
# 11 are named but carry no `_CONTEXT_TAGS` key — "Bare" is their shared
# word — exercising the coords-only (node) / None (way) context outcomes.

_NODE_NAMED = (1, -79.123456, 43.654321, {"name": "Test Location", "amenity": "cafe"})
_NODE_UNNAMED = (2, -79.5, 43.5, {"amenity": "bench"})
_NODE_UNTAGGED = (3, -79.6, 43.6, {})
_NODE_NO_CONTEXT_TAG = (4, -79.7, 43.7, {"name": "Bare Node"})


def _build_pbf(path: Path) -> None:
    writer = osmium.SimpleWriter(str(path))
    try:
        for node_id, lon, lat, tags in (
            _NODE_NAMED, _NODE_UNNAMED, _NODE_UNTAGGED, _NODE_NO_CONTEXT_TAG,
        ):
            writer.add_node(
                osmium.osm.mutable.Node(id=node_id, location=(lon, lat), tags=tags)
            )
        writer.add_way(
            osmium.osm.mutable.Way(
                id=10, nodes=[1, 2], tags={"name": "Test Way", "highway": "residential"}
            )
        )
        writer.add_way(
            osmium.osm.mutable.Way(
                id=11, nodes=[1, 2], tags={"name": "Bare Way"}
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
def pbf_path(tmp_path: Path) -> Path:
    p = tmp_path / "mirror.osm.pbf"
    _build_pbf(p)
    return p


@pytest.fixture
def indexed_pbf_path(pbf_path: Path) -> Path:
    osm_pbf.build_index(pbf_path)
    return pbf_path


def _ref(
    tag: str, artifact: str, *, path: str | None = None, latest: str | None = None
) -> Reference:
    return Reference(
        dataset="testosm", description="test mirror", adapter="osm-pbf",
        latest=latest or tag, snapshots={tag: Snapshot(artifact=artifact, path=path)},
    )


# --- adapter registration -------------------------------------------------


def test_adapter_available() -> None:
    assert adapter_available("osm-pbf") is True


# --- resolve: exact text rendering ----------------------------------------


def test_resolve_named_node(indexed_pbf_path: Path) -> None:
    handle = osm_pbf.open_archive(indexed_pbf_path)
    result = osm_pbf.resolve_entry(handle, "node/1")
    assert result.canonical_id == "node/1"
    assert result.title == "Test Location"
    assert result.content_type == "text/plain"
    assert result.text == (
        "node 1\nlat 43.6543210\nlon -79.1234560\namenity=cafe\nname=Test Location"
    )


def test_resolve_unnamed_node(indexed_pbf_path: Path) -> None:
    handle = osm_pbf.open_archive(indexed_pbf_path)
    result = osm_pbf.resolve_entry(handle, "node/2")
    assert result.title is None
    assert result.text == "node 2\nlat 43.5000000\nlon -79.5000000\namenity=bench"


def test_resolve_way(indexed_pbf_path: Path) -> None:
    handle = osm_pbf.open_archive(indexed_pbf_path)
    result = osm_pbf.resolve_entry(handle, "way/10")
    assert result.canonical_id == "way/10"
    assert result.title == "Test Way"
    assert result.text == "way 10\nhighway=residential\nname=Test Way"


def test_resolve_relation(indexed_pbf_path: Path) -> None:
    handle = osm_pbf.open_archive(indexed_pbf_path)
    result = osm_pbf.resolve_entry(handle, "relation/100")
    assert result.canonical_id == "relation/100"
    assert result.title is None
    assert result.text == "relation 100\ntype=multipolygon"


def test_untagged_node_not_found(indexed_pbf_path: Path) -> None:
    handle = osm_pbf.open_archive(indexed_pbf_path)
    with pytest.raises(EntryNotFound):
        osm_pbf.resolve_entry(handle, "node/3")


@pytest.mark.parametrize("native_id", ["foo/1", "node/abc", "12", "node/", "/1"])
def test_grammar_violations_not_found(indexed_pbf_path: Path, native_id: str) -> None:
    handle = osm_pbf.open_archive(indexed_pbf_path)
    with pytest.raises(EntryNotFound):
        osm_pbf.resolve_entry(handle, native_id)


# --- index state: missing / stale -----------------------------------------


def test_missing_index_raises_from_resolve_and_search(pbf_path: Path) -> None:
    assert osm_pbf.index_state(pbf_path) == "missing"
    handle = osm_pbf.open_archive(pbf_path)
    with pytest.raises(MirrorUnindexed):
        osm_pbf.resolve_entry(handle, "node/1")
    with pytest.raises(MirrorUnindexed):
        osm_pbf.search_entries(handle, "Test", limit=10)


def test_stale_index_raises_from_resolve_and_search(indexed_pbf_path: Path) -> None:
    assert osm_pbf.index_state(indexed_pbf_path) == "indexed"
    with open(indexed_pbf_path, "ab") as f:
        f.write(b"\x00")
    assert osm_pbf.index_state(indexed_pbf_path) == "stale"

    handle = osm_pbf.open_archive(indexed_pbf_path)
    with pytest.raises(MirrorUnindexed):
        osm_pbf.resolve_entry(handle, "node/1")
    with pytest.raises(MirrorUnindexed):
        osm_pbf.search_entries(handle, "Test", limit=10)


# --- corrupt mirror ---------------------------------------------------------


def test_corrupt_mirror_raises_from_open_archive(tmp_path: Path) -> None:
    bad = tmp_path / "corrupt.osm.pbf"
    bad.write_bytes(b"not a pbf file, just garbage" * 100)
    with pytest.raises(MirrorCorrupt):
        osm_pbf.open_archive(bad)


def test_corrupt_mirror_raises_from_build_index(tmp_path: Path) -> None:
    bad = tmp_path / "corrupt.osm.pbf"
    bad.write_bytes(b"not a pbf file, just garbage" * 100)
    with pytest.raises(MirrorCorrupt):
        osm_pbf.build_index(bad)


# --- search -----------------------------------------------------------------


def test_search_finds_node_by_unique_name_word(indexed_pbf_path: Path) -> None:
    handle = osm_pbf.open_archive(indexed_pbf_path)
    hits = osm_pbf.search_entries(handle, "Location", limit=10)
    assert len(hits) == 1
    assert hits[0].native_id == "node/1"
    assert hits[0].title == "Test Location"


def test_search_limit_respected(indexed_pbf_path: Path) -> None:
    """"Test" is a word in both node/1's and way/10's names."""
    handle = osm_pbf.open_archive(indexed_pbf_path)
    hits = osm_pbf.search_entries(handle, "Test", limit=10)
    assert {h.native_id for h in hits} == {"node/1", "way/10"}
    limited = osm_pbf.search_entries(handle, "Test", limit=1)
    assert len(limited) == 1


def test_search_fulltext_mode_returns_empty_without_touching_index(pbf_path: Path) -> None:
    """`fulltext` is a structural absence for this format — it returns `[]`
    unconditionally, even against a mirror with no sidecar index at all."""
    assert osm_pbf.index_state(pbf_path) == "missing"
    handle = osm_pbf.open_archive(pbf_path)
    assert osm_pbf.search_entries(handle, "Test", limit=10, mode="fulltext") == []


def test_search_unknown_mode_raises(indexed_pbf_path: Path) -> None:
    handle = osm_pbf.open_archive(indexed_pbf_path)
    with pytest.raises(ValueError):
        osm_pbf.search_entries(handle, "Test", limit=10, mode="not-a-real-mode")


@pytest.mark.parametrize("query", ["", "   ", "!!!", "---"])
def test_search_empty_or_punctuation_query_returns_empty(
    indexed_pbf_path: Path, query: str
) -> None:
    handle = osm_pbf.open_archive(indexed_pbf_path)
    assert osm_pbf.search_entries(handle, query, limit=10) == []


# --- search: context ---------------------------------------------------------


def test_search_node_context_has_classifying_tag_and_coords(indexed_pbf_path: Path) -> None:
    """Node 1 carries `amenity=cafe` (a `_CONTEXT_TAGS` key) — its context
    is the tag plus `@lat,lon` rounded to 3 decimals."""
    handle = osm_pbf.open_archive(indexed_pbf_path)
    hits = osm_pbf.search_entries(handle, "Location", limit=10)
    assert len(hits) == 1
    assert hits[0].native_id == "node/1"
    assert hits[0].context == "amenity=cafe @43.654,-79.123"


def test_search_way_context_has_classifying_tag_no_coords(indexed_pbf_path: Path) -> None:
    """Way 10 carries `highway=residential` but ways carry no lat/lon — its
    context is the tag alone, with no `@` part. Both query tokens are
    required ("Test" alone also hits node/1; "Way" alone also hits way/11)
    to isolate way/10 exactly."""
    handle = osm_pbf.open_archive(indexed_pbf_path)
    hits = osm_pbf.search_entries(handle, "Test Way", limit=10)
    assert len(hits) == 1
    assert hits[0].native_id == "way/10"
    assert hits[0].context == "highway=residential"


def test_search_context_missing_classifying_tag(indexed_pbf_path: Path) -> None:
    """Node 4 and way 11 are named but carry no `_CONTEXT_TAGS` key: the node
    falls back to coords-only context, the way (no coords of its own) to
    None."""
    handle = osm_pbf.open_archive(indexed_pbf_path)
    hits = {h.native_id: h for h in osm_pbf.search_entries(handle, "Bare", limit=10)}
    assert set(hits) == {"node/4", "way/11"}
    assert hits["node/4"].context == "@43.700,-79.700"
    assert hits["way/11"].context is None


# --- build_index / index_state ----------------------------------------------


def test_build_index_counts(pbf_path: Path) -> None:
    counts = osm_pbf.build_index(pbf_path)
    assert counts == {"elements": 6, "named": 4}


def test_index_state_transitions(pbf_path: Path) -> None:
    assert osm_pbf.index_state(pbf_path) == "missing"
    osm_pbf.build_index(pbf_path)
    assert osm_pbf.index_state(pbf_path) == "indexed"
    with open(pbf_path, "ab") as f:
        f.write(b"\x00")
    assert osm_pbf.index_state(pbf_path) == "stale"


# --- end-to-end through refdata.resolve()/search() --------------------------


def test_refdata_resolve_end_to_end(indexed_pbf_path: Path) -> None:
    ref = _ref("t", "a" * 64, path=str(indexed_pbf_path))
    entry = refdata.resolve(ref, "way/10")
    assert entry.dataset == "testosm"
    assert entry.tag == "t"
    assert entry.artifact == "a" * 64
    assert entry.native_id == "way/10"
    assert entry.canonical_id == "way/10"
    assert entry.title == "Test Way"
    assert entry.content_type == "text/plain"
    assert entry.text == "way 10\nhighway=residential\nname=Test Way"


def test_refdata_search_end_to_end(indexed_pbf_path: Path) -> None:
    ref = _ref("t", "a" * 64, path=str(indexed_pbf_path))
    hits = refdata.search(ref, "Location")
    assert any(h.native_id == "node/1" and h.title == "Test Location" for h in hits)


def test_refdata_resolve_mirror_unindexed(pbf_path: Path) -> None:
    ref = _ref("t", "a" * 64, path=str(pbf_path))
    with pytest.raises(MirrorUnindexed):
        refdata.resolve(ref, "node/1")
