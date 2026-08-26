"""Drafter registry + per-MIME drafters (PDF, image) tests."""

from __future__ import annotations

import base64
from pathlib import Path

import frontmatter
import pytest
from bs4 import BeautifulSoup
from PIL import Image

from corpus import draft, lint, paths, records, resolver, schemas, segments
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

    from tests._draftlib import draft_for_test

    assert draft_for_test(root, rid_a) == 0
    assert draft_for_test(root, rid_b) == 0  # no longer merges into A

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
    # onepager.pdf is a PIL-rendered full-page-image PDF (no born-digital text layer).
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


def test_pdf_drafter_born_digital_emits_text_segments(tmp_path, run_drafter):
    """A born-digital PDF (real vector text, no full-page image) drafts to `atom: text`
    segments carrying the extracted body — no sections. born_text.pdf's own glyph
    geometry fragments (a base-14 Helvetica hyphen trips `assemble_lines`' baseline
    tolerance — the known failure mode its docstring describes), so both pages fall back
    to the bare `page=N` address rather than a content band;
    `test_pdf_drafter_outline_marks_precede_content_and_dedupe_same_page` below exercises
    a fixture whose geometry DOES support the band form."""
    root = _make_corpus(tmp_path)
    rid = _ingest(root, "born_text.pdf", "application/pdf", "pdf")
    binary = LocalArtifactStore(root).local_path(rid, "pdf")
    drafter = draft.get_drafter("application/application_pdf")
    result, blocks = run_drafter(
        drafter, binary, corpus_root=root, record_id=rid, record_metadata={}
    )
    assert result.get("fields", {})["page_count"] == 2
    assert all(isinstance(b, segments.Segment) for b in blocks)
    assert [b.atom for b in blocks] == ["text", "text"]
    assert [b.address for b in blocks] == ["page=1", "page=2"]
    assert blocks[0].body.strip() == "Hello born-digital vector text"
    assert blocks[1].body.strip() == "Second page vector text only"
    assert blocks[0].perceptual is None  # fingerprinting is opt-in — off by default


def _minimal_text_pdf(text: str) -> bytes:
    """A hand-built single-page PDF (mirrors `born_text.pdf`'s raw-content-stream style)
    whose page draws exactly `text` in one `Tj` — for a page short enough to trip the
    drafter's blank-page threshold while still carrying a real, non-empty text layer."""
    escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    content = f"BT /F1 24 Tf 72 700 Td ({escaped}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_offset = len(out)
    n = len(objects) + 1
    out += f"xref\n0 {n}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode()
    return bytes(out)


def test_pdf_drafter_blank_born_digital_page_emits_image_marker(tmp_path, run_drafter):
    """A born-digital page (real vector text, so `probe_page` reports shape_hint
    'born-digital') whose extracted text is below the blank threshold gets the same
    image marker a scanned page gets — never an empty text segment."""
    blankish = tmp_path / "blankish.pdf"
    blankish.write_bytes(_minimal_text_pdf("."))

    drafter = draft.get_drafter("application/application_pdf")
    result, blocks = run_drafter(
        drafter, blankish, corpus_root=None, record_id="c" * 64, record_metadata={}
    )
    assert result.get("fields", {})["page_count"] == 1
    assert len(blocks) == 1
    assert blocks[0].atom == "image"
    assert blocks[0].address == "page=1"
    assert blocks[0].body == ""


def test_pdf_drafter_mixed_document_text_then_image(tmp_path, run_drafter):
    """A document mixing a born-digital page with a scanned (full-page-image) page drafts
    each page independently by its own shape: text where the geometry says born-digital,
    an image marker where it doesn't."""
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    writer.add_page(PdfReader(str(_FIXTURES / "born_text.pdf")).pages[0])
    writer.add_page(PdfReader(str(_FIXTURES / "onepager.pdf")).pages[0])
    mixed = tmp_path / "mixed.pdf"
    with open(mixed, "wb") as f:
        writer.write(f)

    drafter = draft.get_drafter("application/application_pdf")
    result, blocks = run_drafter(
        drafter, mixed, corpus_root=None, record_id="a" * 64, record_metadata={}
    )
    assert result.get("fields", {})["page_count"] == 2
    assert [b.atom for b in blocks] == ["text", "image"]
    assert blocks[0].address == "page=1"
    assert blocks[0].body.strip() == "Hello born-digital vector text"
    assert blocks[1].address == "page=2"
    assert blocks[1].body == ""


def test_pdf_drafter_outline_marks_precede_content_and_dedupe_same_page(tmp_path, run_drafter):
    """Top-level outline entries become `atom: structural` marks inserted immediately
    before their page's own content segment, in document order; two entries resolving to
    the same page keep only the first. `geometry_pages.pdf`'s per-page glyph geometry
    (unlike `born_text.pdf`'s) supports real content-band addressing, so this also
    exercises the `page=N&bbox=...` form on a mid-document page with no outline entry of
    its own."""
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for page in PdfReader(str(_FIXTURES / "geometry_pages.pdf")).pages:
        writer.add_page(page)
    writer.add_outline_item("Introduction", 0)
    writer.add_outline_item("Conclusion", 2)
    writer.add_outline_item("Conclusion Redux", 2)  # same page as "Conclusion" — dropped
    outlined = tmp_path / "outlined.pdf"
    with open(outlined, "wb") as f:
        writer.write(f)

    drafter = draft.get_drafter("application/application_pdf")
    result, blocks = run_drafter(
        drafter, outlined, corpus_root=None, record_id="b" * 64, record_metadata={}
    )
    assert result.get("fields", {})["page_count"] == 3
    assert [(b.atom, b.address) for b in blocks] == [
        ("structural", "page=1"),
        ("text", "page=1&bbox=0,0.0992,1,0.0831"),
        ("text", "page=2&bbox=0,0.1046,1,0.0146"),
        ("structural", "page=3"),
        ("text", "page=3&bbox=0,0.1046,1,0.0146"),
    ]
    intro_mark, page1_text, _page2_text, concl_mark, page3_text = blocks
    assert intro_mark.level == 1 and intro_mark.body == "Introduction"
    assert concl_mark.level == 1 and concl_mark.body == "Conclusion"  # "Redux" dropped
    assert "1. Introduction" in page1_text.body
    assert "Body text on page three only." in page3_text.body


def test_pdf_introspect_shape_signal(tmp_path):
    """Born-digital vs scanned is the drafter's own advisory shape signal
    (`pdf_introspect.probe_page`'s `shape_hint`) — this test pins the underlying
    image-coverage measurement directly, independent of the drafter. Coverage keys on
    full-page-image area, not vendor strings."""
    import pypdfium2 as pdfium
    from pypdf import PdfReader

    from corpus import pdf_introspect

    for name, scanned in (("onepager.pdf", True), ("born_text.pdf", False)):
        reader = PdfReader(str(_FIXTURES / name))
        doc = pdfium.PdfDocument(str(_FIXTURES / name))
        try:
            probe = pdf_introspect.probe_document(reader, doc)
        finally:
            doc.close()
        cov = probe["pages"][0]["image_coverage"]
        if scanned:
            assert cov >= pdf_introspect.SCANNED_COVERAGE
            assert probe["pages"][0]["shape_hint"].startswith("scanned")
        else:
            assert cov < pdf_introspect.SCANNED_COVERAGE
            assert probe["pages"][0]["shape_hint"] in ("born-digital", "no-text")


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

    from tests._draftlib import draft_for_test

    rc = draft_for_test(root, rid)
    assert rc == 0

    post = records.load(paths.record_path(root, rid))
    assert records.derived_state(post) == "rendered"  # stored content, no governing form
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


def test_draft_is_idempotent_on_rerun(tmp_path):
    """3.0: `derive_record` (the transitional draft core) is idempotent — re-running it strips
    the attested layer before re-applying, so it never doubles embeds/issues (the 2.x
    non-stub refusal is replaced by idempotence)."""
    from tests._draftlib import draft_for_test

    root = _make_corpus(tmp_path)
    rid = _ingest(root, "sample.png", "image/png", "png")

    assert draft_for_test(root, rid) == 0
    first = records.load(paths.record_path(root, rid))
    n1 = len(list(records.iter_embed_blocks(first)))
    assert draft_for_test(root, rid) == 0  # re-run: no duplication
    second = records.load(paths.record_path(root, rid))
    assert len(list(records.iter_embed_blocks(second))) == n1


# ---------- HTML drafter ---------- #


def test_html_drafter_registered_and_axis_aligned():
    assert "text/text_html" in draft.REGISTRY
    # *(3.6)* The historical drafter/resolver lockstep is deliberately SEVERED (§12.28):
    # the address space is the total child-index path (§6.1.1) with no membership
    # predicate, and the drafter's tag tuple is a free emit heuristic. What must now hold
    # instead is that the two FROZEN whitelists never change again — the resolver's
    # legacy copy reads pre-remap records, and the EPUB axis is its own contract until it
    # gets the same amendment. Pin both to literals so any edit screams.
    frozen = (
        "section", "article", "p", "ul", "ol", "dl", "table",
        "pre", "blockquote", "figure",
        "h1", "h2", "h3", "h4", "h5", "h6",
        "img",
    )
    assert frozen == transforms_html._LEGACY_ADDRESSABLE_TAGS
    from corpus import epub as epub_mod

    assert frozen == epub_mod._ADDRESSABLE_TAGS
    # The shared surface is now the path walk itself — importable by drafters and
    # resolvable by the transform, with nothing to configure.
    assert transforms_html.element_path is not None
    assert transforms_html.resolve_element_path is not None


def test_html_drafter_addresses_dl_definition_list(tmp_path, run_drafter):
    """A `<dl>` is a content-bearing block — the peer of `<ul>`/`<ol>` — so the emit
    heuristic annotates it; its `<dt>`/`<dd>` items get no annotation, exactly as `<li>`
    doesn't. *(v35)* Under the total ordinal space its ADDRESS never depended on the
    tuple: it is the element's document-order position (§6.1.1), so a heuristic edit like
    the one that motivated this test (§12.28's `<dl>` incident) can no longer move any
    address."""
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
    result, segs = run_drafter(drafter, binary, corpus_root=root, record_id=rid, record_metadata={})

    # The wrapper claims the body's element children, each by its own ORDINAL: h1(1),
    # p(2), dl(3), and the trailing p — NOT ordinal 4, because dl's own children (dt, dd)
    # occupy ordinals 4 and 5 first, pushing it to 6.
    assert len(segs) == 1
    seg = segs[0]
    assert isinstance(seg, segments.Segment)
    assert seg.address == ["el=1", "el=2", "el=3", "el=6"]

    body = BeautifulSoup(seg.body, "html.parser")
    dl = body.find("dl")
    assert dl is not None and dl.get("data-el") == "3"
    # The dl's items carry no annotation of their own (peers of <li>).
    assert body.find("dt").get("data-el") is None
    assert body.find("dd").get("data-el") is None
    # The trailing <p> is the document's 6th element overall — its own ordinal, owed to
    # nothing about its position among siblings.
    assert body.find_all("p")[-1].get("data-el") == "6"
    # Resolver side: walking the annotated ordinal in the RAW artifact reaches the same dl.
    raw_soup = BeautifulSoup(binary.read_bytes(), "html.parser")
    reached = transforms_html.resolve_ordinal(transforms_html.path_root(raw_soup), 3)
    assert reached.name == "dl"
    # The attested stamp (§7.1) rides the artifact fields: pinned parser + total count +
    # `scheme: ordinal` (v35) — the only grammar this drafter writes going forward.
    stamp = (result.get("fields") or {})["addressing"]
    assert stamp["parser"] == "html.parser"
    assert stamp["elements"] == len(raw_soup.find_all(True))
    assert stamp["scheme"] == "ordinal"


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

    # Exactly one wrapping text segment claiming the body's element children (§6.1.1 —
    # each child's subtree; nav/div/main/footer/script in this fixture), each named by
    # its own document-order ORDINAL (v35) — not its position among siblings, which
    # differ here because earlier siblings carry descendant elements of their own.
    assert len(segs) == 1
    seg = segs[0]
    assert isinstance(seg, segments.Segment)
    assert seg.atom == "text"
    assert seg.address == ["el=1", "el=4", "el=6", "el=20", "el=21"]
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
    # The PNG appears twice (inside the first <figure>, then directly under <main>) →
    # one embed with a list of ordinals (§6.1.1, v35).
    png = by_type["image/png"]
    assert png["address"] == ["el=11", "el=15"]
    assert png["fields"]["width"] == 8 and png["fields"]["height"] == 6
    assert png["fields"]["alt"] == "Diagram one"
    # GIF appears once → scalar ordinal.
    assert by_type["image/gif"]["address"] == "el=17"
    # SVG: PIL can't open it, so dimensions come from the SVG width=/height= attrs.
    svg = by_type["image/svg+xml"]
    assert svg["address"] == "el=19"
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


def test_html_drafter_div_soup_addresses_fine_now(tmp_path, run_drafter):
    """*(3.6, §12.28)* The `unaddressable-content` issue and the guaranteed-broken
    `el=1` fallback are RETIRED: under the total path space a `<div>`-soup page is
    addressable like anything else. The exact page shape that forced the old fallback
    now drafts quietly, its wrapper address names the real overlay div, and the address
    resolves. The one remnant degenerate — visible content as bare text nodes with no
    element under <body> at all — gets the new `elementless-body` flag and NO segment
    (there is no honest address to give one)."""
    p = tmp_path / "dialog.html"
    p.write_text(
        "<!DOCTYPE html><html><head><title>Article Not Found</title></head>"
        "<body><div id='overlay'><span>Article Not Found</span>"
        "<div>The article you are trying to view could not be found.</div>"
        "</div></body></html>",
        encoding="utf-8",
    )
    drafter = draft.get_drafter("text/text_html")
    result, segs = run_drafter(
        drafter, p, record_id="0" * 64, canonical_algo="blake3-canonical-html"
    )

    assert not [
        i for i in result.get("issues") or []
        if i.get("subtype") in ("unaddressable-content", "elementless-body")
    ]
    assert len(segs) == 1
    assert segs[0].address == "el=1"  # the overlay div IS the document's first element
    raw_soup = BeautifulSoup(p.read_bytes(), "html.parser")
    reached = transforms_html.resolve_ordinal(transforms_html.path_root(raw_soup), 1)
    assert reached.name == "div" and reached.get("id") == "overlay"

    # The remnant degenerate: bare text directly under <body>, no element children.
    q = tmp_path / "baretext.html"
    q.write_text(
        "<!DOCTYPE html><html><head><title>t</title></head>"
        "<body>Just some words, no markup at all.</body></html>",
        encoding="utf-8",
    )
    bare, bare_segs = run_drafter(
        drafter, q, record_id="1" * 64, canonical_algo="blake3-canonical-html"
    )
    flagged = [
        i for i in bare.get("issues") or []
        if i["id"] == "partial-content" and i.get("subtype") == "elementless-body"
    ]
    assert len(flagged) == 1
    assert flagged[0]["severity"] == "warning"
    assert flagged[0]["detector"].startswith("corpus.draft.text/text_html@")
    assert bare_segs == []


def test_html_draft_cli_pipeline_and_lint(tmp_path):
    """End-to-end `corpus draft` against an ingested HTML snapshot, then lint."""
    root = _make_corpus(tmp_path)
    rid = _ingest(root, "article.html", "text/html", "html")

    class Args:
        target = rid
        corpus_root = str(root)

    from tests._draftlib import draft_for_test
    assert draft_for_test(root, rid) == 0

    post = records.load(paths.record_path(root, rid))
    assert records.derived_state(post) == "rendered"  # stored content, no governing form
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
    """The drafter's pre-strip `el=` ORDINALS (v35) align with the resolver's raw-artifact
    walk: resolving an embed's ordinal returns the decoded image at the right size. The
    drafted record carries the `addressing:` stamp with `scheme: ordinal`, so the resolver
    reads the ordinal grammar."""
    root = _make_corpus(tmp_path)
    rid = _ingest(root, "article.html", "text/html", "html")

    class Args:
        target = rid
        corpus_root = str(root)

    from tests._draftlib import draft_for_test
    assert draft_for_test(root, rid) == 0

    post = records.load(paths.record_path(root, rid))
    stamp = records.el_addressing(post)
    assert stamp is not None and stamp.get("scheme") == "ordinal"  # the §7.1 stamp landed
    # el=11 is the first PNG occurrence (8x6); el=17 is the GIF (4x4).
    png_path = resolver.resolve(f"corpus://{rid}?el=11", root)
    with Image.open(png_path) as im:
        assert im.size == (8, 6)
    gif_path = resolver.resolve(f"corpus://{rid}?el=17", root)
    with Image.open(gif_path) as im:
        assert im.size == (4, 4)
    # And the LEGACY spelling of the same element no longer resolves silently to a
    # different element: on an ordinal-stamped record `el=4` is the cookie-banner <div>
    # (a container with no inline bytes) — never the old whitelist's 4th entry.
    from corpus.transforms import NotMaterializable

    with pytest.raises(NotMaterializable):
        raw_soup = BeautifulSoup(
            LocalArtifactStore(root).local_path(rid, "html").read_bytes(), "html.parser"
        )
        ref = transforms_html.extract_el(raw_soup, "4", {"el_addressing": stamp})
        transforms_html.htmlel_bytes(ref)


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
    # the el= resolver materialises the same largest variant (drafter/resolver agree).
    # `el=` now yields an HtmlElRef; an <img> ref renders to a PIL image terminally.
    # The value is a §6.1.1 path, read under the stamp the drafter emitted.
    stamp = (result.get("fields") or {})["addressing"]
    value = str(emb["address"]).split("=", 1)[1]
    ref = transforms_html.extract_el(
        BeautifulSoup(p.read_bytes(), "html.parser"), value, {"el_addressing": stamp}
    )
    img = transforms_html.render_htmlel_image(ref, {})
    assert img.size == (40, 32)


def _png_data_uri(w: int, h: int) -> str:
    import io as _io

    buf = _io.BytesIO()
    Image.new("RGB", (w, h), (1, 2, 3)).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _bytes_data_uri(media_type: str, raw: bytes) -> str:
    return f"data:{media_type};base64," + base64.b64encode(raw).decode()


def test_legacy_predicate_is_frozen_with_media_carriers():
    """`legacy_is_addressable` is the FROZEN pre-3.6 membership predicate — the exact
    enumeration every unstamped record's stored addresses were written under, kept so the
    resolver's legacy branch and the §12.28 remap read them unchanged. It admits the
    structural whitelist plus inline-media carriers (`<video>`/`<audio>`,
    `<a href="data:…">`), but NOT a bare `<a>` / `<source>` — so the per-message
    `<a href="sms://…">` deep links the imessage exporter emits never consumed an index."""
    soup = BeautifulSoup(
        "<p>x</p>"
        '<img src="data:image/png;base64,AA==">'
        "<video><source src=\"data:video/mp4;base64,AA==\"></video>"
        "<audio><source src=\"data:audio/mp4;base64,AA==\"></audio>"
        '<a href="data:text/x-vcard;base64,AA==">card</a>'
        '<a href="sms://open?message-guid=X">timestamp</a>'
        '<source src="data:video/mp4;base64,AA==">',
        "html.parser",
    )
    addressable = [t.name for t in soup.find_all(transforms_html.legacy_is_addressable)]
    # p, img, video, audio, a[data:] — in document order. The sms:// <a> and the bare
    # <source> are excluded.
    assert addressable == ["p", "img", "video", "audio", "a"]
    sms_a = soup.find("a", href=lambda h: h and h.startswith("sms://"))
    assert transforms_html.legacy_is_addressable(sms_a) is False


def test_html_drafter_materializes_video_audio_attachment_embeds(tmp_path, run_drafter):
    """The drafter materializes every inline-media carrier — not just `<img>` — into an
    embed, strips the (potentially huge) base64 from the body, and leaves a body-empty
    `el=N` positioning marker. The non-`data:` `<a href="sms://…">` link stays in the body
    and off the `el=` axis."""
    img_uri = _png_data_uri(6, 4)
    video_bytes = b"\x00\x00\x00\x18ftypmp42FAKEVIDEOBYTES"
    vcard_bytes = b"BEGIN:VCARD\nVERSION:3.0\nFN:Jane Doe\nEND:VCARD\n"
    p = tmp_path / "thread.html"
    p.write_text(
        "<html><body>"
        '<p data-x="1"><a href="sms://open?message-guid=A">Dec 01, 2025</a> Me</p>'
        f'<img src="{img_uri}" alt="a photo">'
        f'<video controls><source src="{_bytes_data_uri("video/mp4", video_bytes)}"></video>'
        f'<a href="{_bytes_data_uri("text/x-vcard", vcard_bytes)}">'
        "Click to download Jane Doe.vcf (46.00 B)</a>"
        "</body></html>",
        encoding="utf-8",
    )
    drafter = draft.get_drafter("text/text_html")
    result, blocks = run_drafter(
        drafter, p, record_id="0" * 64, canonical_algo="blake3-canonical-html"
    )
    embeds = {e["media_type"]: e for e in (result.get("embeds") or [])}
    assert set(embeds) == {"image/png", "video/mp4", "text/x-vcard"}
    # The attachment carries its recovered filename; the video carries no dimensions.
    assert embeds["text/x-vcard"]["fields"].get("filename") == "Jane Doe.vcf"
    assert "width" not in embeds["video/mp4"]["fields"]
    assert embeds["image/png"]["fields"]["width"] == 6

    # Transports are the blake3 of the decoded bytes (round-trip identity).
    import blake3 as _b3

    assert embeds["video/mp4"]["transport"] == f"blake3:{_b3.blake3(video_bytes).hexdigest()}"

    # Body: every base64 payload stripped; carriers survive as body-empty markers; the
    # sms:// link stays.
    text_seg = next(b for b in blocks if isinstance(b, segments.Segment))
    body = text_seg.body
    assert "base64" not in body and "FAKEVIDEO" not in body
    soup = BeautifulSoup(body, "html.parser")
    assert soup.find("video").get("data-el") is not None
    assert not soup.find("video").find("source")  # <source> removed
    assert soup.find("img").get("src") is None
    assert soup.find("a", attrs={"data-el": True}).get("href") is None  # attachment href gone
    assert soup.find("a", href=lambda h: h and h.startswith("sms://")) is not None


def test_field_pairs_preserve_images_and_addressable_content(tmp_path, run_drafter):
    """`_convert_field_pairs` rewrites `<div><div>Label</div><div>Value</div></div>`
    to `<p><strong>Label:</strong> Value</p>` from `get_text()` only — which silently
    DROPS any `<img>` (it contributes no text) and with it the gallery embed.
    Regression (Costco PDP `d1d74f97`): the disqualifier now rejects a child holding
    ANY addressable element (`_ADDRESSABLE_TAGS`), so image- or `<dl>`-bearing pairs
    are left intact while genuine inline-text pairs still convert."""
    import io

    def png(w, h):
        buf = io.BytesIO()
        Image.new("RGB", (w, h), (1, 2, 3)).save(buf, "PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    p = tmp_path / "pdp.html"
    p.write_text(
        "<html><body>"
        "<div><div>Brand</div><div>Alani Nu</div></div>"  # genuine pair -> converts
        "<div><div>Gallery</div><div>8 photos"  # img-bearing pair -> left intact
        f'<div id="corpus-gallery-fullres"><img src="{png(12, 9)}" alt="front"></div>'
        "</div></div>"
        "<div><div>Terms</div><div><dl><dt>A</dt><dd>B</dd></dl></div></div>"  # dl pair -> intact
        "</body></html>",
        encoding="utf-8",
    )
    drafter = draft.get_drafter("text/text_html")
    result, segs = run_drafter(drafter, p, record_id="0" * 64)

    # The gallery image survived to an embed — it was silently eaten before the fix.
    embeds = result.get("embeds") or []
    assert len(embeds) == 1
    assert embeds[0]["media_type"] == "image/png"
    assert embeds[0]["fields"]["width"] == 12 and embeds[0]["fields"]["height"] == 9

    body = BeautifulSoup(segs[0].body, "html.parser")
    # The genuine inline-text pair still collapses to <p><strong>Label:</strong> value>.
    strongs = [s.get_text() for s in body.find_all("strong")]
    assert "Brand:" in strongs
    # Image- and dl-bearing pairs are NOT collapsed: their addressable content survives.
    img = body.find("img")
    assert img is not None and img.get("data-el")
    assert body.find("dl") is not None
    assert "Gallery:" not in strongs and "Terms:" not in strongs


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

    from tests._draftlib import draft_for_test
    assert draft_for_test(root, rid_a) == 0
    assert draft_for_test(root, rid_b) == 0  # no longer merges (canonical off)

    # canonical disabled → scoped recompute never runs → no merge: both records persist.
    assert paths.record_path(root, rid_b).exists()
    a = records.load(paths.record_path(root, rid_a))
    b = records.load(paths.record_path(root, rid_b))
    assert "canonical" not in a.metadata and "canonical" not in b.metadata


def test_origin_meta_overlay_parses_producer_declared_metas():
    """`<meta name="corpus-origin-*">` tags declare a uri-less origin's overlay (spec §7.2):
    `corpus-origin-schema` → the overlay id; each `corpus-origin-<field>` → an extended field;
    a repeated field name collects into a list."""
    from bs4 import BeautifulSoup

    from corpus.draft.html import _origin_meta_overlay

    html = (
        "<html><head>"
        '<meta name="corpus-origin-schema" content="imessage-export">'
        '<meta name="corpus-origin-chat_name" content="Family group">'
        '<meta name="corpus-origin-phone_number" content="+14035551234">'
        '<meta name="corpus-origin-phone_number" content="+15875559876">'
        '<meta name="description" content="ignored">'
        "</head><body></body></html>"
    )
    schema_id, fields = _origin_meta_overlay(BeautifulSoup(html, "html.parser"))
    assert schema_id == "imessage-export"
    assert fields["chat_name"] == "Family group"
    assert fields["phone_number"] == ["+14035551234", "+15875559876"]  # repeated → list
    # No corpus-origin metas → empty.
    assert _origin_meta_overlay(BeautifulSoup("<html></html>", "html.parser")) == (None, {})


def test_local_code_loads_corpus_shapers(tmp_path):
    """`load_corpus_modules` imports `<root>/shapers/*.py` by path so they self-register —
    including a module that defines a `@dataclass` (which resolves its module via
    `sys.modules`, so the loader must register the module there before exec). Idempotent."""
    from corpus import local_code, shape

    d = tmp_path / "shapers"
    d.mkdir()
    (d / "mine.py").write_text(
        "from dataclasses import dataclass\n"
        "from corpus.shape import register_shaper\n"
        "@dataclass\n"
        "class _M:\n"
        "    x: int = 0\n"
        "@register_shaper('mine-form')\n"
        "def shape_mine(*args, **kwargs):\n"
        "    return None\n",
        encoding="utf-8",
    )
    try:
        assert shape.get_shaper("mine-form") is None
        local_code.load_corpus_modules(tmp_path, "shapers")
        fn = shape.get_shaper("mine-form")
        assert fn is not None and fn.__name__ == "shape_mine"
        # A `_`-prefixed file is skipped; absent dir / None root are no-ops.
        local_code.load_corpus_modules(tmp_path, "shapers")  # idempotent — no re-import/error
        local_code.load_corpus_modules(None, "shapers")
    finally:
        shape.REGISTRY.pop("mine-form", None)
        local_code._loaded.discard((str(tmp_path.resolve()), "shapers"))


def test_html_resolver_materializes_octet_stream_labeled_image():
    """The `<img>` resolver path sniffs an image inlined under a generic
    `data:application/octet-stream` label (imessage-exporter does this) rather than
    rejecting it — the bytes are decoded and PIL determines the real format."""
    import io

    from bs4 import BeautifulSoup

    buf = io.BytesIO()
    Image.new("RGB", (5, 4), (10, 20, 30)).save(buf, "PNG")
    uri = "data:application/octet-stream;base64," + base64.b64encode(buf.getvalue()).decode()
    img = BeautifulSoup(f'<img src="{uri}">', "html.parser").find("img")

    out = transforms_html._img_tag_to_pil(img, "test")
    assert out.size == (5, 4)
