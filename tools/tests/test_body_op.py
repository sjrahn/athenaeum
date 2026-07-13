"""The `body` derivation op (spec §6.2, 3.0) — the record's faithful mechanical body,
derived from the artifact on demand. The equivalence that makes retiring the draft stage
reproducible: `derive_body` produces exactly the content zone the (transitional) draft stage
stores, because both run the same drafter through the same `build_content_zone` core."""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter

from corpus import derive, hashing, paths, records, resolver, schemas
from corpus._cli import draft as draft_cli
from corpus.store import LocalArtifactStore


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _ingest_json(root: Path, text: str) -> str:
    src = root / "doc.json"
    src.write_text(text, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "json", src)
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": rid, "title": "", "description": "", "status": "stub",
         "transport": f"sha256:{h['sha256']}", "touch": "corpus.ingest@0.1.0"}
    )
    records.set_artifact_block(post, mime="application/json", fields={})
    records.append_origin_block(post, uri=f"file://{src.resolve()}",
                                snapshot="2026-07-12T00:00:00Z")
    records.dump(post, paths.record_path(root, rid))
    return rid


def test_derive_body_equals_drafted_content_zone(tmp_path):
    """The op's output == what `corpus draft` stores (the reproducibility guarantee)."""
    root = _make_corpus(tmp_path)
    rid = _ingest_json(root, json.dumps([{"a": 1}, {"b": 2}], indent=2) + "\n")
    path = paths.record_path(root, rid)

    # Derived body from the stub (record untouched).
    stub = records.load(path)
    derived = derive.derive_body(stub, root)
    assert stub.metadata["status"] == "stub"  # derivation did not mutate the record
    assert (stub.content or "") == ""          # stub body still empty

    # What the (transitional) draft stage stores.
    drafted = records.load(path)
    draft_cli.derive_record(drafted, root)
    assert derived.strip() == (drafted.content or "").strip()
    assert "<!--segment text/code" in derived


def test_resolver_body_op(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_json(root, json.dumps({"x": 1}, indent=2) + "\n")
    out = resolver.resolve(f"corpus://{rid}?body", root)
    assert out.is_file() and out.suffix == ".txt"
    text = out.read_text("utf-8")
    assert "<!--segment text/code" in text
    # Cache hit on a second resolve.
    assert resolver.resolve(f"corpus://{rid}?body", root) == out


def test_corpus_body_cli_derives_for_empty_stub(tmp_path, capsys):
    from corpus._cli import body as body_cli

    root = _make_corpus(tmp_path)
    rid = _ingest_json(root, json.dumps([1, 2, 3], indent=2) + "\n")

    class _Args:
        target = rid
        derived = False
        corpus_root = str(root)

    rc = body_cli.run(_Args())
    assert rc == 0
    out = capsys.readouterr().out
    assert "<!--segment text/code" in out  # derived (the stub has no stored body)
