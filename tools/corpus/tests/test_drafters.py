"""Drafter registry + per-MIME drafters (PDF, image) tests."""

from __future__ import annotations

import base64
from pathlib import Path

import frontmatter
import pytest
from bs4 import BeautifulSoup
from PIL import Image

from corpus import draft, lint, paths, records, resolver, schemas, segments
from corpus._cli import draft as draft_cli
from corpus.draft import html as draft_html
from corpus.store import LocalArtifactStore
from corpus.transforms import html as transforms_html

_FIXTURES = Path(__file__).parent / "data"


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _ingest(corpus_root: Path, fixture: str, mime: str, ext: str) -> str:
    from corpus import hashing

    src = _FIXTURES / fixture
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(corpus_root).put(rid, ext, src)
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": rid,
            "description": "",
            "status": "stub",
            "transport": f"sha256:{h['sha256']}",
            "touch": "corpus.ingest@0.1.0",
        }
    )
    records.set_artifact_block(post, mime=mime, fields={})
    records.append_origin_block(
        post, uri=f"file://{src.resolve()}", snapshot="2026-05-31T00:00:00Z"
    )
    records.dump(post, paths.record_path(corpus_root, rid))
    return rid


def _ingest_html_str(corpus_root: Path, html: str, *, uri: str, name: str) -> str:
    """Ingest an inline HTML string as a stub under a chosen origin URI."""
    from corpus import hashing

    src = corpus_root / f"{name}.html"
    src.write_text(html, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(corpus_root).put(rid, "html", src)
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": rid,
            "description": "",
            "status": "stub",
            "transport": f"sha256:{h['sha256']}",
            "touch": "corpus.ingest@0.1.0",
        }
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, uri=uri, snapshot="2026-06-02T00:00:00Z")
    records.dump(post, paths.record_path(corpus_root, rid))
    return rid


def test_content_key_distinguishes_by_canonical_and_embeds():
    # No canonical (undrafted stub) → not dedup-able.
    stub = frontmatter.Post("")
    stub.metadata.update({"id": "a" * 64})
    assert records.content_key(stub) is None
    # Same canonical + same embed set → equal keys.
    p1 = frontmatter.Post("")
    p1.metadata.update({"canonical": "blake3:abc", "_embeds": [{"transport": "blake3:img1"}]})
    p2 = frontmatter.Post("")
    p2.metadata.update({"canonical": "blake3:abc", "_embeds": [{"transport": "blake3:img1"}]})
    assert records.content_key(p1) == records.content_key(p2)
    # Same canonical TEXT but a different image → different key (guards false-merge of
    # distinct image pages whose sparse caption text collides).
    p3 = frontmatter.Post("")
    p3.metadata.update({"canonical": "blake3:abc", "_embeds": [{"transport": "blake3:img2"}]})
    assert records.content_key(p1) != records.content_key(p3)


def test_draft_does_not_merge_same_content_canonical_disabled(tmp_path):
    """Cross-URL content dedup is DISABLED: `canonical:` is no longer persisted at draft
    (see `_apply_drafter_result` — the canonical strategy isn't useful yet and its
    `blake3-canonical-pdf` text-hash mis-merged text-empty scans), so `content_key` is None
    and the fold never fires. Two URLs that render the same page now stay TWO records, each
    keeping its own url; byte identity remains the only dedup."""
    root = _make_corpus(tmp_path)
    # Identical visible text; bytes differ only inside <script>, which canonical-html
    # drops — so different record ids but the same canonical content hash.
    base = (
        "<!doctype html><html lang=en><head><title>P Code Charts</title></head>"
        "<body><h1>Code Chart</h1><p>P0300 random cylinder misfire.</p>{script}</body></html>"
    )
    rid_a = _ingest_html_str(
        root, base.format(script="<script>var a=1;</script>"),
        uri="https://x.test/#/p0300", name="a",
    )
    rid_b = _ingest_html_str(
        root, base.format(script="<script>var b=2;</script>"),
        uri="https://x.test/#/p0301", name="b",
    )
    assert rid_a != rid_b  # different bytes → genuinely two stubs

    class ArgsA:
        target = rid_a
        corpus_root = str(root)

    class ArgsB:
        target = rid_b
        corpus_root = str(root)

    assert draft_cli.run(ArgsA()) == 0  # type: ignore[arg-type]
    assert draft_cli.run(ArgsB()) == 0  # type: ignore[arg-type]  no longer merges into A

    # No canonical persisted → no fold: BOTH records survive, each with only its own url.
    a = records.load(paths.record_path(root, rid_a))
    b = records.load(paths.record_path(root, rid_b))
    assert "canonical" not in a.metadata and "canonical" not in b.metadata
    assert paths.record_path(root, rid_b).exists()
    a_uris, b_uris = list(records.iter_origin_uris(a)), list(records.iter_origin_uris(b))
    assert "https://x.test/#/p0300" in a_uris and "https://x.test/#/p0301" not in a_uris
    assert "https://x.test/#/p0301" in b_uris and "https://x.test/#/p0300" not in b_uris


def test_drafter_registry_has_pdf_and_images():
    assert "application/application_pdf" in draft.REGISTRY
    for sid in (
        "image/image_png",
        "image/image_jpeg",
        "image/image_gif",
        "image/image_webp",
        "image/image_avif",
    ):
        assert sid in draft.REGISTRY


def test_pdf_drafter_scanned_emits_page_image_markers(tmp_path, run_drafter):
    root = _make_corpus(tmp_path)
    # onepager.pdf is a PIL-rendered full-page-image PDF (no born-digital text layer) —
    # the structural signature of a scanned image-of-document.
    rid = _ingest(root, "onepager.pdf", "application/pdf", "pdf")
    binary = LocalArtifactStore(root).local_path(rid, "pdf")
    drafter = draft.get_drafter("application/application_pdf")
    assert drafter is not None
    result, blocks = run_drafter(
        drafter, binary, corpus_root=root, record_id=rid, record_metadata={}
    )
    assert result.get("fields", {})["page_count"] == 2
    canonical = result.get("canonical") or ""
    assert canonical.startswith("blake3:")
    assert len(canonical.split(":", 1)[1]) == 64
    assert result.get("embeds") == []
    # Sectionless: one body-empty image-atom positioning marker per page at page=N.
    assert all(isinstance(b, segments.Segment) for b in blocks)
    assert [b.atom for b in blocks] == ["image", "image"]
    assert [b.address for b in blocks] == ["page=1", "page=2"]
    assert all(b.body == "" for b in blocks)


def test_pdf_drafter_born_digital_extracts_text(tmp_path, run_drafter):
    root = _make_corpus(tmp_path)
    # born_text.pdf carries real vector text and no full-page image → born-digital path.
    rid = _ingest(root, "born_text.pdf", "application/pdf", "pdf")
    binary = LocalArtifactStore(root).local_path(rid, "pdf")
    drafter = draft.get_drafter("application/application_pdf")
    result, blocks = run_drafter(
        drafter, binary, corpus_root=root, record_id=rid, record_metadata={}
    )
    assert result.get("fields", {})["page_count"] == 2
    # No outline → flat per-page text segments with extracted bodies.
    assert all(isinstance(b, segments.Segment) for b in blocks)
    assert [b.atom for b in blocks] == ["text", "text"]
    assert [b.address for b in blocks] == ["page=1", "page=2"]
    assert "born-digital" in blocks[0].body
    assert "Second page" in blocks[1].body


def test_pdf_scanned_detection(tmp_path):
    """The structural detector keys on full-page-image coverage, not vendor strings."""
    from pypdf import PdfReader

    from corpus.draft.pdf import _is_scanned_pdf

    assert _is_scanned_pdf(PdfReader(str(_FIXTURES / "onepager.pdf"))) is True
    assert _is_scanned_pdf(PdfReader(str(_FIXTURES / "born_text.pdf"))) is False


def test_image_drafter_emits_metadata_and_positioning_marker(tmp_path, run_drafter):
    root = _make_corpus(tmp_path)
    rid = _ingest(root, "sample.png", "image/png", "png")
    binary = LocalArtifactStore(root).local_path(rid, "png")
    drafter = draft.get_drafter("image/image_png")
    assert drafter is not None
    result, segs = run_drafter(drafter, binary, corpus_root=root, record_id=rid, record_metadata={})
    fields = result.get("fields") or {}
    assert fields["width"] == 200
    assert fields["height"] == 150
    assert fields["format"] == "PNG"
    # Spec §4.3.2.2: image segment is a body-empty positioning marker at bbox=0,0,1,1.
    assert len(segs) == 1
    s = segs[0]
    assert isinstance(s, segments.Segment)
    assert s.atom == "image"
    assert s.address == "bbox=0,0,1,1"
    assert s.body == ""
    # Canonical present.
    assert result.get("canonical", "").startswith("blake3:")


def test_image_drafter_fingerprint_opt_in(tmp_path, run_drafter):
    """The image drafter sets the image-atom segment's `perceptual` only when the
    `fingerprint` knob is on, with the schema-selected algorithm (default phash)."""
    pytest.importorskip("imagehash")
    root = _make_corpus(tmp_path)
    rid = _ingest(root, "sample.png", "image/png", "png")
    binary = LocalArtifactStore(root).local_path(rid, "png")
    drafter = draft.get_drafter("image/image_png")
    kw = {"corpus_root": root, "record_id": rid, "record_metadata": {}}

    _, off = run_drafter(drafter, binary, **kw)
    assert off[0].perceptual is None

    _, on = run_drafter(drafter, binary, fingerprint=True, **kw)
    assert on[0].perceptual.startswith("phash:")  # image atom's default algorithm

    _, dh = run_drafter(drafter, binary, fingerprint="dhash", **kw)
    assert dh[0].perceptual.startswith("dhash:")


def test_draft_cli_pipeline_against_image(tmp_path):
    """End-to-end through `corpus draft` against an ingested PNG."""
    root = _make_corpus(tmp_path)
    rid = _ingest(root, "sample.png", "image/png", "png")

    class Args:
        target = rid
        corpus_root = str(root)

    rc = draft_cli.run(Args())  # type: ignore[arg-type]
    assert rc == 0

    post = records.load(paths.record_path(root, rid))
    assert post.metadata["status"] == "draft"
    assert "canonical" not in post.metadata  # canonical persistence disabled (not useful yet)
    chain = post.metadata.get("touch", [])
    chain_list = chain if isinstance(chain, list) else [chain]
    # Last touch is the draft pass for our mime schema.
    assert any("draft.image/image_png" in t for t in chain_list)
    # Content body has the body-empty image positioning marker.
    blocks = segments.iter_blocks(post.content or "")
    assert len(blocks) == 1
    assert isinstance(blocks[0], segments.Segment)
    assert blocks[0].atom == "image"


def test_draft_cli_refuses_non_stub(tmp_path):
    """Re-running `draft` on an already-drafted record is refused (it would otherwise
    append duplicate embed/issue blocks); the clean re-run path is `re-stub` then `draft`."""
    root = _make_corpus(tmp_path)
    rid = _ingest(root, "sample.png", "image/png", "png")

    class Args:
        target = rid
        corpus_root = str(root)

    assert draft_cli.run(Args()) == 0  # stub → draft
    with pytest.raises(SystemExit):
        draft_cli.run(Args())  # status is now 'draft' → refused


# ---------- HTML drafter ---------- #


def test_html_drafter_registered_and_axis_aligned():
    assert "text/text_html" in draft.REGISTRY
    # The `el=N` index axis MUST match the resolver's addressable-tag set, or
    # `corpus://<hash>?el=N` resolves to the wrong element (or out of range).
    assert draft_html._ADDRESSABLE_TAGS == transforms_html._ADDRESSABLE_TAGS
    # The EPUB drafter/resolver carry a third copy of the same axis (spine=<N>&el=<K>
    # image addresses must be consistent across formats) — keep all three in lockstep.
    from corpus import epub as epub_mod

    assert epub_mod._ADDRESSABLE_TAGS == draft_html._ADDRESSABLE_TAGS


def test_html_drafter_addresses_dl_definition_list(tmp_path, run_drafter):
    """A `<dl>` is a content-bearing block — the peer of `<ul>`/`<ol>` — so it gets its
    own `el=N` address; its `<dt>`/`<dd>` items do not, exactly as `<li>` doesn't.
    Regression: `<dl>` was absent from `_ADDRESSABLE_TAGS`, so the list was unaddressable
    and its text was silently absorbed into a neighbouring segment's range."""
    assert "dl" in draft_html._ADDRESSABLE_TAGS
    assert "dt" not in draft_html._ADDRESSABLE_TAGS
    assert "dd" not in draft_html._ADDRESSABLE_TAGS

    root = _make_corpus(tmp_path)
    html = (
        "<html><head><title>Glossary</title></head><body>"
        '<h1 id="t">Glossary</h1>'
        "<p>Intro.</p>"
        '<dl id="terms"><dt>Corpus</dt><dd>A content-addressed archive.</dd></dl>'
        "<p>Outro.</p>"
        "</body></html>"
    )
    rid = _ingest_html_str(root, html, uri="https://x.test/glossary", name="glossary")
    drafter = draft.get_drafter("text/text_html")
    assert drafter is not None
    binary = LocalArtifactStore(root).local_path(rid, "html")
    _, segs = run_drafter(drafter, binary, corpus_root=root, record_id=rid, record_metadata={})

    # Four addressable elements in document order: h1(1), p(2), dl(3), p(4). The dl
    # consumes an index, so the trailing <p> is el=4 (it would be el=3 without the fix).
    assert len(segs) == 1
    seg = segs[0]
    assert isinstance(seg, segments.Segment)
    assert seg.address == "el=1-4"

    body = BeautifulSoup(seg.body, "html.parser")
    dl = body.find("dl")
    assert dl is not None and dl.get("data-el") == "3"
    # The dl's items carry no address of their own (peers of <li>).
    assert body.find("dt").get("data-el") is None
    assert body.find("dd").get("data-el") is None
    # The trailing <p> was pushed to el=4 by the dl — proves the dl is in the axis.
    assert body.find_all("p")[-1].get("data-el") == "4"
    # Resolver side: the dl is the 3rd addressable element, in lockstep with the drafter.
    assert body.find_all(transforms_html._ADDRESSABLE_TAGS)[2].name == "dl"


def test_html_drafter_emits_segment_embeds_and_canonical(tmp_path, run_drafter):
    root = _make_corpus(tmp_path)
    rid = _ingest(root, "article.html", "text/html", "html")
    binary = LocalArtifactStore(root).local_path(rid, "html")
    drafter = draft.get_drafter("text/text_html")
    assert drafter is not None
    result, segs = run_drafter(drafter, binary, corpus_root=root, record_id=rid, record_metadata={})

    # Artifact fields are document metadata only — the canonical/final URLs and the
    # capture timestamp belong on the ORIGIN block, not here (spec §7.2).
    fields = result.get("fields") or {}
    assert fields["title"] == "Sample Article — Demo Publisher"
    assert fields["lang"] == "en"
    assert fields["og_site_name"] == "Demo Publisher"
    assert "canonical_url" not in fields
    assert "final_url" not in fields
    assert "fetched_at" not in fields
    # Canonical (<link rel=canonical>) + final URL (corpus-capture-url meta) come back as
    # origin aliases for the origin block, not artifact fields.
    aliases = result.get("origin_uri_aliases") or []
    assert "https://example.com/sample-article" in aliases

    # Canonical: blake3-canonical-html → `blake3:<64hex>`.
    canonical = result.get("canonical") or ""
    assert canonical.startswith("blake3:")
    assert len(canonical.split(":", 1)[1]) == 64

    # Exactly one wrapping text segment spanning every addressable element (1..11).
    assert len(segs) == 1
    seg = segs[0]
    assert isinstance(seg, segments.Segment)
    assert seg.atom == "text"
    assert seg.address == "el=1-11"
    assert seg.perceptual is None  # fingerprinting is opt-in — off by default

    # Mechanical drafter output: data-el annotations present; <img src> dropped
    # (addressed by data-el); non-rendered infra (<script>/<style>) stripped.
    body = seg.body
    assert 'data-el="' in body
    assert "src=" not in body  # <img src> dropped; the addressing scheme is data-el
    assert "<script" not in body and "console.log" not in body  # infra stripped
    # The drafter NO LONGER drops chrome — nav/footer/cookie content survives (removing
    # it is the capture layer's per-host job). Nothing content-bearing is silently lost.
    assert "<nav" in body
    assert "<footer" in body
    assert "We use cookies" in body

    # Embeds are plain dicts keyed for `records.append_embed_block`; deduped by transport.
    embeds = result.get("embeds") or []
    by_type = {e["media_type"]: e for e in embeds}
    assert set(by_type) == {"image/png", "image/gif", "image/svg+xml"}
    for e in embeds:
        assert e["transport"].startswith("blake3:")
        assert len(e["transport"].split(":", 1)[1]) == 64
    # The PNG appears twice (el=4 and el=7) → one embed with a list address.
    png = by_type["image/png"]
    assert png["address"] == ["el=4", "el=7"]
    assert png["fields"]["width"] == 8 and png["fields"]["height"] == 6
    assert png["fields"]["alt"] == "Diagram one"
    # GIF appears once → scalar address.
    assert by_type["image/gif"]["address"] == "el=9"
    # SVG: PIL can't open it, so dimensions come from the SVG width=/height= attrs.
    svg = by_type["image/svg+xml"]
    assert svg["address"] == "el=11"
    assert svg["fields"]["width"] == 40 and svg["fields"]["height"] == 30


def test_html_drafter_fingerprint_opt_in(tmp_path, run_drafter):
    """Perceptual fingerprinting is opt-in via the resolved `fingerprint` knob: off →
    no perceptual; True / an algorithm name → a `simhash:` on the text segment; an
    image algorithm requested on a text atom is ignored."""
    p = tmp_path / "f.html"
    p.write_text(
        "<html><body><p>some words here for tokens</p></body></html>", encoding="utf-8"
    )
    drafter = draft.get_drafter("text/text_html")

    _, off = run_drafter(drafter, p, record_id="0" * 64)
    assert off[0].perceptual is None

    _, on = run_drafter(drafter, p, record_id="0" * 64, fingerprint=True)
    assert on[0].perceptual.startswith("simhash:")

    _, named = run_drafter(drafter, p, record_id="0" * 64, fingerprint="simhash")
    assert named[0].perceptual.startswith("simhash:")

    _, wrong = run_drafter(drafter, p, record_id="0" * 64, fingerprint="phash")
    assert wrong[0].perceptual is None  # phash is an image algorithm — ignored on text


def test_svg_dimensions_reads_root_not_inner_elements():
    """SVG sizing reads the ROOT <svg> only — never scrapes an inner element.

    Regression for ALLDATA's interactive-color wiring SVGs: the root declares
    `width="100%" height="100%"` with a real `viewBox`, and a naive whole-doc
    `width=` scan returned a bogus 100x100 from an inner element."""
    d = draft_html._svg_dimensions
    # Percentage root width/height → fall through to the viewBox extent.
    assert d(
        b'<svg xmlns="x" width="100%" height="100%" '
        b'viewBox="-1.2 -1801.2 1452.4 1802.4"><path d="M0 0"/></svg>'
    ) == (1452, 1802)
    # Plain integer root width/height win outright.
    assert d(b'<svg width="40" height="30"><rect width="9" height="9"/></svg>') == (40, 30)
    # No root size + an inner element with width/height must NOT be scraped (the old
    # bug returned 100x100); report an honest unknown instead.
    assert d(b'<svg xmlns="x"><rect width="100" height="100"/></svg>') == (0, 0)


def test_svg_embed_falls_back_to_img_pixel_attrs():
    """When an SVG declares no intrinsic size, the embed falls back to the <img>'s
    own width/height attributes (ALLDATA stamps the display size on the element)."""
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0L1 1"/></svg>'
    uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    img = BeautifulSoup(
        f'<img src="{uri}" width="725" height="900" alt="diagram">', "html.parser"
    ).img
    meta = draft_html._compute_img_embed_metadata(img)
    assert meta is not None
    assert meta["media_type"] == "image/svg+xml"
    assert meta["width"] == 725 and meta["height"] == 900
    # Percentage <img> sizes are not intrinsic pixels — ignored (stays 0).
    img2 = BeautifulSoup(
        f'<img src="{uri}" width="100%" height="100%">', "html.parser"
    ).img
    meta2 = draft_html._compute_img_embed_metadata(img2)
    assert meta2 is not None and meta2["width"] == 0 and meta2["height"] == 0


def test_html_drafter_preserves_form_wrapped_content(tmp_path, run_drafter):
    """Mechanical-drafter regression (realtor.ca / ASP.NET WebForms): the whole page
    is wrapped in one `<form id="form1">`. The drafter must NOT decompose it — the
    form-wrapped content stays addressable and its inline image still embeds."""
    gif = (
        "data:image/gif;base64,R0lGODdhBAAEAIEAAMgyMgAAAAAAAAAAACwAAAAABAAEAAAICQABC"
        "BxIsCCAgAA7"
    )
    html = (
        "<!DOCTYPE html><html lang='en'><head><title>Listing</title></head><body>"
        "<form id='form1'>"
        "<nav><a href='/'>Home</a></nav>"
        "<h1>123 Main St</h1><p>2 beds, 2 baths.</p>"
        f"<figure><img src='{gif}' alt='photo'></figure>"
        "</form></body></html>"
    )
    p = tmp_path / "webforms.html"
    p.write_text(html, encoding="utf-8")
    drafter = draft.get_drafter("text/text_html")
    result, blocks = run_drafter(
        drafter, p, corpus_root=tmp_path, record_id="a" * 64, record_metadata={}
    )

    body = blocks[0].body
    assert "123 Main St" in body and "2 beds, 2 baths." in body  # content survives the form
    # The image inside the page-wrapping form is embedded (was silently dropped before).
    embeds = result.get("embeds") or []
    assert any(e["media_type"] == "image/gif" for e in embeds)


def test_html_title_falls_back_to_title_tag_when_og_title_is_generic():
    """og:title is preferred normally, but a generic social-share CTA (realtor.ca's
    "Check out this listing") loses to the real <title>."""
    cta = (
        "<html><head><title>123 Main St, Calgary - A1 | REALTOR.ca</title>"
        '<meta property="og:title" content="Check out this listing"></head>'
        "<body><p>x</p></body></html>"
    )
    assert (
        draft_html._title(BeautifulSoup(cta, "html.parser"))
        == "123 Main St, Calgary - A1 | REALTOR.ca"
    )
    # An informative og:title is still preferred over <title> (the common case).
    clean = (
        "<html><head><title>Headline | The Daily Site</title>"
        '<meta property="og:title" content="Headline"></head>'
        "<body><p>x</p></body></html>"
    )
    assert draft_html._title(BeautifulSoup(clean, "html.parser")) == "Headline"
    # No og:title → <title>.
    no_og = "<html><head><title>Just The Title</title></head><body><p>x</p></body></html>"
    assert draft_html._title(BeautifulSoup(no_og, "html.parser")) == "Just The Title"


def test_html_drafter_flags_empty_body(tmp_path, run_drafter):
    """Drafter-deterministic issue, emitted in our spec §4.3.3.1 shape."""
    p = tmp_path / "empty.html"
    p.write_text(
        "<!DOCTYPE html><html><head><title>x</title></head>"
        "<body><script>var a=1;</script></body></html>",
        encoding="utf-8",
    )
    drafter = draft.get_drafter("text/text_html")
    result, _ = run_drafter(drafter, p, record_id="0" * 64, canonical_algo="blake3-canonical-html")
    empties = [
        i for i in result.get("issues") or []
        if i["id"] == "partial-content" and i.get("subtype") == "empty-body"
    ]
    assert len(empties) == 1
    issue = empties[0]
    assert issue["severity"] == "blocking"
    assert issue["resolution"] == "open"
    assert issue["detector"].startswith("corpus.draft.text/text_html@")


def test_html_draft_cli_pipeline_and_lint(tmp_path):
    """End-to-end `corpus draft` against an ingested HTML snapshot, then lint."""
    root = _make_corpus(tmp_path)
    rid = _ingest(root, "article.html", "text/html", "html")

    class Args:
        target = rid
        corpus_root = str(root)

    assert draft_cli.run(Args()) == 0  # type: ignore[arg-type]

    post = records.load(paths.record_path(root, rid))
    assert post.metadata["status"] == "draft"
    assert "canonical" not in post.metadata  # canonical persistence disabled (not useful yet)
    chain = post.metadata.get("touch", [])
    chain_list = chain if isinstance(chain, list) else [chain]
    assert any("draft.text/text_html" in t for t in chain_list)

    # Metadata zone carries the three dedup'd embed blocks.
    assert len(list(records.iter_embed_blocks(post))) == 3
    # canonical/final URL re-homed to the origin block's uri list; off the artifact block.
    art_fields = records.artifact_block(post).get("fields") or {}
    assert not ({"canonical_url", "final_url", "fetched_at"} & set(art_fields))
    origin_uris: list[str] = []
    for o in records.iter_origin_blocks(post):
        u = (o.get("fields") or {}).get("uri")
        origin_uris += u if isinstance(u, list) else [u]
    assert "https://example.com/sample-article" in origin_uris
    # Content zone is the single wrapping text segment.
    blocks = segments.iter_blocks(post.content or "")
    assert len(blocks) == 1
    assert isinstance(blocks[0], segments.Segment)
    assert blocks[0].atom == "text"

    # Lint the drafted record: no error-severity findings.
    findings = lint.lint(post, blocks, root)
    errors = [f for f in findings if f.severity == "error"]
    assert not errors, [f"{f.rule_id}: {f.message}" for f in errors]


def test_html_el_addressing_round_trips(tmp_path):
    """The drafter's pre-strip `el=N` indices align with the resolver's raw-artifact
    walk: resolving an embed's `el=N` returns the decoded image at the right size."""
    root = _make_corpus(tmp_path)
    rid = _ingest(root, "article.html", "text/html", "html")

    class Args:
        target = rid
        corpus_root = str(root)

    assert draft_cli.run(Args()) == 0  # type: ignore[arg-type]

    # el=4 is the first PNG occurrence (8x6); el=9 is the GIF (4x4).
    png_path = resolver.resolve(f"corpus://{rid}?el=4", root)
    with Image.open(png_path) as im:
        assert im.size == (8, 6)
    gif_path = resolver.resolve(f"corpus://{rid}?el=9", root)
    with Image.open(gif_path) as im:
        assert im.size == (4, 4)


def test_html_drafter_prefers_largest_srcset(tmp_path, run_drafter):
    """The embed metadata and the `el=` resolver both use the largest inlined `srcset`
    variant, not the displayed thumbnail `src` — so embeds are full-resolution."""
    import base64
    import io

    def datauri(w, h):
        buf = io.BytesIO()
        Image.new("RGB", (w, h), (10, 20, 30)).save(buf, "PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    small, large = datauri(10, 8), datauri(40, 32)
    p = tmp_path / "srcset.html"
    p.write_text(
        "<html><body><p>lede</p>"
        f'<figure><img src="{small}" srcset="{small} 1x, {large} 2x" alt="chart"></figure>'
        "</body></html>",
        encoding="utf-8",
    )
    drafter = draft.get_drafter("text/text_html")
    result, _ = run_drafter(drafter, p, record_id="0" * 64, canonical_algo="blake3-canonical-html")
    embeds = result.get("embeds") or []
    assert len(embeds) == 1
    emb = embeds[0]
    # the 2x variant (40x32), NOT the displayed 10x8 thumbnail
    assert emb["fields"]["width"] == 40 and emb["fields"]["height"] == 32
    # the el= resolver materialises the same largest variant (drafter/resolver agree)
    n = str(emb["address"]).split("=", 1)[1]
    img = transforms_html.extract_el(BeautifulSoup(p.read_bytes(), "html.parser"), n, {})
    assert img.size == (40, 32)


def test_canonical_html_content_selector_scopes_and_falls_back(tmp_path):
    """canonical-html scoped to a content selector ignores per-page framing (title/h1);
    a selector matching nothing falls back to whole-document hashing."""
    from corpus import content_hash

    base = (
        "<html><head><title>{t}</title></head>"
        "<body><h1>{t}</h1><main id=c><p>same body text</p></main></body></html>"
    )
    a = tmp_path / "a.html"
    a.write_text(base.format(t="AAA"), encoding="utf-8")
    b = tmp_path / "b.html"
    b.write_text(base.format(t="BBB"), encoding="utf-8")
    algo = "blake3-canonical-html"
    # whole-document: the title/h1 differ → different hashes
    assert content_hash.compute(algo, a) != content_hash.compute(algo, b)
    # scoped to the shared #c region → identical
    ha = content_hash.compute(algo, a, content_selector="#c")
    hb = content_hash.compute(algo, b, content_selector="#c")
    assert ha == hb
    # list/union selector behaves the same (extra non-matching selector is harmless)
    assert content_hash.compute(algo, a, content_selector=["#c", "#nope"]) == ha
    # selector matching NOTHING → whole-doc fallback (so a and b stay distinct, not empty)
    fa = content_hash.compute(algo, a, content_selector="#missing")
    fb = content_hash.compute(algo, b, content_selector="#missing")
    assert fa != fb
    assert fa == content_hash.compute(algo, a)  # fallback == whole-document


def test_draft_canonical_selector_inert_when_canonical_disabled(tmp_path):
    """Opt-in per-host `canonical.content_selector` is INERT while `canonical:` is not
    persisted: the draft-time recompute is guarded on a present `canonical:`, which no longer
    exists, so two pages sharing an article body but differing in title/heading framing no
    longer collapse — each keeps its own record. (Re-enabling canonical restores this.)"""
    from corpus import schemas

    root = _make_corpus(tmp_path)
    # Per-host overlay scoping canonical to the shared <article> region.
    origin = root / "schema" / "origin"
    origin.mkdir(parents=True, exist_ok=True)
    (origin / "origin.yaml").write_text(
        "description: test\nextended_fields: {}\n", encoding="utf-8"
    )
    (origin / "x.test.yaml").write_text(
        "applies_to:\n  host_pattern: x.test\n  include_subdomains: true\n"
        "canonical:\n  content_selector:\n    - article\n",
        encoding="utf-8",
    )
    schemas._sources.cache_clear()

    body = "<article><h2>Shared diagnostic</h2><p>Perform the check for X or Y.</p></article>"
    page = (
        "<!doctype html><html lang=en><head><title>Code {c}</title></head>"
        "<body><h1>Code {c}</h1>{b}</body></html>"
    )
    rid_a = _ingest_html_str(root, page.format(c="X", b=body), uri="https://x.test/#/x", name="a")
    rid_b = _ingest_html_str(
        root, page.format(c="Y", b=body), uri="https://x.test/#/y", name="b"
    )
    assert rid_a != rid_b

    class ArgsA:
        target = rid_a
        corpus_root = str(root)

    class ArgsB:
        target = rid_b
        corpus_root = str(root)

    assert draft_cli.run(ArgsA()) == 0  # type: ignore[arg-type]
    assert draft_cli.run(ArgsB()) == 0  # type: ignore[arg-type]  no longer merges (canonical off)

    # canonical disabled → scoped recompute never runs → no merge: both records persist.
    assert paths.record_path(root, rid_b).exists()
    a = records.load(paths.record_path(root, rid_a))
    b = records.load(paths.record_path(root, rid_b))
    assert "canonical" not in a.metadata and "canonical" not in b.metadata
