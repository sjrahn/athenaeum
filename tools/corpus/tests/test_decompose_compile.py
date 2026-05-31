"""Decompose ↔ compile round-trip tests, including embed-in-metadata-zone routing."""

from __future__ import annotations

import hashlib
from pathlib import Path

import frontmatter

from corpus import recordbuild, records, restub, schemas, segments


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _make_golden_record_file(corpus_root: Path) -> Path:
    p = corpus_root / "records" / "aa" / ("a" * 64 + ".md")
    p.parent.mkdir(parents=True)
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": "a" * 64,
            "description": "Round-trip golden.",
            "status": "draft",
            "transport": "sha256:" + "b" * 64,
            "touch": ["corpus.ingest@0.1.0", "corpus.draft.mime/application/pdf@0.1.0"],
        }
    )
    records.set_artifact_block(post, mime="application/pdf", fields={"title": "G", "page_count": 2})
    records.append_origin_block(
        post,
        uri="https://example.com/g.pdf",
        snapshot="2026-05-31T00:00:00Z",
    )
    records.append_classify_block(post, namespace="document", id="document")
    records.append_embed_block(
        post,
        media_type="image/png",
        address="page=1&bbox=0.1,0.1,0.5,0.5",
        transport="blake3:" + "c" * 64,
        fields={"alt": "Cover"},
    )
    sec = segments.Section(
        address="pages=1-2",
        entry="Pages",
        segments=[
            segments.Segment(atom="text", address="page=1", body="One."),
            segments.Segment(atom="text", address="page=2", body="Two."),
        ],
    )
    post.content = segments.emit([sec])
    records.append_issue_block(
        post,
        id="format-loss",
        severity="warning",
        resolution="open",
        detector="corpus.draft.mime/application/pdf@0.1.0",
    )
    records.dump(post, p)
    return p


def test_decompose_compile_roundtrip_preserves_every_block(tmp_path):
    """A record decomposed and recompiled is byte-identical to the original
    (modulo canonical ordering)."""
    root = _make_corpus(tmp_path)
    rec = _make_golden_record_file(root)
    original_text = rec.read_text("utf-8")
    original_sha = hashlib.sha256(rec.read_bytes()).hexdigest()

    # Decompose.
    workdir = tmp_path / "work"
    workdir.mkdir()
    post = records.load(rec)
    blocks = segments.iter_blocks(post.content or "")
    recordbuild.write_workdir(
        post, blocks, workdir, source=str(rec), orig_sha256=f"sha256:{original_sha}"
    )

    # Manifest must list the embed (metadata zone) before any section/seg.
    manifest = (workdir / "manifest.corpus").read_text("utf-8")
    embed_pos = manifest.index("\nembed ")
    section_pos = manifest.index("\nsection ")
    seg_pos = manifest.index("\nseg ")
    assert embed_pos < section_pos < seg_pos

    # Compile.
    rebuilt = recordbuild.read_workdir(workdir, root)
    records.dump(rebuilt, rec)
    rebuilt_text = rec.read_text("utf-8")
    assert rebuilt_text == original_text, "decompose→compile must round-trip byte-identically"


def test_compile_routes_embed_to_metadata_zone(tmp_path):
    """Reconciliation #1: `embed` ops produce metadata-zone embeds; the content
    body holds only sections/segments."""
    root = _make_corpus(tmp_path)
    rec = _make_golden_record_file(root)
    workdir = tmp_path / "work"
    workdir.mkdir()
    post = records.load(rec)
    blocks = segments.iter_blocks(post.content or "")
    recordbuild.write_workdir(
        post, blocks, workdir, source=str(rec), orig_sha256="sha256:x"
    )
    rebuilt = recordbuild.read_workdir(workdir, root)
    assert len(list(records.iter_embed_blocks(rebuilt))) == 1
    assert "<!--embed" not in (rebuilt.content or "")


def test_restub_preserves_byte_and_provenance_state(tmp_path):
    root = _make_corpus(tmp_path)
    rec = _make_golden_record_file(root)
    original_id = "a" * 64

    returned_id = restub.restub(rec)
    assert returned_id == original_id

    re_loaded = records.load(rec)
    # Survives:
    assert re_loaded.metadata["id"] == original_id
    assert re_loaded.metadata["transport"] == "sha256:" + "b" * 64
    assert records.media_type_for(re_loaded) == "application/pdf"
    assert records.title_for(re_loaded) == "G"
    origins = list(records.iter_origin_blocks(re_loaded))
    assert len(origins) == 1
    assert origins[0]["fields"]["uri"] == "https://example.com/g.pdf"
    # Resets:
    assert re_loaded.metadata["status"] == "stub"
    assert re_loaded.metadata["description"] == ""
    assert list(records.iter_classify_blocks(re_loaded)) == []
    assert list(records.iter_embed_blocks(re_loaded)) == []
    assert list(records.iter_issue_blocks(re_loaded)) == []
    assert (re_loaded.content or "").strip() == ""
    # Touch chain: first entry kept + re-stub touch appended.
    chain = re_loaded.metadata["touch"]
    assert isinstance(chain, list)
    assert chain[0] == "corpus.ingest@0.1.0"
    assert chain[-1].startswith("corpus.re-stub@")
