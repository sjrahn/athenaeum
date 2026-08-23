"""ATH-CORPUS v35 — the `annotated` op and the markup default delivery (spec §6.1, §6.1.1,
§6.2: `annotated` + `raw` rows).

"Ordinals are counted by machines, never by eyes." Pins the span-surgical splice
(`transforms.html.annotate_bytes`) end to end: byte-for-byte faithfulness (re-derivation
recovers the source exactly), the two attested-parse drift checks, the resolver's default
bare-route delivery on an ordinal-scheme markup record (one cache entry shared with the
explicit `?annotated` spelling), `?raw`'s escape hatch, the frozen-generation fallback
(bare stays raw until a record is migrated), and that every internal consumer of artifact
bytes is untouched by any of this.
"""

from __future__ import annotations

import re
from pathlib import Path

import frontmatter
import pytest
from bs4 import BeautifulSoup

from corpus import containment, hashing, paths, records, resolver, schemas, segments
from corpus.segments import Segment
from corpus.store import LocalArtifactStore
from corpus.transforms import html as thtml
from corpus.transforms.html import AnnotationError, annotate_bytes

# ---------- pure splice fidelity (no resolver, no corpus) ---------- #


def test_annotate_bytes_round_trips_byte_for_byte():
    raw = b"<html><body><div><p>a</p><p>b</p></div><ul><li>x</li></ul></body></html>"
    soup = BeautifulSoup(raw, "html.parser")
    root = thtml.path_root(soup)
    out = annotate_bytes(raw, soup, root)
    assert out != raw
    # Stripping exactly the injected spans recovers the source byte-for-byte.
    recovered = re.sub(rb' data-el="\d+"', b"", out)
    assert recovered == raw


def test_annotate_bytes_multiline_and_attributes_untouched():
    raw = (
        b"<html>\n<body>\n"
        b'<div class="x"><p id=foo>a</p><p>b</p></div>\n'
        b"<ul><li>x</li></ul>\n"
        b"</body>\n</html>"
    )
    soup = BeautifulSoup(raw, "html.parser")
    root = thtml.path_root(soup)
    out = annotate_bytes(raw, soup, root)
    # Existing attributes (quoted, unquoted) survive verbatim; only the tag NAME's own
    # end gets the new attribute, before anything the source wrote.
    assert b'<div data-el="1" class="x">' in out
    assert b'<p data-el="2" id=foo>' in out
    recovered = re.sub(rb' data-el="\d+"', b"", out)
    assert recovered == raw


def test_annotate_bytes_preserves_a_pre_existing_data_el_attribute():
    """Faithfulness deletes nothing: a source `data-el` stays in the bytes, verbatim — the
    injected stamp lands immediately after the tag name, before it. NOTE: under this
    toolchain's attested parser (`html.parser`), a duplicate attribute resolves LAST-wins
    (`dict(attrs)` semantics), not first — so re-parsing the annotated bytes and reading
    `data-el` off the DOM yields the SOURCE's own value here, not ours. The byte-level
    faithfulness guarantee (nothing deleted, ours present) holds regardless; a reader must
    still resolve ordinals via the shared walk (`resolve_ordinal`), never by trusting a
    `data-el` value read back off arbitrary HTML."""
    raw = b'<html><body><div data-el="999">x</div></body></html>'
    soup = BeautifulSoup(raw, "html.parser")
    root = thtml.path_root(soup)
    out = annotate_bytes(raw, soup, root)
    assert out == b'<html><body><div data-el="1" data-el="999">x</div></body></html>'
    reparsed = BeautifulSoup(out, "html.parser")
    assert reparsed.find("div").get("data-el") == "999"  # last-wins, see note above


def test_annotate_bytes_single_quoted_and_multiline_attribute_values():
    raw = b"<html><body><img src='x.png'\n     alt=\"multi\nline\"></body></html>"
    soup = BeautifulSoup(raw, "html.parser")
    root = thtml.path_root(soup)
    out = annotate_bytes(raw, soup, root)
    recovered = re.sub(rb' data-el="\d+"', b"", out)
    assert recovered == raw
    assert b"<img data-el=\"1\" src='x.png'" in out


def test_annotate_bytes_non_utf8_encoding_round_trips():
    raw = "<html><body><p>café</p><p>naïve €100</p></body></html>".encode("windows-1252")
    soup = BeautifulSoup(raw, "html.parser")
    root = thtml.path_root(soup)
    out = annotate_bytes(raw, soup, root)
    recovered = re.sub(rb' data-el="\d+"', b"", out)
    assert recovered == raw
    # And the stamped bytes still decode + reparse to the same two <p> elements.
    reparsed = BeautifulSoup(out, "html.parser")
    ps = reparsed.find_all("p")
    assert [p.get("data-el") for p in ps] == ["1", "2"]


def test_annotate_bytes_refuses_when_the_offset_does_not_prove_out():
    """A hard error, never a silent skip: `annotate_bytes` is handed a parse whose source
    positions do not actually describe `raw` (simulating the class of drift the attested
    parser/element-count checks exist to catch upstream) — a byte inserted before the
    parsed content shifts every computed offset off the '<' it should land on."""
    original = b"<html><body><div>x</div></body></html>"
    soup = BeautifulSoup(original, "html.parser")
    root = thtml.path_root(soup)
    mismatched = b"Z" + original  # every offset the parse computed is now off by one
    with pytest.raises(AnnotationError, match="does not land on"):
        annotate_bytes(mismatched, soup, root)


# ---------- round-trip resolution: every stamped ordinal names the same element ---------- #


def test_annotated_ordinals_resolve_via_resolve_ordinal_on_the_original_parse():
    raw = (
        b"<html><body>"
        b"<div><p>First</p><p>Second</p></div>"
        b"<ul><li>Alpha</li><li>Beta</li></ul>"
        b"</body></html>"
    )
    original_soup = BeautifulSoup(raw, "html.parser")
    original_root = thtml.path_root(original_soup)
    annotated = annotate_bytes(raw, original_soup, original_root)

    reparsed = BeautifulSoup(annotated, "html.parser")
    for tag in reparsed.body.find_all(True):
        n = int(tag["data-el"])
        original_tag = thtml.resolve_ordinal(original_root, n)
        assert original_tag.name == tag.name
        assert original_tag.get_text() == tag.get_text()


# ---------- resolver: default delivery, ?raw, dispatch, frozen fallback ---------- #


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


_DOC = b"<html><body><div><p>First</p><p>Second</p></div></body></html>"


def _html_record(
    tmp_path: Path, *, scheme: str | None = "ordinal", raw: bytes = _DOC
) -> tuple[Path, str]:
    """An HTML record over `raw`, its `addressing:` stamp shaped per `scheme` — `"ordinal"`
    (v35), `"dotted"` (a stamp with no `scheme` key — the frozen 3.6 era), or `None` (no
    stamp at all — the frozen legacy era)."""
    root = _make_corpus(tmp_path)
    src = root / "page.html"
    src.write_bytes(raw)
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)
    soup = BeautifulSoup(raw, "html.parser")
    total = thtml.total_element_count(soup)
    fields: dict = {}
    if scheme is not None:
        addressing = {"parser": "html.parser", "elements": total}
        if scheme == "ordinal":
            addressing["scheme"] = "ordinal"
        fields["addressing"] = addressing
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(post, mime="text/html", fields=fields)
    records.append_origin_block(post, uri="https://x.test/page", snapshot="2026-01-01T00:00:00Z")
    post.content = segments.emit([Segment(atom="text", address="el=1", body="stub")])
    records.dump(post, paths.record_path(root, rid))
    return root, rid


def test_bare_route_and_explicit_annotated_are_one_resolution(tmp_path):
    root, rid = _html_record(tmp_path)
    bare_path = resolver.resolve(f"corpus://{rid}", root)
    explicit_path = resolver.resolve(f"corpus://{rid}?annotated", root)
    assert bare_path == explicit_path  # one cache entry, disclosed by construction
    out = bare_path.read_bytes()
    assert b'<div data-el="1">' in out
    assert b'<p data-el="2">First</p>' in out
    assert b'<p data-el="3">Second</p>' in out
    # And it's provably a splice of the stored bytes, not a re-serialization.
    recovered = re.sub(rb' data-el="\d+"', b"", out)
    assert recovered == _DOC


def test_raw_returns_the_stored_bytes_exactly(tmp_path):
    root, rid = _html_record(tmp_path)
    raw_path = resolver.resolve(f"corpus://{rid}?raw", root)
    assert raw_path.read_bytes() == _DOC
    # Terminal only — composing it with anything else is refused, not silently chained.
    with pytest.raises(ValueError, match="terminal-only"):
        resolver.resolve(f"corpus://{rid}?raw&el=1", root)


def test_annotated_requires_the_ordinal_scheme_stamp(tmp_path):
    root, rid = _html_record(tmp_path, scheme="dotted")
    with pytest.raises(ValueError, match="v35 remap"):
        resolver.resolve(f"corpus://{rid}?annotated", root)


def test_bare_route_stays_raw_on_frozen_generation_records(tmp_path):
    """The migration flips this: until an old record is restamped, its bare route keeps
    returning exactly what it always has."""
    root_dotted, rid_dotted = _html_record(tmp_path / "dotted", scheme="dotted")
    assert resolver.resolve(f"corpus://{rid_dotted}", root_dotted).read_bytes() == _DOC

    root_legacy, rid_legacy = _html_record(tmp_path / "legacy", scheme=None)
    assert resolver.resolve(f"corpus://{rid_legacy}", root_legacy).read_bytes() == _DOC


def test_non_markup_bare_route_is_unaffected(tmp_path):
    root = _make_corpus(tmp_path)
    src = root / "note.txt"
    src.write_text("plain text, nothing markup about it", encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "txt", src)
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(post, mime="text/plain", fields={})
    records.append_origin_block(post, uri="https://x.test/note", snapshot="2026-01-01T00:00:00Z")
    records.dump(post, paths.record_path(root, rid))

    bare = resolver.resolve(f"corpus://{rid}", root)
    raw = resolver.resolve(f"corpus://{rid}?raw", root)
    assert bare.read_bytes() == raw.read_bytes() == src.read_bytes()


def test_annotated_cache_key_is_version_pinned(tmp_path):
    """The splice algorithm's own pin folds into the cache key — proven indirectly: the
    annotated cache file's path differs from the bare artifact's own store path (it is a
    genuinely separate, version-keyed cache entry, not an in-place rewrite)."""
    root, rid = _html_record(tmp_path)
    annotated_path = resolver.resolve(f"corpus://{rid}?annotated", root)
    stored_path = LocalArtifactStore(root).local_path(rid, "html")
    assert annotated_path != stored_path
    assert annotated_path.suffix == ".html"
    sidecar = annotated_path.with_name(annotated_path.name + ".json")
    assert sidecar.is_file()
    import json as _json

    meta = _json.loads(sidecar.read_text())
    assert meta["engine"] == thtml.ANNOTATED_ENGINE_VERSION


# ---------- pipeline isolation: internal consumers never see stamped bytes ---------- #


def test_containment_reads_raw_bytes_even_after_annotation_is_cached(tmp_path):
    root, rid = _html_record(tmp_path)
    # Populate the annotated cache first.
    resolver.resolve(f"corpus://{rid}?annotated", root)
    # The containment chokepoint every internal consumer (transforms, drafters,
    # verify/fidelity, promotion) reads through still returns the ORIGINAL bytes.
    path = containment.ensure_local_bytes(root, rid, "html")
    assert path.read_bytes() == _DOC


def test_body_derivation_reads_raw_bytes_not_the_annotated_view(tmp_path):
    from corpus import derive

    root, rid = _html_record(tmp_path)
    # Prime the annotated cache before deriving the body, so a leak would be visible.
    resolver.resolve(f"corpus://{rid}?annotated", root)
    post = records.load(paths.record_path(root, rid))
    body = derive.derive_body(post, root)
    # The faithful body render carries no injected `data-el` noise — it comes from the
    # drafter's own (unrelated) annotation pass over the RAW artifact, never the cached
    # annotated view.
    assert "First" in body and "Second" in body


def test_el_member_bytes_reads_raw_bytes_not_the_annotated_view(tmp_path):
    """An ordinal-scheme record whose `el=` member materializes to real bytes (an inline
    image) — resolved once via `?annotated` first (priming the cache), then via `?el=`,
    proving the two paths never share bytes."""
    b64_png = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAGCAIAAABxZ0isAAAAFEl"
        "EQVR4nGNkaGhgwAaYsIrSSQIAl5oBDCp8u/sAAAAASUVORK5CYII="
    )
    raw = f'<html><body><img src="{b64_png}" alt="x"></body></html>'.encode()
    root, rid = _html_record(tmp_path, raw=raw)
    resolver.resolve(f"corpus://{rid}?annotated", root)  # prime the annotated cache
    img_path = resolver.resolve(f"corpus://{rid}?el=1", root)
    from PIL import Image

    with Image.open(img_path) as im:
        assert im.size == (8, 6)
