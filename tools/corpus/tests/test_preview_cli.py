"""`corpus preview` — the cropping loop's eyes: mark region(s) + fit to a model budget."""

from __future__ import annotations

from pathlib import Path

import frontmatter
from PIL import Image

from corpus import hashing, paths, records, schemas
from corpus._cli import dispatch
from corpus.store import LocalArtifactStore

_FIXTURES = Path(__file__).parent / "data"


def _stage(tmp_path: Path, fixture: str, *, mime: str, ext: str) -> tuple[Path, str]:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()

    src = _FIXTURES / fixture
    hashes = hashing.hash_file(src)
    rid = hashes["blake3"]
    LocalArtifactStore(root).put(rid, ext, src)

    post = frontmatter.Post("")
    post.metadata.update(
        {"id": rid, "description": "", "status": "stub", "touch": "corpus.ingest@0.1.0"}
    )
    records.set_artifact_block(post, mime=mime, fields={"title": fixture})
    records.append_origin_block(
        post, uri=f"file://{src.resolve()}", snapshot="2026-05-31T00:00:00Z"
    )
    records.dump(post, paths.record_path(root, rid))
    return root, rid


def test_preview_marks_and_writes_out(tmp_path):
    root, rid = _stage(tmp_path, "sample.png", mime="image/png", ext="png")
    out = tmp_path / "p.png"
    rc = dispatch(
        ["preview", rid, "--mark", "0.1,0.1,0.3,0.3", "-o", str(out), "--corpus-root", str(root)]
    )
    assert rc == 0
    assert out.is_file()
    with Image.open(out) as im:
        assert im.mode == "RGB"
        assert im.size == (200, 150)  # full image, fit=llm leaves a small image alone


def test_preview_default_fits_llm(tmp_path):
    """Without --full, a big page is fit to the llm budget (long edge <= 1568)."""
    root, rid = _stage(tmp_path, "onepager.pdf", mime="application/pdf", ext="pdf")
    out = tmp_path / "page.png"
    rc = dispatch(
        ["preview", rid, "--page", "1", "--dpi", "400", "-o", str(out), "--corpus-root", str(root)]
    )
    assert rc == 0
    with Image.open(out) as im:
        assert max(im.size) <= 1568


def test_preview_full_skips_fit(tmp_path):
    """--full renders at native resolution (3400x4400 @400dpi)."""
    root, rid = _stage(tmp_path, "onepager.pdf", mime="application/pdf", ext="pdf")
    out = tmp_path / "full.png"
    rc = dispatch(
        [
            "preview", rid, "--page", "1", "--dpi", "400", "--full",
            "-o", str(out), "--corpus-root", str(root),
        ]
    )
    assert rc == 0
    with Image.open(out) as im:
        assert im.size == (3400, 4400)


def test_preview_prints_cache_path(tmp_path, capsys):
    root, rid = _stage(tmp_path, "sample.png", mime="image/png", ext="png")
    rc = dispatch(["preview", rid, "--corpus-root", str(root)])
    assert rc == 0
    printed = capsys.readouterr().out.strip()
    assert printed.endswith(".png")
    assert Path(printed).is_file()


def test_preview_multiple_marks(tmp_path):
    root, rid = _stage(tmp_path, "sample.png", mime="image/png", ext="png")
    out = tmp_path / "multi.png"
    rc = dispatch(
        [
            "preview", rid,
            "--mark", "0.05,0.05,0.2,0.2",
            "--mark", "0.5,0.5,0.3,0.3",
            "-o", str(out), "--corpus-root", str(root),
        ]
    )
    assert rc == 0
    assert out.is_file()


def test_preview_rotate_flag_swaps_dims(tmp_path):
    root, rid = _stage(tmp_path, "sample.png", mime="image/png", ext="png")  # 200x150
    out = tmp_path / "rot.png"
    rc = dispatch(["preview", rid, "--rotate", "90", "-o", str(out), "--corpus-root", str(root)])
    assert rc == 0
    with Image.open(out) as im:
        assert im.size == (150, 200)


def test_preview_from_segments_draws_committed_boxes(tmp_path):
    from corpus import regions

    root, rid = _stage(tmp_path, "sample.png", mime="image/png", ext="png")
    regions.save_regions(
        root,
        rid,
        [
            {"box": [0.1, 0.1, 0.3, 0.2], "atom": "image"},
            {"box": [0.5, 0.5, 0.3, 0.2], "atom": "image"},
        ],
    )
    out = tmp_path / "verify.png"
    rc = dispatch(["preview", rid, "--from-segments", "-o", str(out), "--corpus-root", str(root)])
    assert rc == 0
    with Image.open(out) as im:
        assert im.mode == "RGB"
        assert im.size == (200, 150)  # committed boxes drawn on the full image


def test_preview_from_segments_none_exits_1(tmp_path):
    root, rid = _stage(tmp_path, "sample.png", mime="image/png", ext="png")
    rc = dispatch(["preview", rid, "--from-segments", "--corpus-root", str(root)])
    assert rc == 1  # no committed bbox segments to draw
