"""Resolver tests — PDF page→image, image bbox/resize/grayscale chains, HTML el=.

Uses tiny deterministic fixtures under tests/data/.
"""

from __future__ import annotations

import frontmatter
from pathlib import Path

from corpus import hashing, paths, records, resolver, schemas, segments
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
    from corpus.store import ArtifactMissing

    import pytest

    with pytest.raises(ArtifactMissing):
        resolver.resolve(f"corpus://{rid}?grayscale", root)
