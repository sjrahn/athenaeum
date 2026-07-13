"""The `members` derivation op (spec §6.2, 3.0) — the container's member manifest, derived
from the record's attested embed blocks. A record-level op: it reads only the record, so it
needs no materialized container bytes."""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter

from corpus import paths, records, resolver, schemas


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _manifest_record(root: Path) -> str:
    rid = "a" * 64
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": rid, "title": "", "description": "d", "status": "stub",
         "touch": "corpus.ingest@0.1.0"}
    )
    records.set_artifact_block(post, mime="application/zip", fields={"member_count": 2})
    records.append_origin_block(post, uri=None, snapshot="2026-01-01T00:00:00Z",
                                fields={"filename": "bundle.zip"})
    records.append_embed_block(post, media_type="text/plain", address="path=a/one.txt",
                               transport="blake3:" + "1" * 64, fields={"bytes": 10})
    records.append_embed_block(post, media_type="image/png", address="path=b/two.png",
                               transport="blake3:" + "2" * 64, fields={"bytes": 2048})
    records.dump(post, paths.record_path(root, rid))
    return rid


def test_members_op_derives_manifest(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _manifest_record(root)
    out = resolver.resolve(f"corpus://{rid}?members", root)
    assert out.is_file() and out.suffix == ".json"
    data = json.loads(out.read_text("utf-8"))
    assert data["count"] == 2
    addrs = {m["address"]: m for m in data["members"]}
    assert set(addrs) == {"path=a/one.txt", "path=b/two.png"}
    assert addrs["path=a/one.txt"]["transport"] == "blake3:" + "1" * 64
    assert addrs["path=a/one.txt"]["media_type"] == "text/plain"
    assert addrs["path=b/two.png"]["bytes"] == 2048
    # A sidecar with the derivation metadata rides alongside.
    assert resolver.furi.cache_sidecar_path(out).is_file()
    # Cache hit: a second resolve returns the same path.
    assert resolver.resolve(f"corpus://{rid}?members", root) == out


def test_members_op_needs_no_container_bytes(tmp_path):
    """The op reads only the record — no artifact/container is stored, yet it resolves."""
    root = _make_corpus(tmp_path)
    rid = _manifest_record(root)
    assert not (root / "artifacts").exists()  # no bytes on disk
    out = resolver.resolve(f"corpus://{rid}?members", root)
    assert json.loads(out.read_text("utf-8"))["count"] == 2


def test_members_op_flattens_repeated_address(tmp_path):
    """An embed whose bytes appear at multiple positions (list address) enumerates one
    member entry per position."""
    root = _make_corpus(tmp_path)
    rid = "b" * 64
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": rid, "title": "", "description": "d", "status": "stub",
         "touch": "corpus.ingest@0.1.0"}
    )
    records.set_artifact_block(post, mime="application/zip", fields={})
    records.append_origin_block(post, uri=None, snapshot="2026-01-01T00:00:00Z",
                                fields={"filename": "x.zip"})
    records.append_embed_block(post, media_type="text/plain",
                               address=["path=a.txt", "path=b.txt"],
                               transport="blake3:" + "3" * 64, fields={"bytes": 5})
    records.dump(post, paths.record_path(root, rid))
    out = resolver.resolve(f"corpus://{rid}?members", root)
    data = json.loads(out.read_text("utf-8"))
    assert data["count"] == 2
    assert {m["address"] for m in data["members"]} == {"path=a.txt", "path=b.txt"}
