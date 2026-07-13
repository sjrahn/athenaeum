"""The `body` derivation op (spec §6.2, 3.0) — the record's faithful mechanical body,
derived from the artifact on demand. The equivalence that makes retiring the draft stage
reproducible: `derive_body` produces exactly the content zone the (transitional) draft stage
stores, because both run the same drafter through the same `build_content_zone` core."""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter

from corpus import derive, hashing, paths, recordbuild, records, resolver, schemas
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


def test_stub_decompose_derives_the_body(tmp_path):
    """`corpus decompose` on a 3.0 stub (empty content zone) derives the body into the working
    dir — so the normalize substrate has content to edit — and marks it derived-at-decompose.
    stub-decompose ≡ the `body` op's output (compile round-trips it)."""
    from corpus._cli import decompose as decompose_cli

    root = _make_corpus(tmp_path)
    rid = _ingest_json(root, json.dumps([{"a": 1}, {"b": 2}], indent=2) + "\n")
    work = tmp_path / "w"

    class _Args:
        target = rid
        into = work
        corpus_root = str(root)

    assert decompose_cli.run(_Args()) == 0

    # The lock records the provenance: the body was DERIVED, with the op id.
    lock = json.loads((work / ".corpus-decompose.json").read_text("utf-8"))
    assert lock["body_source"] == "derived"
    assert lock["body_op"].startswith("corpus.body@")
    # The manifest header flags it so a compile is understood as authoring.
    manifest = (work / "manifest.corpus").read_text("utf-8")
    assert "BODY DERIVED at decompose time" in manifest

    # stub-decompose ≡ body-op output: compiling the working dir reproduces derive_body().
    stub = records.load(paths.record_path(root, rid))
    compiled = recordbuild.read_workdir(work, root)
    assert (compiled.content or "").strip() == derive.derive_body(stub, root).strip()


def test_normalized_decompose_uses_stored_body(tmp_path):
    """A record with a stored content zone decomposes it verbatim (body_source: stored)."""
    from corpus import segments
    from corpus._cli import decompose as decompose_cli

    root = _make_corpus(tmp_path)
    rid = _ingest_json(root, json.dumps({"x": 1}, indent=2) + "\n")
    rf = paths.record_path(root, rid)
    post = records.load(rf)
    post.metadata["status"] = "normalized"
    post.content = segments.emit([segments.Segment(atom="text", address="line=1", body="authored")])
    records.dump(post, rf)
    work = tmp_path / "w2"

    class _Args:
        target = rid
        into = work
        corpus_root = str(root)

    assert decompose_cli.run(_Args()) == 0
    lock = json.loads((work / ".corpus-decompose.json").read_text("utf-8"))
    assert lock["body_source"] == "stored"
    assert "authored" in (work / "manifest.corpus").read_text("utf-8") or any(
        "authored" in p.read_text("utf-8") for p in (work / "bodies").glob("*")
    )


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
