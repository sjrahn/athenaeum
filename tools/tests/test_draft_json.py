"""application/json passthrough drafter tests."""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter

from corpus import paths, records, schemas, segments
from corpus._cli import draft as draft_cli
from corpus.store import LocalArtifactStore


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _ingest_json(corpus_root: Path, text: str, name: str = "doc") -> str:
    from corpus import hashing

    src = corpus_root / f"{name}.json"
    src.write_text(text, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(corpus_root).put(rid, "json", src)
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
    records.set_artifact_block(post, mime="application/json", fields={})
    records.append_origin_block(
        post, uri=f"file://{src.resolve()}", snapshot="2026-07-12T00:00:00Z"
    )
    records.dump(post, paths.record_path(corpus_root, rid))
    return rid


def _draft(corpus_root: Path, rid: str) -> frontmatter.Post:
    path = paths.record_path(corpus_root, rid)
    post = records.load(path)
    draft_cli.derive_record(post, corpus_root)
    records.dump(post, path)
    return records.load(path)


def test_json_array_drafts_to_one_verbatim_code_segment(tmp_path: Path) -> None:
    text = json.dumps([{"a": 1}, {"b": 2}], indent=2) + "\n"
    root = _make_corpus(tmp_path)
    rid = _ingest_json(root, text)
    post = _draft(root, rid)

    assert post.metadata["status"] == "draft"
    art = records.artifact_block(post)
    assert art["fields"]["json_root"] == "array"
    assert art["fields"]["json_top_count"] == 2

    segs = [b for b in segments.iter_blocks(post.content) if isinstance(b, segments.Segment)]
    assert len(segs) == 1
    (seg,) = segs
    assert seg.atom == "text"
    assert seg.overlay == "text/code"
    assert seg.extra.get("language") == "json"
    # verbatim passthrough, modulo the block grammar's trailing-newline normalization
    assert seg.body == text.rstrip("\n")
    assert seg.address == f"line=1-{text.count(chr(10))}"


def test_json_object_root_counts_keys(tmp_path: Path) -> None:
    root = _make_corpus(tmp_path)
    rid = _ingest_json(root, '{"x": 1, "y": [1, 2, 3]}')
    post = _draft(root, rid)
    art = records.artifact_block(post)
    assert art["fields"]["json_root"] == "object"
    assert art["fields"]["json_top_count"] == 2


def test_malformed_json_passes_through_with_warning_issue(tmp_path: Path) -> None:
    text = '{"unterminated": '
    root = _make_corpus(tmp_path)
    rid = _ingest_json(root, text)
    post = _draft(root, rid)

    art = records.artifact_block(post)
    assert "json_root" not in art["fields"]

    issues = list(records.iter_issue_blocks(post))
    assert any(i.get("id") == "malformed-json" for i in issues)
    (issue,) = [i for i in issues if i.get("id") == "malformed-json"]
    assert issue["fields"].get("severity") == "warning"

    segs = [b for b in segments.iter_blocks(post.content) if isinstance(b, segments.Segment)]
    assert len(segs) == 1
    assert segs[0].body == text
