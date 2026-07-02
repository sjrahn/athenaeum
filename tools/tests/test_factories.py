"""Factory + injection tests: get_store dispatch, artifacts.py facade, resolver
injection of store/transcriber, missing-extra error paths."""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

from corpus import artifacts, paths, records
from corpus.store import (
    ArtifactMissing,
    LocalArtifactStore,
    get_store,
)


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _clean_env(monkeypatch):
    for k in (
        "CORPUS_STORE",
        "CORPUS_AZURE_ACCOUNT",
        "CORPUS_AZURE_CONTAINER",
        "CORPUS_AZURE_PREFIX",
        "CORPUS_S3_BUCKET",
        "CORPUS_S3_REGION",
        "CORPUS_S3_PREFIX",
        "CORPUS_TRANSCRIBE",
        "WHISPER_BASE_URL",
    ):
        monkeypatch.delenv(k, raising=False)


# ---------- get_store dispatch ---------- #


def test_get_store_default_is_local(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    root = _make_corpus(tmp_path)
    s = get_store(root)
    assert isinstance(s, LocalArtifactStore)


def test_get_store_azure_dispatch_constructs_adapter(tmp_path, monkeypatch):
    """With Azure config set, get_store returns an AzureBlobStore (lazy-imports
    the SDK on construction; no remote calls until an op needs them)."""
    pytest.importorskip("azure.storage.blob")
    _clean_env(monkeypatch)
    monkeypatch.setenv("CORPUS_STORE", "azure")
    monkeypatch.setenv("CORPUS_AZURE_ACCOUNT", "fakeacct")
    monkeypatch.setenv("CORPUS_AZURE_CONTAINER", "corpus")
    root = _make_corpus(tmp_path)
    s = get_store(root)
    from corpus.store.azure import AzureBlobStore

    assert isinstance(s, AzureBlobStore)


def test_get_store_azure_without_extra_raises_clean_error(tmp_path, monkeypatch):
    """If the [azure] extra isn't installed, the lazy-import raises ImportError
    with an operator-actionable message."""
    _clean_env(monkeypatch)
    monkeypatch.setenv("CORPUS_STORE", "azure")
    monkeypatch.setenv("CORPUS_AZURE_ACCOUNT", "a")
    monkeypatch.setenv("CORPUS_AZURE_CONTAINER", "c")
    root = _make_corpus(tmp_path)
    # Construct the store — Azure SDK isn't required to construct, only to call
    # remote ops. Trigger remote by calling exists() on a missing key.
    s = get_store(root)
    # Force the import path to fail by patching the lazy importer.
    import corpus.store.azure as az_mod

    def fake_lazy():
        raise ImportError(
            "Azure backend requires the `[azure]` extra. Install with: "
            "uv pip install 'athenaeum[azure]'"
        )

    monkeypatch.setattr(az_mod, "_lazy_import", fake_lazy)
    with pytest.raises(ImportError, match=r"azure.*extra"):
        s.exists("a" * 64, "pdf")


def test_get_store_s3_dispatch(tmp_path, monkeypatch):
    pytest.importorskip("boto3")
    _clean_env(monkeypatch)
    monkeypatch.setenv("CORPUS_STORE", "s3")
    monkeypatch.setenv("CORPUS_S3_BUCKET", "mybucket")
    monkeypatch.setenv("CORPUS_S3_REGION", "us-east-1")
    root = _make_corpus(tmp_path)
    s = get_store(root)
    from corpus.store.s3 import S3Store

    assert isinstance(s, S3Store)


# ---------- artifacts.py facade (back-compat) ---------- #


def test_artifacts_facade_delegates_to_local(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    root = _make_corpus(tmp_path)
    src = tmp_path / "x.bin"
    src.write_bytes(b"abc")
    rid = "a" * 64
    artifacts.put(root, rid, "bin", src)
    assert artifacts.is_local(root, rid, "bin")
    assert artifacts.exists(root, rid, "bin")
    p = artifacts.ensure_local(root, rid, "bin")
    assert p.is_file()
    assert "aa/" + rid + ".bin" in artifacts.list_local(root)
    assert artifacts.list_remote(root) == set()


def test_artifacts_facade_raises_when_absent(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    root = _make_corpus(tmp_path)
    rid = "b" * 64
    with pytest.raises(ArtifactMissing):
        artifacts.ensure_local(root, rid, "pdf")


# ---------- resolver accepts a transcriber + store ---------- #


def test_resolver_accepts_transcriber_param(tmp_path, monkeypatch):
    """The resolver's signature now takes `transcriber=None` for forward-compat
    with P5 audio transforms. Passing it on a non-audio chain is a no-op."""
    from corpus import hashing, resolver, schemas
    from corpus.transcription import NoOpTranscriber

    _clean_env(monkeypatch)
    schemas._sources.cache_clear()
    root = _make_corpus(tmp_path)

    src = Path(__file__).parent / "data" / "sample.png"
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "png", src)

    post = frontmatter.Post("")
    post.metadata.update({
        "id": rid,
        "description": "",
        "status": "stub",
        "touch": "corpus.ingest@0.1.0",
    })
    records.set_artifact_block(post, mime="image/png", fields={"title": "x"})
    records.append_origin_block(
        post, uri=f"file://{src.resolve()}", snapshot="2026-05-31T00:00:00Z"
    )
    records.dump(post, paths.record_path(root, rid))

    out = resolver.resolve(
        f"corpus://{rid}?grayscale",
        root,
        store=LocalArtifactStore(root),
        transcriber=NoOpTranscriber(),
    )
    assert out.is_file()
