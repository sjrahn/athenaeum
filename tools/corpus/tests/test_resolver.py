"""Resolver tests — PDF page→image, image bbox/resize/grayscale chains, HTML el=.

Uses tiny deterministic fixtures under tests/data/.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

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
    # Sidecar metadata exists.
    sidecar = out.with_suffix(".json")
    assert sidecar.is_file()
    # Cache hit: second call returns the same path with no error.
    out2 = resolver.resolve(f"corpus://{rid}?page=1", root)
    assert out2 == out


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
