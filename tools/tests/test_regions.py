"""Crop-region save (`corpus.regions.save_regions`) — the library behind the write API.

Pure-library tests (no `[api]` extra): a tiny on-disk corpus, drive `save_regions`
directly, assert the content-zone merge, metadata/title preservation, touch chain, and
the validation failures.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

from corpus import records, regions, schemas, segments


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _image_record(root: Path) -> Path:
    """Single-image record (paged=False): sectionless top-level segments, one of them
    already bbox-addressed."""
    rid = "a" * 64
    p = root / "records" / "aa" / f"{rid}.md"
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": rid,
            "title": "Wiring Diagram — Front Lighting",
            "description": "An image.",
            "transport": "blake3:" + "b" * 64,
            "touch": ["corpus.ingest@0.1.0", "corpus.draft.mime/image/png@0.1.0"],
        }
    )
    records.set_artifact_block(post, mime="image/png", fields={"title": "diagram"})
    records.append_origin_block(
        post, uri="https://example.com/d.png", snapshot="2026-06-01T00:00:00Z"
    )
    post.content = segments.emit(
        [
            segments.Segment(atom="image", address="bbox=0.0,0.0,1.0,1.0", body=""),
            segments.Segment(atom="text", address="el=1", body="caption text", entry="Caption"),
        ]
    )
    records.dump(post, p)
    return p


def _pdf_record(root: Path) -> Path:
    """Paged PDF record (paged=True): sectioned by outline, page-addressed children."""
    rid = "c" * 64
    p = root / "records" / "cc" / f"{rid}.md"
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": rid,
            "title": "Service Bulletin — Brakes",
            "description": "A bulletin.",
            "transport": "sha256:" + "d" * 64,
            "touch": ["corpus.ingest@0.1.0", "corpus.draft.mime/application/pdf@0.1.0"],
        }
    )
    records.set_artifact_block(
        post, mime="application/pdf", fields={"title": "SB", "page_count": 2}
    )
    sec = segments.Section(
        address="pages=1-2",
        entry="Body",
        segments=[
            segments.Segment(atom="text", address="page=1", body="One."),
            segments.Segment(atom="text", address="page=2&bbox=0.1,0.1,0.2,0.2", body=""),
        ],
    )
    post.content = segments.emit([sec])
    records.dump(post, p)
    return p


def test_save_regions_sectionless_replaces_bbox_keeps_rest(tmp_path):
    root = _make_corpus(tmp_path)
    rec = _image_record(root)

    out = regions.save_regions(
        root,
        "a" * 64,
        [
            {"box": [0.1, 0.2, 0.3, 0.4], "atom": "image", "overlay": "", "entry": ""},
            {"box": [0.5, 0.5, 0.2, 0.2], "atom": "text", "overlay": "captions"},
        ],
    )
    assert out["bbox_segment_count"] == 2
    assert out["addresses"] == ["bbox=0.1,0.2,0.3,0.4", "bbox=0.5,0.5,0.2,0.2"]

    post = records.load(rec)
    blocks = segments.iter_blocks(post.content or "")
    addrs = [b.address for b in blocks if isinstance(b, segments.Segment)]
    # The old image bbox is gone; the non-bbox `el=1` text segment survives; the two new
    # bbox segments are present.
    assert "bbox=0.0,0.0,1.0,1.0" not in addrs
    assert "el=1" in addrs
    assert "bbox=0.1,0.2,0.3,0.4" in addrs
    assert "bbox=0.5,0.5,0.2,0.2" in addrs
    # Top-level segments keep their entry (the surviving caption); the new text segment
    # carries the captions overlay.
    new_text = next(
        b
        for b in blocks
        if isinstance(b, segments.Segment) and b.address == "bbox=0.5,0.5,0.2,0.2"
    )
    assert new_text.overlay == "text/captions"


def test_save_regions_preserves_title_and_metadata(tmp_path):
    root = _make_corpus(tmp_path)
    rec = _image_record(root)
    before = records.load(rec)

    regions.save_regions(root, "a" * 64, [{"box": [0.1, 0.1, 0.1, 0.1], "atom": "image"}])

    after = records.load(rec)
    assert after.metadata["title"] == "Wiring Diagram — Front Lighting"
    assert after.metadata["description"] == "An image."
    assert records.title_for(after) == "Wiring Diagram — Front Lighting"
    assert records.artifact_block(after) == records.artifact_block(before)
    assert list(records.iter_origin_blocks(after)) == list(records.iter_origin_blocks(before))


def test_save_regions_appends_touch_and_coalesces(tmp_path):
    root = _make_corpus(tmp_path)
    rec = _image_record(root)

    regions.save_regions(root, "a" * 64, [{"box": [0.1, 0.1, 0.1, 0.1], "atom": "image"}])
    chain = records.load(rec).metadata["touch"]
    assert chain[-1] == "corpus.regions@0.1.0"

    regions.save_regions(root, "a" * 64, [{"box": [0.2, 0.2, 0.1, 0.1], "atom": "image"}])
    chain = records.load(rec).metadata["touch"]
    assert chain[-1] == "corpus.regions@0.1.0_2"


def test_save_regions_paged_places_into_section_and_drops_entry(tmp_path):
    root = _make_corpus(tmp_path)
    rec = _pdf_record(root)

    out = regions.save_regions(
        root,
        "c" * 64,
        [
            {"page": 1, "box": [0.3, 0.3, 0.4, 0.1], "atom": "text", "overlay": "ocr", "entry": "x"}
        ],
    )
    assert out["addresses"] == ["page=1&bbox=0.3,0.3,0.4,0.1"]

    blocks = segments.iter_blocks(records.load(rec).content or "")
    assert all(isinstance(b, segments.Section) for b in blocks)  # still sectioned
    sec = blocks[0]
    addrs = [s.address for s in sec.segments]
    assert "page=1" in addrs  # non-bbox page text preserved
    assert "page=2&bbox=0.1,0.1,0.2,0.2" not in addrs  # old bbox dropped
    placed = next(s for s in sec.segments if s.address == "page=1&bbox=0.3,0.3,0.4,0.1")
    assert placed.overlay == "text/ocr"
    assert placed.entry is None  # in-section segment can't carry a TOC entry


def test_save_regions_rejects_bad_box(tmp_path):
    root = _make_corpus(tmp_path)
    _image_record(root)
    with pytest.raises(regions.RegionSaveError):
        regions.save_regions(root, "a" * 64, [{"box": [0.1, 0.1, 1.5, 0.2], "atom": "image"}])
    with pytest.raises(regions.RegionSaveError):
        regions.save_regions(root, "a" * 64, [{"box": [0.1, 0.1, 0.0, 0.2], "atom": "image"}])


def _mixed_statement_record(root: Path) -> Path:
    """Mixed-artifact PDF (§4.3.2.1): a formless page-1 cover letter, then a `statement`
    section over pages 2-6 (the case the parser fix admits)."""
    rid = "e" * 64
    p = root / "records" / "ee" / f"{rid}.md"
    (root / "records" / "ee").mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": rid, "title": "March Statement", "description": "A statement.",
         "transport": "sha256:" + "f" * 64,
         "touch": ["corpus.ingest@0.1.0"]}
    )
    records.set_artifact_block(post, mime="application/pdf", fields={"page_count": 6})
    cover = segments.Segment(atom="image", address="page=1", entry="Cover",
                             description="Cover letter accompanying the March statement.")
    sec = segments.Section(
        form="statement", address="pages=2-6", entry="Statement",
        extra={"account": "…7841", "period": "2026-03"},
        segments=[
            segments.Segment(atom="text", overlay="text/ocr", address="page=2", body="opening"),
            segments.Segment(atom="text", overlay="text/ocr", address="page=6", body="closing"),
        ],
    )
    post.content = segments.emit([cover, sec])
    records.dump(post, p)
    return p


def test_save_regions_mixed_record_preserves_formless_and_places_top_level(tmp_path):
    root = _make_corpus(tmp_path)
    rec = _mixed_statement_record(root)

    out = regions.save_regions(
        root, "e" * 64,
        [
            {"page": 1, "box": [0.1, 0.1, 0.2, 0.2], "atom": "image"},  # formless → top-level
            {"page": 3, "box": [0.2, 0.2, 0.3, 0.1], "atom": "text", "overlay": "ocr"},  # section
        ],
    )
    assert out["addresses"] == ["page=1&bbox=0.1,0.1,0.2,0.2", "page=3&bbox=0.2,0.2,0.3,0.1"]

    blocks = segments.iter_blocks(records.load(rec).content or "")
    top_addrs = [b.address for b in blocks if isinstance(b, segments.Segment)]
    # The formless cover-letter segment SURVIVES (not dropped) …
    assert "page=1" in top_addrs
    # … and the region on the formless page rides TOP-LEVEL (no containing section ≠ error).
    assert "page=1&bbox=0.1,0.1,0.2,0.2" in top_addrs
    # The region on a statement page landed IN the section.
    sec = next(b for b in blocks if isinstance(b, segments.Section))
    assert "page=3&bbox=0.2,0.2,0.3,0.1" in [s.address for s in sec.segments]
    # Before-only order preserved: the section is last, formless segments precede it.
    assert isinstance(blocks[-1], segments.Section)


def test_save_regions_rejects_unknown_overlay(tmp_path):
    """The cropper's historical `caption` typo (bundled overlay is `captions`)."""
    root = _make_corpus(tmp_path)
    _image_record(root)
    with pytest.raises(regions.RegionSaveError):
        regions.save_regions(
            root, "a" * 64, [{"box": [0.1, 0.1, 0.2, 0.2], "atom": "text", "overlay": "caption"}]
        )


def test_save_regions_page_without_section_rides_top_level(tmp_path):
    """A region on a page no section covers is NOT an error (superseding the old reject): it
    rides at the top level — the mixed-artifact / cover-letter case (§4.3.2.1)."""
    root = _make_corpus(tmp_path)
    rec = _pdf_record(root)
    out = regions.save_regions(
        root, "c" * 64, [{"page": 9, "box": [0.1, 0.1, 0.2, 0.2], "atom": "image"}]
    )
    assert out["addresses"] == ["page=9&bbox=0.1,0.1,0.2,0.2"]
    blocks = segments.iter_blocks(records.load(rec).content or "")
    top_addrs = [b.address for b in blocks if isinstance(b, segments.Segment)]
    assert "page=9&bbox=0.1,0.1,0.2,0.2" in top_addrs  # rode top-level, not an error
    assert any(isinstance(b, segments.Section) for b in blocks)  # the section is intact
