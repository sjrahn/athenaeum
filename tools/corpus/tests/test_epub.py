"""EPUB reader + drafter tests (synthetic in-memory EPUB, no real book needed)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import blake3
from PIL import Image

from corpus import content_hash, epub
from corpus.draft import get_drafter
from corpus.draft.epub import draft as epub_draft
from corpus.segments import Section, Segment


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


_COVER_PNG = _png(2, 3)

_CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

# Spine reading order: cover, ch1, ch2. The cover is intentionally NOT in the nav/NCX TOC
# so it exercises the synthetic "Front matter" section.
_COVER = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Cover</title></head>
<body><p>cover</p></body></html>"""

_CH1 = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Chapter One</title></head>
<body>
  <div class="chapter">
    <h1>Chapter One</h1>
    <p>The <em>first</em> chapter has prose.</p>
    <img src="cover.png" alt="cover"/>
    <script>tracking();</script>
  </div>
</body></html>"""

_CH2 = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head></head>
<body><h2>Second Part</h2><p>More words in the second document.</p></body></html>"""

_NAV = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>Contents</title></head>
<body><nav epub:type="toc"><ol>
  <li><a href="ch1.xhtml">Chapter One</a></li>
  <li><a href="ch2.xhtml#mid">Second Part</a></li>
</ol></nav></body></html>"""

_NCX = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<navMap>
  <navPoint id="n1" playOrder="1">
    <navLabel><text>Chapter One</text></navLabel><content src="ch1.xhtml"/>
  </navPoint>
  <navPoint id="n2" playOrder="2">
    <navLabel><text>Second Part</text></navLabel><content src="ch2.xhtml"/>
  </navPoint>
</navMap></ncx>"""


def _opf(*, nav: bool, ncx: bool) -> str:
    items = [
        '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>',
        '<item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>',
        '<item id="ch2" href="ch2.xhtml" media-type="application/xhtml+xml"/>',
        '<item id="coverimg" href="cover.png" media-type="image/png"/>',
        '<item id="css" href="style.css" media-type="text/css"/>',
    ]
    xhtml = "application/xhtml+xml"
    if nav:
        items.append(f'<item id="nav" href="nav.xhtml" properties="nav" media-type="{xhtml}"/>')
    if ncx:
        items.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
    spine_attr = ' toc="ncx"' if ncx else ""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Synthetic Test Book</dc:title>
    <dc:creator>A. Tester</dc:creator>
    <dc:language>en</dc:language>
    <dc:publisher>Test Press</dc:publisher>
    <dc:date>2026-01-01</dc:date>
    <dc:identifier id="bookid">urn:isbn:9990001112223</dc:identifier>
  </metadata>
  <manifest>
    {chr(10).join("    " + i for i in items).strip()}
  </manifest>
  <spine{spine_attr}>
    <itemref idref="cover"/>
    <itemref idref="ch1"/>
    <itemref idref="ch2"/>
  </spine>
</package>"""


def _write_epub(
    path: Path, *, nav: bool = True, ncx: bool = False, opf: str | None = None,
    extra: dict[str, str] | None = None,
) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        # `mimetype` must be the first entry, stored (uncompressed) per the EPUB OCF spec.
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", _CONTAINER)
        zf.writestr("OEBPS/content.opf", opf if opf is not None else _opf(nav=nav, ncx=ncx))
        zf.writestr("OEBPS/cover.xhtml", _COVER)
        zf.writestr("OEBPS/ch1.xhtml", _CH1)
        zf.writestr("OEBPS/ch2.xhtml", _CH2)
        zf.writestr("OEBPS/style.css", "body { color: black; }")
        zf.writestr("OEBPS/cover.png", _COVER_PNG)
        if nav:
            zf.writestr("OEBPS/nav.xhtml", _NAV)
        if ncx:
            zf.writestr("OEBPS/toc.ncx", _NCX)
        for name, content in (extra or {}).items():
            zf.writestr(name, content)
    return path


def test_read_package_metadata_and_spine(tmp_path):
    pkg = epub.read_package(_write_epub(tmp_path / "b.epub"))
    assert pkg.metadata["title"] == "Synthetic Test Book"
    assert pkg.metadata["creator"] == "A. Tester"
    assert pkg.metadata["language"] == "en"
    assert pkg.metadata["publisher"] == "Test Press"
    assert pkg.metadata["identifier"] == "urn:isbn:9990001112223"
    # Spine is reading order, resolved against the OPF directory; the non-spine
    # cover-image/css/nav manifest items are NOT in it.
    assert [d.href for d in pkg.spine] == [
        "OEBPS/cover.xhtml", "OEBPS/ch1.xhtml", "OEBPS/ch2.xhtml"
    ]


def test_clean_xhtml_keeps_structure_strips_scripts(tmp_path):
    pkg = epub.read_package(_write_epub(tmp_path / "b.epub"))
    body, embeds = epub.clean_xhtml_body(pkg.spine[1].data)  # ch1, no resolver
    assert "<h1>" in body and "first" in body
    assert "tracking()" not in body and "<script" not in body  # non-rendered stripped
    assert 'class="chapter"' not in body  # presentational attrs stripped
    # No resolver → images are dropped and no embeds produced (the text-only path).
    assert "<img" not in body and embeds == []


def test_clean_xhtml_extracts_image_embeds_with_resolver(tmp_path):
    pkg = epub.read_package(_write_epub(tmp_path / "b.epub"))
    ch1 = pkg.spine[1]
    resolver = epub.make_image_resolver(epub.read_resources(tmp_path / "b.epub"), ch1.href)
    body, embeds = epub.clean_xhtml_body(ch1.data, image_resolver=resolver)
    # The img is kept as an addressable, src-stripped placeholder.
    assert '<img alt="cover" data-el="3"/>' in body
    assert len(embeds) == 1
    em = embeds[0]
    assert em["media_type"] == "image/png"
    assert em["byte_hash"] == blake3.blake3(_COVER_PNG).hexdigest()
    assert (em["width"], em["height"]) == (2, 3)  # real PIL dimensions
    assert em["alt"] == "cover"
    assert em["els"] == [3]  # h1=1, p=2, img=3


def test_document_title_prefers_title_then_heading(tmp_path):
    pkg = epub.read_package(_write_epub(tmp_path / "b.epub"))
    assert epub.document_title(pkg.spine[1].data) == "Chapter One"  # <title>
    assert epub.document_title(pkg.spine[2].data) == "Second Part"  # first heading


def test_read_toc_nav_maps_to_spine_indices(tmp_path):
    pkg = epub.read_package(_write_epub(tmp_path / "b.epub"))  # nav
    assert [(e.title, e.spine_index) for e in pkg.toc] == [
        ("Chapter One", 2), ("Second Part", 3)
    ]


def test_read_toc_ncx_fallback(tmp_path):
    pkg = epub.read_package(_write_epub(tmp_path / "b.epub", nav=False, ncx=True))
    assert [(e.title, e.spine_index) for e in pkg.toc] == [
        ("Chapter One", 2), ("Second Part", 3)
    ]


def test_no_toc_is_sectionless(tmp_path):
    pkg = epub.read_package(_write_epub(tmp_path / "b.epub", nav=False))
    assert pkg.toc == []


def test_malformed_epub_is_tolerant(tmp_path):
    bad = tmp_path / "bad.epub"
    bad.write_bytes(b"not a zip at all")
    pkg = epub.read_package(bad)
    assert pkg.metadata == {} and pkg.spine == [] and pkg.toc == []


def test_canonical_epub_is_packaging_invariant(tmp_path):
    # Two EPUBs with identical spine prose but a different non-spine asset hash to the same
    # canonical — content identity drops packaging.
    a = _write_epub(tmp_path / "a.epub")
    b = _write_epub(tmp_path / "b.epub", extra={"OEBPS/extra.txt": "ignored junk"})
    ca = content_hash.compute("blake3-canonical-epub", a)
    cb = content_hash.compute("blake3-canonical-epub", b)
    assert ca == cb
    assert len(ca) == 64  # blake3 hexdigest


def test_drafter_sections_by_toc(tmp_path, run_drafter):
    path = _write_epub(tmp_path / "b.epub")  # nav TOC: ch1, ch2 (cover omitted)
    result, blocks = run_drafter(epub_draft, path, corpus_root=tmp_path, record_id="x")
    # Spine docs before the first TOC target (the cover) → a synthetic Front matter section;
    # then one section per top-level TOC entry, addressed by spine-range with the TOC label.
    assert all(isinstance(b, Section) for b in blocks)
    assert [b.entry for b in blocks] == ["Front matter", "Chapter One", "Second Part"]
    assert [b.address for b in blocks] == ["spines=1", "spines=2", "spines=3"]
    # Child segments are spine=<N> points carrying NO entry (the section owns the label).
    assert [s.address for s in blocks[0].segments] == ["spine=1"]
    assert blocks[1].segments[0].address == "spine=2"
    assert all(s.entry is None for b in blocks for s in b.segments)
    assert result["fields"]["title"] == "Synthetic Test Book"
    assert result["fields"]["spine_item_count"] == 3
    assert result["fields"]["toc_entry_count"] == 2
    assert result["canonical"].startswith("blake3:")
    assert not result["issues"]


def test_drafter_flat_fallback_when_no_toc(tmp_path, run_drafter):
    path = _write_epub(tmp_path / "b.epub", nav=False)  # no nav, no NCX
    result, blocks = run_drafter(epub_draft, path, corpus_root=tmp_path, record_id="x")
    # Sectionless: a flat top-level segment per spine doc, each carrying its doc title.
    assert all(isinstance(b, Segment) for b in blocks)
    assert [b.address for b in blocks] == ["spine=1", "spine=2", "spine=3"]
    assert [b.entry for b in blocks] == ["Cover", "Chapter One", "Second Part"]
    assert result["fields"]["toc_entry_count"] == 0


def test_drafter_empty_spine_emits_partial_content_issue(tmp_path, run_drafter):
    # An OPF with an empty spine → no segments + a partial-content issue.
    empty_opf = _opf(nav=False, ncx=False).split("<spine")[0] + "<spine></spine>\n</package>"
    path = _write_epub(tmp_path / "empty.epub", nav=False, opf=empty_opf)
    result, blocks = run_drafter(epub_draft, path, corpus_root=tmp_path, record_id="x")
    assert blocks == []
    assert result["issues"]
    assert result["issues"][0]["id"] == "partial-content"
    assert result["issues"][0]["severity"] == "blocking"


def test_drafter_emits_image_embeds(tmp_path, run_drafter):
    # ch1 (spine 2) references cover.png → one image embed addressed spine=2&el=K, with the
    # blake3 of the member bytes as transport and PIL dimensions in fields.
    path = _write_epub(tmp_path / "b.epub")
    result, _blocks = run_drafter(epub_draft, path, corpus_root=tmp_path, record_id="x")
    embeds = result["embeds"]
    assert len(embeds) == 1
    em = embeds[0]
    assert em["media_type"] == "image/png"
    assert em["address"] == "spine=2&el=3"
    assert em["transport"] == f"blake3:{blake3.blake3(_COVER_PNG).hexdigest()}"
    assert em["fields"] == {"width": 2, "height": 3, "alt": "cover"}


def test_audio_mp4_drafter_registered():
    # The M4B routing wires audio/mp4 to the existing audio drafter.
    assert get_drafter("audio/audio_mp4") is not None


# ---------- resolver: spine=N&el=K → image bytes ---------- #


def _stage_epub_record(corpus_root: Path, epub_path: Path) -> str:
    """Stage an EPUB as a corpus record + artifact for resolver tests. Returns the id."""
    import frontmatter

    from corpus import hashing, paths, records
    from corpus.store import LocalArtifactStore

    hashes = hashing.hash_file(epub_path)
    rid = hashes["blake3"]
    LocalArtifactStore(corpus_root).put(rid, "epub", epub_path)
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": rid, "description": "", "status": "stub", "touch": "corpus.ingest@0.1.0"}
    )
    records.set_artifact_block(post, mime="application/epub+zip", fields={})
    records.append_origin_block(
        post, uri=f"file://{epub_path.resolve()}", snapshot="2026-06-04T00:00:00Z"
    )
    records.dump(post, paths.record_path(corpus_root, rid))
    return rid


def test_resolver_spine_el_materializes_image_member(tmp_path):
    # ch1 (spine 2) holds the <img> at addressable el=3 → the round-trip of the embed the
    # drafter recorded (spine=2&el=3 / transport blake3(cover.png)) back to its bytes.
    from corpus import resolver, schemas

    schemas._sources.cache_clear()
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    rid = _stage_epub_record(root, _write_epub(tmp_path / "b.epub"))
    out = resolver.resolve(f"corpus://{rid}?spine=2&el=3", root)
    assert out.is_file()
    assert out.suffix == ".png"
    with Image.open(out) as im:
        assert im.size == (2, 3)  # the real cover.png dimensions
    # Cache hit on a second call.
    assert resolver.resolve(f"corpus://{rid}?spine=2&el=3", root) == out


def test_resolver_spine_el_errors(tmp_path):
    import pytest

    from corpus import resolver, schemas

    schemas._sources.cache_clear()
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    rid = _stage_epub_record(root, _write_epub(tmp_path / "b.epub"))
    # spine out of range (only 3 spine docs).
    with pytest.raises(ValueError, match="spine=9 out of range"):
        resolver.resolve(f"corpus://{rid}?spine=9&el=1", root)
    # el points at a non-img element (spine 2 el=1 is the <h1>).
    with pytest.raises(ValueError, match="expected <img>"):
        resolver.resolve(f"corpus://{rid}?spine=2&el=1", root)
