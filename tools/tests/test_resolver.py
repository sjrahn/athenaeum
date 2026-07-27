"""Resolver tests — PDF page→image, image bbox/resize/grayscale chains, HTML el=.

Uses tiny deterministic fixtures under tests/data/.
"""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter

from corpus import functional_uri as furi
from corpus import hashing, paths, records, resolver, schemas
from corpus.store import LocalArtifactStore

_FIXTURES = Path(__file__).parent / "data"


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _ingest_fixture(corpus_root: Path, fixture_name: str, *, mime: str, ext: str) -> str:
    """Quickly stage a fixture as a corpus record + artifact. Returns the record id."""
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


def test_bare_uri_returns_source_path(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.png", mime="image/png", ext="png")
    out = resolver.resolve(f"corpus://{rid}", root)
    assert out.is_file()
    assert out == (root / "artifacts" / rid[:2] / f"{rid}.png").resolve()


def test_pdf_page_renders_to_cached_png(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "onepager.pdf", mime="application/pdf", ext="pdf")
    out = resolver.resolve(f"corpus://{rid}?page=1", root)
    assert out.is_file()
    assert out.suffix == ".png"
    # Sidecar metadata exists (named after the full cache file: <name>.json).
    sidecar = resolver.furi.cache_sidecar_path(out)
    assert sidecar.is_file()
    # Cache hit: second call returns the same path with no error.
    out2 = resolver.resolve(f"corpus://{rid}?page=1", root)
    assert out2 == out


def test_pdf_page_render_paints_acroform_field_values(tmp_path):
    """AcroForm field values without appearance streams (NeedAppearances form-fill) must
    paint in page renders — requires init_forms() on the resolver's document, without
    which the page renders blank exactly where the filled content is."""
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "formfield.pdf", mime="application/pdf", ext="pdf")
    out = resolver.resolve(f"corpus://{rid}?page=1", root)
    from PIL import Image

    with Image.open(out) as im:
        histogram = im.convert("L").histogram()
    dark_pixels = sum(histogram[:128])
    # The fixture's only content is the field value "FILLED"; a blank render means the
    # form layer was never initialized.
    assert dark_pixels > 100


def test_image_bbox_resize_grayscale_chain(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.png", mime="image/png", ext="png")
    out = resolver.resolve(
        f"corpus://{rid}?bbox=0.1,0.1,0.5,0.5&resize=120x90&grayscale", root
    )
    assert out.is_file()
    assert out.suffix == ".png"
    from PIL import Image

    with Image.open(out) as im:
        assert im.size == (120, 90)
        assert im.mode == "L"  # grayscale


def test_pdf_page_with_bbox_resize_chain(tmp_path):
    """Spec §6: param chain composes left-to-right; type-changing transforms work."""
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "onepager.pdf", mime="application/pdf", ext="pdf")
    out = resolver.resolve(
        f"corpus://{rid}?page=1&bbox=0.0,0.0,0.5,0.5&resize=300x300", root
    )
    assert out.is_file()
    from PIL import Image

    with Image.open(out) as im:
        assert im.size == (300, 300)


# ---- PDF introspection ops (selector + sub-op: text / words / probe / outline) ---- #


def test_pdf_page_text_extracts_embedded_layer(tmp_path):
    """`page=N&text` returns the page's embedded text layer as a cached .txt — NOT an
    OCR of the raster. born_text.pdf carries real vector text."""
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "born_text.pdf", mime="application/pdf", ext="pdf")
    out = resolver.resolve(f"corpus://{rid}?page=1&text", root)
    assert out.suffix == ".txt"
    assert "born-digital" in out.read_text("utf-8")
    out2 = resolver.resolve(f"corpus://{rid}?page=2&text", root)
    assert "Second page" in out2.read_text("utf-8")


def test_pdf_page_words_returns_boxes(tmp_path):
    """`page=N&words` returns JSON word boxes in [0,1] page fractions, origin top-left."""
    import json

    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "born_text.pdf", mime="application/pdf", ext="pdf")
    out = resolver.resolve(f"corpus://{rid}?page=1&words", root)
    assert out.suffix == ".json"
    data = json.loads(out.read_text("utf-8"))
    assert data["page"] == 1
    assert data["word_count"] >= 1
    assert "born" in " ".join(w["text"] for w in data["words"]).lower()
    for w in data["words"]:
        x, y, ww, hh = w["bbox"]
        assert all(0.0 <= v <= 1.0 for v in (x, y, ww, hh))
        assert x + ww <= 1.0 + 1e-6 and y + hh <= 1.0 + 1e-6


def test_pdf_probe_document_reports_per_page_shape(tmp_path):
    """`probe` (whole-doc) reports per-page signals + an advisory shape. onepager.pdf is a
    full-page raster (scanned); born_text.pdf is born-digital with no outline."""
    import json

    root = _make_corpus(tmp_path)
    scan = _ingest_fixture(root, "onepager.pdf", mime="application/pdf", ext="pdf")
    probe = json.loads(resolver.resolve(f"corpus://{scan}?probe", root).read_text("utf-8"))
    assert probe["page_count"] == 2
    assert probe["pages"][0]["image_coverage"] >= 0.9
    assert probe["shape_summary"].startswith("scanned")

    born = _ingest_fixture(root, "born_text.pdf", mime="application/pdf", ext="pdf")
    probe2 = json.loads(resolver.resolve(f"corpus://{born}?probe", root).read_text("utf-8"))
    assert probe2["has_outline"] is False
    assert probe2["pages"][0]["text_char_count"] > 0


def test_pdf_page_probe_single_page(tmp_path):
    import json

    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "born_text.pdf", mime="application/pdf", ext="pdf")
    page = json.loads(resolver.resolve(f"corpus://{rid}?page=1&probe", root).read_text("utf-8"))
    assert page["page"] == 1
    assert page["text_char_count"] > 0
    assert page["shape_hint"] == "born-digital"


def test_pdf_outline_resolves_empty_when_absent(tmp_path):
    """`outline` resolves cleanly to `[]` for a PDF with no bookmarks."""
    import json

    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "born_text.pdf", mime="application/pdf", ext="pdf")
    out = resolver.resolve(f"corpus://{rid}?outline", root)
    assert out.suffix == ".json"
    assert json.loads(out.read_text("utf-8")) == []


def test_pdf_render_flag_matches_bare_page(tmp_path):
    """`page=N&render` is the explicit form of a terminal `page=N` — both -> image."""
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "onepager.pdf", mime="application/pdf", ext="pdf")
    from PIL import Image

    out = resolver.resolve(f"corpus://{rid}?page=1&render", root)
    assert out.suffix == ".png"
    with Image.open(out) as im:
        assert im.size == (1700, 2200)


def test_html_el_extracts_inline_image(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.html", mime="text/html", ext="html")
    # The HTML has h1, p, figure, img, p — find_all returns them in document order.
    # Per html.py addressable tags: section, article, p, ul, ol, table, pre,
    # blockquote, figure, h1-h6, img. So order is:
    #   1=h1, 2=p, 3=figure, 4=img, 5=p
    # el=4 is the <img>.
    out = resolver.resolve(f"corpus://{rid}?el=4", root)
    assert out.is_file()
    from PIL import Image

    with Image.open(out) as im:
        # The inline image matches our blue-with-red-square sample.png.
        assert im.size == (200, 150)


def test_html_el_sidecar_records_engine_version(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.html", mime="text/html", ext="html")
    out = resolver.resolve(f"corpus://{rid}?el=4", root)
    sidecar = furi.cache_sidecar_path(out)
    data = json.loads(sidecar.read_text("utf-8"))
    assert data["engine"] == "html-el@2"


def test_html_el_cache_key_includes_engine_version(tmp_path, monkeypatch):
    """The LIVE `el=` cache key folds in `transforms.html.ENGINE_VERSION` — verified by
    swapping the (monkeypatched) pin between two resolves of the SAME canonical URI and
    observing two distinct cache files (mirrors `test_video_muxing.py`'s
    `test_cache_key_includes_engine_version`)."""
    from corpus.transforms import html as html_tf

    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.html", mime="text/html", ext="html")

    monkeypatch.setattr(html_tf, "ENGINE_VERSION", "html-el@fake-1")
    out1 = resolver.resolve(f"corpus://{rid}?el=4", root)
    sidecar1 = json.loads(furi.cache_sidecar_path(out1).read_text())

    monkeypatch.setattr(html_tf, "ENGINE_VERSION", "html-el@fake-2")
    out2 = resolver.resolve(f"corpus://{rid}?el=4", root)
    sidecar2 = json.loads(furi.cache_sidecar_path(out2).read_text())

    assert out1 != out2
    assert sidecar1["engine"] == "html-el@fake-1"
    assert sidecar2["engine"] == "html-el@fake-2"


def _ingest_html_bytes(corpus_root: Path, html: bytes) -> str:
    """Stage inline HTML bytes as a corpus record + artifact. Returns the record id."""
    import hashlib

    import blake3 as _b3

    rid = _b3.blake3(html).hexdigest()
    LocalArtifactStore(corpus_root).local_path(rid, "html").parent.mkdir(
        parents=True, exist_ok=True
    )
    LocalArtifactStore(corpus_root).local_path(rid, "html").write_bytes(html)
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": rid,
            "description": "",
            "status": "draft",
            "transport": f"sha256:{hashlib.sha256(html).hexdigest()}",
            "touch": "corpus.ingest@0.1.0",
        }
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, uri="https://x.test/t", snapshot="2026-05-31T00:00:00Z")
    records.dump(post, paths.record_path(corpus_root, rid))
    return rid


def _data_uri(media_type: str, raw: bytes) -> str:
    import base64

    return f"data:{media_type};base64," + base64.b64encode(raw).decode()


def test_html_el_video_carrier_materializes_raw_bytes(tmp_path):
    """A terminal `el=N` on a `<video>` carrier materializes the inline `<source>` bytes
    verbatim — cached under the media's native extension, sidecar mime `video/mp4`, NOT a
    rasterized image."""
    import json

    video = b"\x00\x00\x00\x18ftypmp42-not-a-real-codec-but-exact-bytes"
    html = (
        "<html><body><p>hi</p>"
        f'<video controls><source src="{_data_uri("video/mp4", video)}"></video>'
        "</body></html>"
    ).encode()
    root = _make_corpus(tmp_path)
    rid = _ingest_html_bytes(root, html)
    # Order: p(1), video(2). el=2 is the carrier.
    out = resolver.resolve(f"corpus://{rid}?el=2", root)
    assert out.is_file() and out.suffix == ".mp4"
    assert out.read_bytes() == video  # byte-exact round trip
    sidecar = json.loads(resolver.furi.cache_sidecar_path(out).read_text("utf-8"))
    assert sidecar["mime"] == "video/mp4"
    # Cache hit (the polymorphic stem glob) returns the same path without re-deriving.
    assert resolver.resolve(f"corpus://{rid}?el=2", root) == out


def test_html_el_attachment_carrier_materializes_raw_bytes(tmp_path):
    """A terminal `el=N` on an `<a href="data:…">` attachment materializes its bytes."""
    vcard = b"BEGIN:VCARD\nVERSION:3.0\nFN:Jane Doe\nEND:VCARD\n"
    html = (
        "<html><body><p>hi</p>"
        f'<a href="{_data_uri("text/x-vcard", vcard)}">Click to download Jane Doe.vcf</a>'
        "</body></html>"
    ).encode()
    root = _make_corpus(tmp_path)
    rid = _ingest_html_bytes(root, html)
    out = resolver.resolve(f"corpus://{rid}?el=2", root)
    assert out.read_bytes() == vcard


def test_html_el_img_carrier_still_renders_image(tmp_path):
    """Regression: a terminal `el=N` on an `<img>` still renders a PNG image (unchanged),
    and an image-output op after `el=N` (`bbox=`) still promotes the `<img>` to an image."""
    import base64
    import io as _io

    from PIL import Image

    buf = _io.BytesIO()
    Image.new("RGB", (20, 10), (4, 5, 6)).save(buf, "PNG")
    img_uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    html = f'<html><body><p>hi</p><img src="{img_uri}"></body></html>'.encode()
    root = _make_corpus(tmp_path)
    rid = _ingest_html_bytes(root, html)
    out = resolver.resolve(f"corpus://{rid}?el=2", root)
    assert out.suffix == ".png"
    with Image.open(out) as im:
        assert im.size == (20, 10)
    cropped = resolver.resolve(f"corpus://{rid}?el=2&bbox=0,0,0.5,1.0", root)
    assert cropped.suffix == ".png"
    with Image.open(cropped) as im:
        assert im.size == (10, 10)


def test_regenerate_bypasses_cache(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.png", mime="image/png", ext="png")
    first = resolver.resolve(f"corpus://{rid}?grayscale", root)
    first_mtime = first.stat().st_mtime_ns
    import time
    time.sleep(0.01)
    again = resolver.resolve(f"corpus://{rid}?grayscale", root, regenerate=True)
    assert again == first
    assert again.stat().st_mtime_ns > first_mtime  # regenerated


def test_urihash_deterministic_across_runs(tmp_path):
    """Spec §6.3: same URI → same urihash → same cache file path."""
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.png", mime="image/png", ext="png")
    a = resolver.resolve(f"corpus://{rid}?grayscale", root)
    b = resolver.resolve(f"corpus://{rid}?grayscale", root)
    assert a == b


def test_missing_artifact_raises(tmp_path):
    """Resolving a URI whose record has no on-disk artifact raises ArtifactMissing."""
    root = _make_corpus(tmp_path)
    # Record present, but artifact never written.
    rid = "a" * 64
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": rid,
            "description": "",
            "status": "stub",
            "touch": "corpus.ingest@0.1.0",
        }
    )
    records.set_artifact_block(post, mime="image/png", fields={"title": "missing"})
    records.append_origin_block(
        post, uri="file:///nope.png", snapshot="2026-05-31T00:00:00Z"
    )
    records.dump(post, paths.record_path(root, rid))
    import pytest

    from corpus.store import ArtifactMissing

    with pytest.raises(ArtifactMissing):
        resolver.resolve(f"corpus://{rid}?grayscale", root)


# ---- mark= (annotate region on the full image, spec §6.2) ------------------ #


def test_mark_draws_box_on_full_image(tmp_path):
    """`mark=` returns the WHOLE image (sample.png is 200x150) with the region
    outlined — not the crop — and forced to RGB so the stroke shows."""
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.png", mime="image/png", ext="png")
    from PIL import Image

    out = resolver.resolve(f"corpus://{rid}?mark=0.1,0.1,0.4,0.4", root)
    with Image.open(out) as im:
        assert im.size == (200, 150)  # full image, not cropped
        assert im.mode == "RGB"
    # The marked image actually differs from the source pixels.
    src = resolver.resolve(f"corpus://{rid}", root)
    with Image.open(src) as a, Image.open(out) as b:
        assert a.convert("RGB").tobytes() != b.convert("RGB").tobytes()


def test_mark_multiple_regions(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.png", mime="image/png", ext="png")
    from PIL import Image

    out = resolver.resolve(f"corpus://{rid}?mark=0.05,0.05,0.2,0.2;0.5,0.5,0.3,0.3", root)
    with Image.open(out) as im:
        assert im.size == (200, 150)


def test_mark_rejects_out_of_bounds(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.png", mime="image/png", ext="png")
    import pytest

    with pytest.raises(ValueError):
        resolver.resolve(f"corpus://{rid}?mark=0.5,0.5,0.8,0.8", root)


def test_mark_composes_after_pdf_page(tmp_path):
    """`page=` then `mark=`: outline a box on a rendered PDF page (1700x2200 @200dpi)."""
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "onepager.pdf", mime="application/pdf", ext="pdf")
    from PIL import Image

    out = resolver.resolve(f"corpus://{rid}?page=1&mark=0.1,0.1,0.5,0.3", root)
    with Image.open(out) as im:
        assert im.size == (1700, 2200)
        assert im.mode == "RGB"


# ---- fit= (aspect-preserving downscale, spec §6.2) ------------------------- #


def test_fit_box_downscales_preserving_aspect(tmp_path):
    """sample.png 200x150, fit=100x100 → scale 0.5 → 100x75 (aspect kept)."""
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.png", mime="image/png", ext="png")
    from PIL import Image

    out = resolver.resolve(f"corpus://{rid}?fit=100x100", root)
    with Image.open(out) as im:
        assert im.size == (100, 75)


def test_fit_never_upscales(tmp_path):
    """A box larger than the image leaves it untouched (reduce-only)."""
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.png", mime="image/png", ext="png")
    from PIL import Image

    out = resolver.resolve(f"corpus://{rid}?fit=10000x10000", root)
    with Image.open(out) as im:
        assert im.size == (200, 150)


def test_fit_llm_preset_caps_edge_and_pixels(tmp_path):
    """A big PDF page (3400x4400 @400dpi) fit to the llm preset lands within the
    model budget: long edge <= 1568 and total pixels <= the preset cap."""
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "onepager.pdf", mime="application/pdf", ext="pdf")
    from PIL import Image

    from corpus.transforms.image import LLM_MAX_EDGE, LLM_MAX_PIXELS

    out = resolver.resolve(f"corpus://{rid}?page=1&dpi=400&fit=llm", root)
    with Image.open(out) as im:
        assert max(im.size) <= LLM_MAX_EDGE
        # Rounding can nudge a hair over the exact cap; allow a small tolerance.
        assert im.size[0] * im.size[1] <= LLM_MAX_PIXELS * 1.02


def test_fit_llm_passes_small_image_through(tmp_path):
    """An image already within budget is unchanged by fit=llm."""
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.png", mime="image/png", ext="png")
    from PIL import Image

    out = resolver.resolve(f"corpus://{rid}?fit=llm", root)
    with Image.open(out) as im:
        assert im.size == (200, 150)


# ---- the bbox bounds error teaches x,y,w,h (the dominant normalizer trap) ---- #


def test_bbox_bounds_error_names_the_format(tmp_path):
    """A corner-coordinate mistake (x0,y0,x1,y1) must produce an error that names the
    real format and the overflowing axis — not just 'out of bounds'."""
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.png", mime="image/png", ext="png")
    import pytest

    with pytest.raises(ValueError) as exc:
        resolver.resolve(f"corpus://{rid}?bbox=0.15,0.2,0.95,0.45", root)
    msg = str(exc.value)
    assert "x+w" in msg and "WIDTH,HEIGHT" in msg and "corners" in msg


# ---- rotate= / auto_orient / contrast (spec §6.2) -------------------------- #


def _stage_image_file(corpus_root, src, *, mime, ext):
    """Stage an arbitrary on-disk image as a record + artifact; return its id."""
    hashes = hashing.hash_file(src)
    rid = hashes["blake3"]
    LocalArtifactStore(corpus_root).put(rid, ext, src)
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": rid, "description": "", "status": "stub", "touch": "corpus.ingest@0.1.0"}
    )
    records.set_artifact_block(post, mime=mime, fields={"title": src.name})
    records.append_origin_block(post, uri=f"file://{src}", snapshot="2026-05-31T00:00:00Z")
    records.dump(post, paths.record_path(corpus_root, rid))
    return rid


def test_rotate_90_swaps_dimensions(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.png", mime="image/png", ext="png")  # 200x150
    from PIL import Image

    out = resolver.resolve(f"corpus://{rid}?rotate=90", root)
    with Image.open(out) as im:
        assert im.size == (150, 200)


def test_rotate_180_keeps_dimensions(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.png", mime="image/png", ext="png")
    from PIL import Image

    out = resolver.resolve(f"corpus://{rid}?rotate=180", root)
    with Image.open(out) as im:
        assert im.size == (200, 150)


def test_rotate_rejects_non_quarter_turn(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.png", mime="image/png", ext="png")
    import pytest

    with pytest.raises(ValueError):
        resolver.resolve(f"corpus://{rid}?rotate=45", root)


def test_auto_orient_applies_exif_orientation(tmp_path):
    """A landscape JPEG tagged EXIF orientation=6 (display rotated) comes back upright
    (dimensions swapped) under auto_orient."""
    root = _make_corpus(tmp_path)
    from PIL import Image

    src = tmp_path / "rot.jpg"
    img = Image.new("RGB", (240, 120), "white")
    exif = img.getexif()
    exif[274] = 6  # Orientation tag → rotate on display
    img.save(src, exif=exif)
    rid = _stage_image_file(root, src, mime="image/jpeg", ext="jpg")

    out = resolver.resolve(f"corpus://{rid}?auto_orient", root)
    with Image.open(out) as im:
        assert im.size == (120, 240)  # swapped — orientation applied


def test_auto_orient_is_noop_without_exif(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.png", mime="image/png", ext="png")
    from PIL import Image

    out = resolver.resolve(f"corpus://{rid}?auto_orient", root)
    with Image.open(out) as im:
        assert im.size == (200, 150)


def test_autocontrast_and_contrast_render(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_fixture(root, "sample.png", mime="image/png", ext="png")
    from PIL import Image

    for uri in (f"corpus://{rid}?autocontrast", f"corpus://{rid}?contrast=2.0"):
        out = resolver.resolve(uri, root)
        with Image.open(out) as im:
            assert im.size == (200, 150)
    import pytest

    with pytest.raises(ValueError):
        resolver.resolve(f"corpus://{rid}?contrast=abc", root)


def test_text_element_raises_not_materializable_not_a_plain_error():
    """A text element (`el=3` → `<table>`) names EXACTLY what the address said — the
    element is there and its content is text, so there are no bytes to render. That is
    reported as `NotMaterializable`, distinct from `el=99` naming nothing at all.

    The distinction is load-bearing for `corpus lint --resolve`: without it, every
    correct text citation in the corpus reads as broken provenance (measured: 26 such
    false positives in a 30-record sample before this type existed). Asserted on the
    TYPE so no caller has to match on message text."""
    import pytest
    from bs4 import BeautifulSoup

    from corpus.transforms import NotMaterializable
    from corpus.transforms import html as thtml

    soup = BeautifulSoup(
        "<html><body><h3>Heading</h3><table><tr><td>x</td></tr></table></body></html>",
        "html.parser",
    )
    ref = thtml.extract_el(soup, "1", {})
    with pytest.raises(NotMaterializable):
        thtml.htmlel_bytes(ref)

    # An IN-BOUNDS span names a real envelope of elements — same class, not a defect.
    with pytest.raises(NotMaterializable):
        thtml.extract_el(soup, "1-2", {})

    # Naming NOTHING stays an ordinary error: the address is wrong, not byte-less.
    with pytest.raises(ValueError) as exc:
        thtml.extract_el(soup, "99", {})
    assert not isinstance(exc.value, NotMaterializable)


def test_out_of_range_span_is_an_error_not_declared_coverage():
    """A span envelope past the end of the element list names NOTHING, so it must fail
    like any other bad address — not pass as `NotMaterializable`.

    This was the hole: the transforms short-circuited every range form to
    `NotMaterializable` before looking at the numbers, so `el=94-102` on a nine-element
    artifact read as declared coverage. Eight of the seventeen out-of-range addresses in
    the corpus hid behind it, including three whole records the single-index check never
    saw. Asserted in BOTH directions so the fix cannot regress into over-reporting."""
    import pytest
    from bs4 import BeautifulSoup

    from corpus.transforms import NotMaterializable
    from corpus.transforms import html as thtml

    soup = BeautifulSoup("<body><h3>a</h3><p>b</p></body>", "html.parser")

    with pytest.raises(ValueError) as exc:
        thtml.extract_el(soup, "1-3", {})
    assert not isinstance(exc.value, NotMaterializable)
    assert "out of range" in str(exc.value)

    # A reversed span is likewise nonsense, and says so.
    with pytest.raises(ValueError) as rev:
        thtml.extract_el(soup, "2-1", {})
    assert "precedes" in str(rev.value)

    # ...while the in-bounds envelope still reads as declared coverage.
    with pytest.raises(NotMaterializable):
        thtml.extract_el(soup, "1-2", {})


def test_inline_svg_is_not_materializable_not_undecodable():
    """PIL has no SVG rasterizer, so a perfectly valid inline SVG reaches the decode path
    and fails there. That is a capability gap, NOT corrupt bytes — and calling it "failed
    to decode" made two records read as broken provenance for a whole arc while their
    bytes were fine (spec §12.24). Valid `<svg>` root → NotMaterializable; real garbage
    stays an ordinary error."""
    import base64

    import pytest
    from bs4 import BeautifulSoup

    from corpus.transforms import NotMaterializable
    from corpus.transforms import html as thtml

    def _img(payload: bytes, media_type: str) -> str:
        b64 = base64.b64encode(payload).decode()
        return f'<html><body><img src="data:{media_type};base64,{b64}"></body></html>'

    svg = b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" '
    svg += b'width="320" height="296" viewBox="0 0 600 135"><rect width="10" height="10"/></svg>'
    soup = BeautifulSoup(_img(svg, "image/svg+xml"), "html.parser")
    ref = thtml.extract_el(soup, "1", {})
    with pytest.raises(NotMaterializable, match="SVG"):
        thtml.render_htmlel_image(ref, {})

    junk = BeautifulSoup(_img(b"\x00\x01not an image at all", "image/png"), "html.parser")
    ref2 = thtml.extract_el(junk, "1", {})
    with pytest.raises(ValueError) as exc:
        thtml.render_htmlel_image(ref2, {})
    assert not isinstance(exc.value, NotMaterializable)
