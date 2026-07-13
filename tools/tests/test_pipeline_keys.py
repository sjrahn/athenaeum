"""3.0 mime-schema pipeline-key aliasing (spec §7.1, open question 2).

The documented keys are `disposition:` / `attest:` / `derive:`; the 2.x `mode:` / `draft.*`
keep working via aliasing so existing member schemas draft UNMODIFIED. A schema declaring the
NEW keys must attest/derive identically to one declaring the old keys."""

from __future__ import annotations

import zipfile
from pathlib import Path

import frontmatter

from corpus import derive, hashing, paths, records, schemas
from corpus.store import LocalArtifactStore


def test_pipeline_disposition_resolution():
    assert schemas.pipeline_disposition({"disposition": "manifest"}) == "manifest"
    assert schemas.pipeline_disposition({"disposition": "work"}) == "work"
    # aliased from a manifest strategy (old OR new key)
    assert schemas.pipeline_disposition({"draft": {"strategy": "zip-manifest"}}) == "manifest"
    assert schemas.pipeline_disposition({"derive": {"strategy": "zip-manifest"}}) == "manifest"
    assert schemas.pipeline_disposition({"mode": "body-draft"}) == "work"
    assert schemas.pipeline_disposition({}) == "work"


def test_normalize_pipeline_keys_backfills_legacy_view():
    new = {"disposition": "manifest", "derive": {"strategy": "zip-manifest",
                                                 "members": {"root_strip": True}}}
    norm = schemas.normalize_pipeline_keys(new)
    assert norm["draft"]["strategy"] == "zip-manifest"      # derive.strategy → draft.strategy
    assert norm["draft"]["manifest"] == {"root_strip": True}  # derive.members → draft.manifest
    assert norm["mode"] == "manifest"                       # disposition → mode
    # a pure-legacy schema is returned unchanged
    legacy = {"mode": "body-draft", "draft": {"strategy": "zip-manifest"}}
    assert schemas.normalize_pipeline_keys(legacy) is legacy


def _corpus_with_schema(tmp_path: Path, zip_schema_body: str) -> Path:
    """A corpus whose local `application/zip` mime schema is authored with the given body
    (so we can test old-key vs new-key declarations)."""
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    sdir = root / "schema" / "mime" / "application"
    sdir.mkdir(parents=True)
    (sdir / "application_zip.yaml").write_text(
        "applies_to:\n  content_types: [application/zip]\nworking_kind: zip\n" + zip_schema_body,
        encoding="utf-8",
    )
    schemas.cache_clear()
    return root


def _ingest_zip(root: Path) -> str:
    src = root / "b.zip"
    with zipfile.ZipFile(src, "w") as zf:
        zf.writestr("a/one.txt", "hello")
        zf.writestr("b/two.txt", "world")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "zip", src)
    src.unlink()
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": rid, "title": "", "description": "", "status": "stub",
         "transport": f"sha256:{h['sha256']}", "touch": "corpus.ingest@0.1.0"}
    )
    records.set_artifact_block(post, mime="application/zip", fields={})
    records.append_origin_block(post, uri=None, snapshot="2026-01-01T00:00:00Z",
                                fields={"filename": "b.zip"})
    records.dump(post, paths.record_path(root, rid))
    return rid


def _attest_embeds(tmp_path: Path, schema_body: str) -> set[str]:
    root = _corpus_with_schema(tmp_path, schema_body)
    rid = _ingest_zip(root)
    post = records.load(paths.record_path(root, rid))
    derive.attest(post, root, strip=False)
    return {e["address"] for e in records.iter_embed_blocks(post)}


def test_new_keys_attest_identically_to_old_keys(tmp_path):
    """`disposition:` + `derive:` produces the same attested embeds as `mode:` + `draft:`."""
    old = _attest_embeds(tmp_path / "old", "mode: manifest\ndraft:\n  strategy: zip-manifest\n")
    new = _attest_embeds(
        tmp_path / "new", "disposition: manifest\nderive:\n  strategy: zip-manifest\n"
    )
    assert old == new == {"path=a/one.txt", "path=b/two.txt"}
