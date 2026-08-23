"""The v35 addressing remap engine (`corpus.remap_el_ordinal`, `corpus remap-el-ordinal`).

Pins the dotted/legacy -> ordinal migration end to end, in the `test_el_path_36.py` mold:
pure mapping proofs, the fleet engine's surfaces (content zone, roster, annotation
context, cross-record origin lineage URIs), held cases, idempotency, and the override
escape hatch. Does not touch `test_el_path_36.py` — the frozen 3.6 engine's own suite —
or the dotted/legacy resolution machinery, which stays untouched by this migration.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest
from bs4 import BeautifulSoup, Tag

from corpus import paths, records, remap_el_ordinal, schemas, segments
from corpus.segments import Segment
from corpus.store import LocalArtifactStore
from corpus.transforms import html as thtml

# ---------- pure mapping proofs ---------- #

_DOC = (
    "<html><head><title>Dotted</title></head><body>"
    "<div><h1>Title</h1><p>One.</p><p>Two.</p><p>Three.</p></div>"
    "<div><p>Coda.</p></div>"
    "</body></html>"
)


def test_map_dotted_value_to_ordinal_point_and_sibling_range():
    soup = BeautifulSoup(_DOC, "html.parser")
    root = thtml.path_root(soup)
    # h1 = el=1.1 (dotted) -> ordinal 2 (div=1, h1=2, ...).
    new, form = remap_el_ordinal.map_dotted_value_to_ordinal("1.1", root)
    assert (new, form) == ("2", "point")
    assert thtml.resolve_ordinal(root, 2).name == "h1"
    # The three <p> siblings under div1 = el=1.[2-4] (dotted) -> ordinals 3,4,5.
    new, form = remap_el_ordinal.map_dotted_value_to_ordinal("1.[2-4]", root)
    assert (new, form) == ("[3-5]", "sibling")


def test_map_dotted_value_rejects_unparseable_or_unresolvable():
    soup = BeautifulSoup(_DOC, "html.parser")
    root = thtml.path_root(soup)
    with pytest.raises(remap_el_ordinal.RemapHold):
        remap_el_ordinal.map_dotted_value_to_ordinal("1.99", root)
    with pytest.raises(remap_el_ordinal.RemapHold):
        remap_el_ordinal.map_dotted_value_to_ordinal("[2-9]", root)  # not a valid dotted form


def test_map_legacy_value_to_ordinal_point_and_flat_range():
    soup = BeautifulSoup(_DOC, "html.parser")
    root = thtml.path_root(soup)
    old_elements = [t for t in soup.find_all(thtml.legacy_is_addressable) if isinstance(t, Tag)]
    # Legacy enumeration: h1(1), p-One(2), p-Two(3), p-Three(4), p-Coda(5).
    new, form = remap_el_ordinal.map_legacy_value_to_ordinal("1", old_elements, root)
    assert (new, form) == ("2", "point")  # h1 -> ordinal 2
    new, form = remap_el_ordinal.map_legacy_value_to_ordinal("2-4", old_elements, root)
    assert (new, form) == ("[3-5]", "sibling")  # One..Three -> ordinals 3-5
    new, form = remap_el_ordinal.map_legacy_value_to_ordinal("5", old_elements, root)
    assert (new, form) == ("7", "point")  # p-Coda -> ordinal 7


# ---------- fleet engine: fixtures ---------- #


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _ingest_dotted_record(tmp_path: Path, name: str = "dotted") -> tuple[Path, Path, str]:
    """A record shaped like the post-3.6, pre-v35 fleet: dotted `el=` addresses (point,
    sibling range, a chained bbox suffix, a placement), stamped `addressing:` with NO
    `scheme` key."""
    from corpus import hashing

    root = _make_corpus(tmp_path)
    src = root / f"{name}.html"
    src.write_text(_DOC, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)
    total = thtml.total_element_count(BeautifulSoup(_DOC, "html.parser"))
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(
        post, mime="text/html", fields={"addressing": {"parser": "html.parser", "elements": total}}
    )
    records.append_origin_block(post, uri="https://x.test/dotted", snapshot="2026-01-01T00:00:00Z")
    post.content = segments.emit([
        Segment(atom="text", address="el=1.1", body="# Title"),
        Segment(atom="text", address="el=1.[2-4]", body="One. Two. Three."),
        Segment(atom="image", address="el=2.1&bbox=0,0,1,1"),
    ])
    records.append_issue_block(
        post, id="partial-content", severity="warning",
        detector="corpus.test@0", address="el=1.2",
    )
    rf = paths.record_path(root, rid)
    records.dump(post, rf)
    return root, rf, rid


def _ingest_legacy_straggler(tmp_path: Path, name: str = "legacy") -> tuple[Path, Path, str]:
    """A pre-3.6 straggler: NO `addressing:` stamp at all, legacy integer/flat-range
    `el=` addresses — the engine must remap it straight to ordinal."""
    from corpus import hashing

    root = _make_corpus(tmp_path)
    src = root / f"{name}.html"
    src.write_text(_DOC, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, uri="https://x.test/legacy", snapshot="2026-01-01T00:00:00Z")
    post.content = segments.emit([
        Segment(atom="text", address="el=1", body="# Title"),
        Segment(atom="text", address="el=2-4", body="One. Two. Three."),
        Segment(atom="text", address="el=5", body="Coda."),
    ])
    rf = paths.record_path(root, rid)
    records.dump(post, rf)
    return root, rf, rid


# ---------- fleet engine: dotted source ---------- #


def test_remap_engine_rewrites_dotted_record_to_ordinal(tmp_path):
    root, rf, _rid = _ingest_dotted_record(tmp_path)
    report = remap_el_ordinal.remap_record(rf, root)
    assert report.hold is None and report.skipped is None and report.changed
    assert report.generation == "dotted"
    rf.write_text(report.new_text, encoding="utf-8")

    post = records.load(rf)
    stamp = records.el_addressing(post)
    assert stamp == {"parser": "html.parser", "elements": 11, "scheme": "ordinal"}
    blocks = segments.iter_blocks(post.content or "")
    addrs = [getattr(b, "address", None) for b in blocks]
    assert addrs[0] == "el=2"          # h1
    assert addrs[1] == "el=[3-5]"      # the three <p> siblings
    assert addrs[2] == "el=7&bbox=0,0,1,1"  # chained suffix preserved verbatim

    # The annotation-zone address migrated too.
    ctx = (post.metadata.get("_contexts") or [])[0]
    assert (ctx.get("fields") or {}).get("address") == "el=3"

    chain = post.metadata.get("touch")
    chain = chain if isinstance(chain, list) else [chain]
    assert any("migrate.el-ordinal-35" in str(t) for t in chain)

    # Every new address resolves, on the raw artifact, to the same elements the dotted
    # addresses named.
    raw_soup = BeautifulSoup(_DOC, "html.parser")
    root_el = thtml.path_root(raw_soup)
    assert thtml.resolve_ordinal(root_el, 2).name == "h1"
    assert thtml.resolve_ordinal(root_el, 7).name == "p"

    # Idempotent: a second pass skips (already ordinal-stamped).
    again = remap_el_ordinal.remap_record(rf, root)
    assert again.skipped is not None and not again.changed


def test_remap_engine_handles_legacy_straggler_directly_to_ordinal(tmp_path):
    root, rf, _rid = _ingest_legacy_straggler(tmp_path)
    report = remap_el_ordinal.remap_record(rf, root)
    assert report.hold is None and report.changed
    assert report.generation == "legacy"
    rf.write_text(report.new_text, encoding="utf-8")

    post = records.load(rf)
    stamp = records.el_addressing(post)
    assert stamp is not None and stamp.get("scheme") == "ordinal"
    blocks = segments.iter_blocks(post.content or "")
    addrs = [b.address for b in blocks]
    assert addrs == ["el=2", "el=[3-5]", "el=7"]


def test_remap_engine_address_list_maps_element_wise(tmp_path):
    from corpus import hashing

    root = _make_corpus(tmp_path)
    src = root / "listy.html"
    src.write_text(_DOC, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)
    total = thtml.total_element_count(BeautifulSoup(_DOC, "html.parser"))
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(
        post, mime="text/html", fields={"addressing": {"parser": "html.parser", "elements": total}}
    )
    records.append_origin_block(post, uri="https://x.test/listy", snapshot="2026-01-01T00:00:00Z")
    # A disjoint-landmarks list: h1 and the Coda paragraph.
    post.content = segments.emit([
        Segment(atom="text", address=["el=1.1", "el=2.1"], body="Title Coda."),
    ])
    rf = paths.record_path(root, rid)
    records.dump(post, rf)

    report = remap_el_ordinal.remap_record(rf, root)
    assert report.hold is None and report.changed
    rf.write_text(report.new_text, encoding="utf-8")
    post = records.load(rf)
    blocks = segments.iter_blocks(post.content or "")
    assert blocks[0].address == ["el=2", "el=7"]


# ---------- held cases ---------- #


def test_remap_holds_on_unreachable_artifact(tmp_path):
    root, rf, rid = _ingest_dotted_record(tmp_path)
    # Remove the stored artifact bytes.
    LocalArtifactStore(root).local_path(rid, "html").unlink()
    report = remap_el_ordinal.remap_record(rf, root)
    assert report.hold is not None and "not resident" in report.hold


def test_remap_holds_on_element_count_drift(tmp_path):
    root, rf, _rid = _ingest_dotted_record(tmp_path)
    post = records.load(rf)
    artifact = records.artifact_block(post) or {}
    fields = dict(artifact.get("fields") or {})
    fields["addressing"] = {"parser": "html.parser", "elements": 999}  # fabricate drift
    records.set_artifact_block(post, mime="text/html", fields=fields)
    records.dump(post, rf)
    report = remap_el_ordinal.remap_record(rf, root)
    assert report.hold is not None and "element-count mismatch" in report.hold


def test_remap_holds_on_out_of_range_dotted_address(tmp_path):
    root, rf, _rid = _ingest_dotted_record(tmp_path)
    post = records.load(rf)
    blocks = segments.iter_blocks(post.content or "")
    blocks[0].address = "el=9.9.9"  # fabricate a drifted address
    post.content = segments.emit(blocks)
    records.dump(post, rf)
    report = remap_el_ordinal.remap_record(rf, root)
    assert report.hold is not None


# ---------- the override escape hatch ---------- #


def test_override_resolves_a_held_ordinal_and_the_rest_still_maps(tmp_path):
    root, rf, _rid = _ingest_dotted_record(tmp_path)
    post = records.load(rf)
    blocks = segments.iter_blocks(post.content or "")
    blocks[0].address = "el=9.9.9"
    post.content = segments.emit(blocks)
    records.dump(post, rf)

    report = remap_el_ordinal.remap_record(rf, root, {"el=9.9.9": "el=2"})
    assert report.hold is None and report.changed
    forms = report.forms
    assert forms.get("override") == 1
    assert sum(v for k, v in forms.items() if k != "override") >= 1


def test_override_that_is_not_an_ordinal_address_is_refused(tmp_path):
    root, rf, _rid = _ingest_dotted_record(tmp_path)
    post = records.load(rf)
    blocks = segments.iter_blocks(post.content or "")
    blocks[0].address = "el=9.9.9"
    post.content = segments.emit(blocks)
    records.dump(post, rf)
    # "el=1.2.3" is dotted, not a valid ordinal override.
    report = remap_el_ordinal.remap_record(rf, root, {"el=9.9.9": "el=1.2.3"})
    assert report.hold is not None and "not a §6.1.1 ordinal address" in report.hold


# ---------- cross-record: origin lineage URIs ---------- #


def _promoted_leaf_record(
    root: Path, container_id: str, member_el_value: str, name: str
) -> tuple[Path, str]:
    """A standalone (non-HTML) member-leaf record whose origin cites the container by a
    dotted `el=` lineage URI — the shape a promoted embed's own record carries (§8.1).
    `root` is the SAME corpus root the container record lives in."""
    from corpus import hashing

    payload = root / f"{name}.bin"
    payload.write_bytes(b"leaf bytes")
    h = hashing.hash_file(payload)
    lid = h["blake3"]
    LocalArtifactStore(root).put(lid, "bin", payload)
    post = frontmatter.Post("")
    post.metadata.update({"id": lid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(post, mime="application/octet-stream", fields={})
    records.append_origin_block(
        post, uri=f"corpus://{container_id}?{member_el_value}",
        snapshot="2026-01-01T00:00:00Z",
    )
    records.dump(post, paths.record_path(root, lid))
    return paths.record_path(root, lid), lid


def test_origin_uri_on_a_second_record_maps_against_the_container(tmp_path):
    root, container_rf, container_id = _ingest_dotted_record(tmp_path, name="container")
    leaf_rf, _lid = _promoted_leaf_record(root, container_id, "el=1.1", name="leaf")

    cache: dict = {}
    leaf_report = remap_el_ordinal.remap_record(leaf_rf, root, container_pairings=cache)
    assert leaf_report.hold is None and leaf_report.changed
    leaf_rf.write_text(leaf_report.new_text, encoding="utf-8")

    leaf_post = records.load(leaf_rf)
    uri = next(records.iter_origin_uris(leaf_post))
    assert uri == f"corpus://{container_id}?el=2"  # h1 -> ordinal 2, proven above

    # The container itself is UNTOUCHED by mapping the leaf's citation of it — the leaf's
    # own report is a pure read against the container's pre-migration on-disk state.
    assert records.el_addressing(records.load(container_rf)) == {
        "parser": "html.parser", "elements": 11,
    }


def test_origin_uri_pass_is_order_independent_via_the_shared_cache(tmp_path):
    """The two-pass discipline the module docstring promises: whichever order the sweep
    visits records in, the cache is built from PRE-migration disk state (pass 1 never
    writes), so the container's OWN remap happening first would not corrupt the leaf's
    mapping — proven here by remapping the CONTAINER first and writing it, then showing
    a FRESH cache (simulating a second independent run) correctly reports the container
    as already-ordinal and leaves the leaf's citation of it alone rather than
    mis-mapping a value that is no longer dotted."""
    root, container_rf, container_id = _ingest_dotted_record(tmp_path, name="container2")
    leaf_rf, _lid = _promoted_leaf_record(root, container_id, "el=1.1", name="leaf2")

    container_report = remap_el_ordinal.remap_record(container_rf, root)
    assert container_report.changed
    container_rf.write_text(container_report.new_text, encoding="utf-8")

    # A fresh cache now sees the container as ALREADY ordinal-stamped.
    fresh_cache: dict = {}
    leaf_report = remap_el_ordinal.remap_record(leaf_rf, root, container_pairings=fresh_cache)
    # The leaf's own citation is still dotted (`el=1.1`) but the container it names no
    # longer speaks that grammar — the engine must not guess: it reports nothing to do
    # rather than silently mis-mapping.
    assert leaf_report.skipped is not None
    leaf_post = records.load(leaf_rf)
    assert next(records.iter_origin_uris(leaf_post)) == f"corpus://{container_id}?el=1.1"


# ---------- stamp-only remap: a markup record with zero el= addresses ---------- #


def _ingest_zero_address_record(
    tmp_path: Path, *, stamped: bool, name: str = "empty"
) -> tuple[Path, Path, str]:
    """An HTML record with NO el= address anywhere — content zone, roster, annotation
    zone, or origin — either dotted-stamped (`stamped=True`) or a genuine pre-3.6
    straggler with no `addressing:` block at all (`stamped=False`)."""
    from corpus import hashing

    root = _make_corpus(tmp_path)
    src = root / f"{name}.html"
    src.write_text(_DOC, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)
    total = thtml.total_element_count(BeautifulSoup(_DOC, "html.parser"))
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    fields = {"addressing": {"parser": "html.parser", "elements": total}} if stamped else {}
    records.set_artifact_block(post, mime="text/html", fields=fields)
    records.append_origin_block(post, uri=f"https://x.test/{name}", snapshot="2026-01-01T00:00:00Z")
    post.content = ""  # no drafted segments at all — nothing to address
    rf = paths.record_path(root, rid)
    records.dump(post, rf)
    return root, rf, rid


def test_stamp_only_remap_restamps_a_dotted_zero_address_record(tmp_path):
    root, rf, rid = _ingest_zero_address_record(tmp_path, stamped=True)
    report = remap_el_ordinal.remap_record(rf, root)
    assert report.hold is None and report.skipped is None
    assert report.changed and report.stamp_only
    assert report.mappings == []
    assert report.generation == "dotted"
    rf.write_text(report.new_text, encoding="utf-8")

    post = records.load(rf)
    stamp = records.el_addressing(post)
    assert stamp == {"parser": "html.parser", "elements": 11, "scheme": "ordinal"}

    # And the bare route now delivers the ANNOTATED view — the whole point.
    from corpus import resolver

    out_path = resolver.resolve(f"corpus://{rid}", root)
    assert b'data-el="' in out_path.read_bytes()


def test_stamp_only_remap_stamps_a_legacy_unstamped_zero_address_record(tmp_path):
    root, rf, _rid = _ingest_zero_address_record(tmp_path, stamped=False, name="straggler")
    report = remap_el_ordinal.remap_record(rf, root)
    assert report.hold is None and report.skipped is None
    assert report.changed and report.stamp_only
    assert report.generation == "legacy"
    rf.write_text(report.new_text, encoding="utf-8")

    post = records.load(rf)
    stamp = records.el_addressing(post)
    assert stamp == {"parser": "html.parser", "elements": 11, "scheme": "ordinal"}


def test_stamp_only_remap_holds_on_element_count_drift(tmp_path):
    root, rf, _rid = _ingest_zero_address_record(tmp_path, stamped=True, name="drifted")
    post = records.load(rf)
    artifact = records.artifact_block(post) or {}
    fields = dict(artifact.get("fields") or {})
    fields["addressing"] = {"parser": "html.parser", "elements": 999}  # fabricate drift
    records.set_artifact_block(post, mime="text/html", fields=fields)
    records.dump(post, rf)
    report = remap_el_ordinal.remap_record(rf, root)
    assert report.hold is not None and "element-count mismatch" in report.hold
    assert not report.changed


def test_stamp_only_remap_is_idempotent(tmp_path):
    root, rf, _rid = _ingest_zero_address_record(tmp_path, stamped=True, name="idem")
    first = remap_el_ordinal.remap_record(rf, root)
    rf.write_text(first.new_text, encoding="utf-8")
    second = remap_el_ordinal.remap_record(rf, root)
    assert second.skipped is not None and not second.changed


def test_stamp_only_manifest_row_shape_and_ledger_tolerance(tmp_path):
    """The manifest row for a stamp-only record carries `stamp_only: true` and an empty
    `mappings` list; the ledger engine's generation loader must not choke on it."""
    import json

    root, rf, rid = _ingest_zero_address_record(tmp_path, stamped=True, name="manifest")
    report = remap_el_ordinal.remap_record(rf, root)
    assert report.changed and report.stamp_only

    row = {
        "record": report.record_id, "relpath": report.relpath, "changed": report.changed,
        "skipped": report.skipped, "hold": report.hold, "generation": report.generation,
        "elements": report.elements, "emit_normalized": report.emit_normalized,
        "stamp_only": report.stamp_only, "forms": report.forms, "mappings": report.mappings,
        "overrides": None,
    }
    assert row["stamp_only"] is True
    assert row["mappings"] == []
    assert row["generation"] == "dotted"

    manifest_path = tmp_path / "manifest.jsonl"
    manifest_path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    from ledger.remap_el_ordinal import load_migration_generations

    generations = load_migration_generations([manifest_path])
    assert generations == {rid: "dotted"}
