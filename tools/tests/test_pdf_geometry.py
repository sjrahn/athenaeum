"""Tests for `corpus.pdf_introspect` visual-line geometry (assemble_lines, chrome
detection, body bands, heading candidates) and the resolver's `page=N&geometry` op.

`geometry_pages.pdf` is a hand-built 3-page fixture (see its generator comment in
tests/data/, mirrors born_text.pdf's raw-content-stream style): every page carries a
"RUNNING HEADER" line (repeats on all 3 pages -> chrome), page 1 additionally carries a
larger, numbered "1. Introduction" line (a heading candidate), and each page carries one
body line unique to that page (never repeats -> never chrome).
"""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter
import pypdfium2 as pdfium

from corpus import hashing, paths, pdf_introspect, records, resolver, schemas
from corpus.store import LocalArtifactStore

_FIXTURES = Path(__file__).parent / "data"


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _ingest_fixture(corpus_root: Path, fixture_name: str, *, mime: str, ext: str) -> str:
    src = _FIXTURES / fixture_name
    hashes = hashing.hash_file(src)
    rid = hashes["blake3"]

    store = LocalArtifactStore(corpus_root)
    store.put(rid, ext, src)

    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": rid,
            "description": "",
            "status": "stub",
            "transport": f"sha256:{hashes['sha256']}",
            "touch": "corpus.ingest@0.1.0",
        }
    )
    records.set_artifact_block(post, mime=mime, fields={"title": fixture_name})
    records.append_origin_block(
        post,
        uri=f"file://{src.resolve()}",
        snapshot="2026-05-31T00:00:00Z",
    )
    records.dump(post, paths.record_path(corpus_root, rid))
    return rid


# ---- pdf_introspect unit tests (direct pypdfium2, no corpus scaffolding) ---- #


def test_assemble_lines_bands_by_baseline_in_relative_coords():
    doc = pdfium.PdfDocument(str(_FIXTURES / "geometry_pages.pdf"))
    lines = pdf_introspect.assemble_lines(doc[0])
    assert [line["text"] for line in lines] == [
        "RUNNING HEADER",
        "1. Introduction",
        "Body text on page one only.",
    ]
    for line in lines:
        for key in ("y", "h", "x0", "x1"):
            assert 0.0 <= line[key] <= 1.0
    # The larger-font heading line measures taller than the two 10pt lines.
    heading = lines[1]
    body = lines[2]
    assert heading["h"] > body["h"]


def test_detect_chrome_finds_repeated_line_not_one_offs():
    doc = pdfium.PdfDocument(str(_FIXTURES / "geometry_pages.pdf"))
    chrome = pdf_introspect.detect_chrome(doc)
    assert chrome == {"RUNNING HEADER"}
    assert "Body text on page one only." not in chrome
    assert pdf_introspect.is_chrome("RUNNING HEADER", chrome)
    assert not pdf_introspect.is_chrome("Body text on page one only.", chrome)


def test_body_band_excludes_chrome():
    doc = pdfium.PdfDocument(str(_FIXTURES / "geometry_pages.pdf"))
    chrome = pdf_introspect.detect_chrome(doc)
    lines = pdf_introspect.assemble_lines(doc[0])
    band = pdf_introspect.body_band(lines, chrome)
    assert band is not None
    top, bottom = band
    header_y = lines[0]["y"]
    # The header sits above the band (excluded); the heading line is the band's top.
    assert top > header_y
    assert top == lines[1]["y"]
    assert bottom >= lines[2]["y"] + lines[2]["h"]


def test_body_band_none_when_page_all_chrome():
    assert pdf_introspect.body_band([], set()) is None


def test_classify_headings_flags_larger_numbered_line():
    doc = pdfium.PdfDocument(str(_FIXTURES / "geometry_pages.pdf"))
    chrome = pdf_introspect.detect_chrome(doc)
    lines = pdf_introspect.assemble_lines(doc[0])
    headings, body_h = pdf_introspect.classify_headings(lines, chrome)
    assert body_h > 0
    assert len(headings) == 1
    assert headings[0]["text"] == "1. Introduction"
    by_text = {line["text"]: line for line in lines}
    assert by_text["1. Introduction"]["heading"] is True
    assert by_text["RUNNING HEADER"]["heading"] is False
    assert by_text["RUNNING HEADER"]["chrome"] is True
    assert by_text["Body text on page one only."]["heading"] is False


# ---- resolver end-to-end: page=N&geometry ---- #


def test_pdf_geometry_op_end_to_end(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "geometry_pages.pdf", mime="application/pdf", ext="pdf")

    out = resolver.resolve(f"corpus://{rid}?page=1&geometry", root)
    assert out.suffix == ".json"
    data = json.loads(out.read_text("utf-8"))

    assert data["page"] == 1
    assert data["pages"] == 3
    assert data["width_pt"] == 612.0
    assert data["height_pt"] == 792.0
    assert data["body_glyph_height"] > 0

    assert data["body_band"] is not None
    assert 0.0 <= data["body_band"]["top"] < data["body_band"]["bottom"] <= 1.0

    assert len(data["headings"]) == 1
    assert data["headings"][0]["text"] == "1. Introduction"

    by_text = {line["text"]: line for line in data["lines"]}
    assert by_text["RUNNING HEADER"]["chrome"] is True
    assert by_text["1. Introduction"]["heading"] is True
    assert by_text["Body text on page one only."]["chrome"] is False
    assert by_text["Body text on page one only."]["heading"] is False

    # Page 2 has no heading candidate and a page-specific body line.
    out2 = resolver.resolve(f"corpus://{rid}?page=2&geometry", root)
    data2 = json.loads(out2.read_text("utf-8"))
    assert data2["page"] == 2
    assert data2["headings"] == []
    assert any(
        line["text"] == "Body text on page two only." for line in data2["lines"]
    )
