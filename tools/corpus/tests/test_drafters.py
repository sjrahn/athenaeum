"""Drafter registry + per-MIME drafters (PDF, image) tests."""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

from corpus import draft, paths, records, schemas, segments
from corpus._cli import draft as draft_cli
from corpus.store import LocalArtifactStore

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
