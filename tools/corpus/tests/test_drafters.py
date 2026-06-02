"""Drafter registry + per-MIME drafters (PDF, image) tests."""

from __future__ import annotations

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
    records.set_artifact_block(post, mime=mime, fields={"title": src.stem})
    records.append_origin_block(
        post, uri=f"file://{src.resolve()}", snapshot="2026-05-31T00:00:00Z"
    )
    records.dump(post, paths.record_path(corpus_root, rid))
    return rid


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


def test_pdf_drafter_emits_canonical_and_metadata(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest(root, "onepager.pdf", "application/pdf", "pdf")
    binary = LocalArtifactStore(root).local_path(rid, "pdf")
    drafter = draft.get_drafter("application/application_pdf")
    assert drafter is not None
    result = drafter(binary, corpus_root=root, record_id=rid, record_metadata={})
    assert "page_count" in (result.get("fields") or {})
    assert result.get("fields", {})["page_count"] == 2
    canonical = result.get("canonical") or ""
    assert canonical.startswith("blake3:")
    assert len(canonical.split(":", 1)[1]) == 64
    # PIL-generated PDF has no extractable text → 0 segments + 0 issues, no outline.
    assert result.get("embeds") == []


def test_image_drafter_emits_metadata_and_positioning_marker(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest(root, "sample.png", "image/png", "png")
    binary = LocalArtifactStore(root).local_path(rid, "png")
    drafter = draft.get_drafter("image/image_png")
    assert drafter is not None
    result = drafter(binary, corpus_root=root, record_id=rid, record_metadata={})
    fields = result.get("fields") or {}
    assert fields["image_width"] == 200
    assert fields["image_height"] == 150
    assert fields["image_format"] == "PNG"
    # Spec §4.3.2.2: image segment is a body-empty positioning marker at bbox=0,0,1,1.
    segs = result.get("segments") or []
    assert len(segs) == 1
    s = segs[0]
    assert isinstance(s, segments.Segment)
    assert s.atom == "image"
    assert s.address == "bbox=0,0,1,1"
    assert s.body == ""
    # Canonical present.
    assert result.get("canonical", "").startswith("blake3:")


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
    assert post.metadata.get("canonical", "").startswith("blake3:")
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


def test_html_drafter_emits_segment_embeds_and_canonical(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest(root, "article.html", "text/html", "html")
    binary = LocalArtifactStore(root).local_path(rid, "html")
    drafter = draft.get_drafter("text/text_html")
    assert drafter is not None
    result = drafter(binary, corpus_root=root, record_id=rid, record_metadata={})

    # Artifact fields are document metadata only — the canonical/final URLs and the
    # capture timestamp belong on the ORIGIN block, not here (spec §7.2).
    fields = result.get("fields") or {}
    assert fields["html_title"] == "Sample Article — Demo Publisher"
    assert fields["html_lang"] == "en"
    assert fields["og_site_name"] == "Demo Publisher"
    assert "canonical_url" not in fields
    assert "final_url" not in fields
    assert "fetched_at" not in fields
    assert result.get("title") == "Sample Article — Demo Publisher"
    # Canonical (<link rel=canonical>) + final URL (corpus-capture-url meta) come back as
    # origin aliases for the origin block, not artifact fields.
    aliases = result.get("origin_uri_aliases") or []
    assert "https://example.com/sample-article" in aliases

    # Canonical: blake3-canonical-html → `blake3:<64hex>`.
    canonical = result.get("canonical") or ""
    assert canonical.startswith("blake3:")
    assert len(canonical.split(":", 1)[1]) == 64

    # Exactly one wrapping text segment spanning every addressable element (1..11).
    segs = result.get("segments") or []
    assert len(segs) == 1
    seg = segs[0]
    assert isinstance(seg, segments.Segment)
    assert seg.atom == "text"
    assert seg.address == "el=1-11"
    assert (seg.perceptual or "").startswith("simhash:")

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


def test_html_drafter_preserves_form_wrapped_content(tmp_path):
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
    result = drafter(p, corpus_root=tmp_path, record_id="a" * 64, record_metadata={})

    body = (result.get("segments") or [None])[0].body
    assert "123 Main St" in body and "2 beds, 2 baths." in body  # content survives the form
    # The image inside the page-wrapping form is embedded (was silently dropped before).
    embeds = result.get("embeds") or []
    assert any(e["media_type"] == "image/gif" for e in embeds)


def test_html_drafter_flags_empty_body(tmp_path):
    """Drafter-deterministic issue, emitted in our spec §4.3.3.1 shape."""
    p = tmp_path / "empty.html"
    p.write_text(
        "<!DOCTYPE html><html><head><title>x</title></head>"
        "<body><script>var a=1;</script></body></html>",
        encoding="utf-8",
    )
    drafter = draft.get_drafter("text/text_html")
    result = drafter(p, record_id="0" * 64, canonical_algo="blake3-canonical-html")
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
    assert post.metadata.get("canonical", "").startswith("blake3:")
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


def test_html_drafter_prefers_largest_srcset(tmp_path):
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
    result = drafter(p, record_id="0" * 64, canonical_algo="blake3-canonical-html")
    embeds = result.get("embeds") or []
    assert len(embeds) == 1
    emb = embeds[0]
    # the 2x variant (40x32), NOT the displayed 10x8 thumbnail
    assert emb["fields"]["width"] == 40 and emb["fields"]["height"] == 32
    # the el= resolver materialises the same largest variant (drafter/resolver agree)
    n = str(emb["address"]).split("=", 1)[1]
    img = transforms_html.extract_el(BeautifulSoup(p.read_bytes(), "html.parser"), n, {})
    assert img.size == (40, 32)
