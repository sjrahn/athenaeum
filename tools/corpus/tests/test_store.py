"""ArtifactStore Protocol + LocalArtifactStore tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from corpus import paths
from corpus.store import ArtifactMissing, ArtifactStore, LocalArtifactStore, get_store
from corpus.store._errors import classify_remote_error


def test_classify_remote_error():
    """Pure error classifier (no SDK import) — covers the cloud error paths that the
    boto3/azure-gated tests can't exercise in a base-install CI."""
    # botocore-style codes.
    assert classify_remote_error("404") == "missing"
    assert classify_remote_error("NoSuchKey") == "missing"
    assert classify_remote_error("403") == "denied"
    assert classify_remote_error("AccessDenied") == "denied"
    assert classify_remote_error("SlowDown") == "operational"
    assert classify_remote_error("RequestTimeout") == "operational"
    assert classify_remote_error("") == "operational"
    # azure-style exception type names (substring match) classify too.
    assert classify_remote_error("ResourceNotFoundError no blob") == "missing"
    assert classify_remote_error("HttpResponseError 404") == "missing"


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def test_local_store_satisfies_protocol(tmp_path):
    """The Protocol is `runtime_checkable`, so we can instance-check at runtime."""
    root = _make_corpus(tmp_path)
    store: ArtifactStore = LocalArtifactStore(root)
    assert isinstance(store, ArtifactStore)


def test_get_store_returns_local_by_default(tmp_path):
    root = _make_corpus(tmp_path)
    store = get_store(root)
    assert isinstance(store, LocalArtifactStore)


def test_local_path_uses_sharded_layout(tmp_path):
    root = _make_corpus(tmp_path)
    store = LocalArtifactStore(root)
    rid = "a" * 64
    p = store.local_path(rid, "pdf")
    assert p == root / "artifacts" / "aa" / f"{rid}.pdf"


def test_put_persists_bytes_and_is_local_flips(tmp_path):
    root = _make_corpus(tmp_path)
    store = LocalArtifactStore(root)
    rid = "b" * 64
    src = tmp_path / "src.pdf"
    src.write_bytes(b"%PDF-1.4\n%%EOF\n")
    assert not store.is_local(rid, "pdf")
    store.put(rid, "pdf", src)
    assert store.is_local(rid, "pdf")
    assert store.exists(rid, "pdf")
    assert store.local_path(rid, "pdf").read_bytes() == b"%PDF-1.4\n%%EOF\n"


def test_ensure_local_returns_path_when_present(tmp_path):
    root = _make_corpus(tmp_path)
    store = LocalArtifactStore(root)
    rid = "c" * 64
    src = tmp_path / "src.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    store.put(rid, "png", src)
    p = store.ensure_local(rid, "png")
    assert p.is_file()


def test_ensure_local_raises_when_absent(tmp_path):
    root = _make_corpus(tmp_path)
    store = LocalArtifactStore(root)
    rid = "d" * 64
    with pytest.raises(ArtifactMissing) as ei:
        store.ensure_local(rid, "pdf")
    msg = str(ei.value)
    assert "not present" in msg
    assert "dd/" in msg  # shard appears in the message
    assert "no remote store" in msg


def test_list_local_walks_sharded_dirs(tmp_path):
    root = _make_corpus(tmp_path)
    store = LocalArtifactStore(root)
    src = tmp_path / "x"
    src.write_bytes(b"x")
    store.put("e" * 64, "txt", src)
    store.put("f" * 64, "txt", src)
    out = store.list_local()
    assert {"ee/" + "e" * 64 + ".txt", "ff/" + "f" * 64 + ".txt"} == out


def test_list_remote_is_empty_for_local_only_store(tmp_path):
    root = _make_corpus(tmp_path)
    store = LocalArtifactStore(root)
    assert store.list_remote() == set()


def test_local_artifact_store_root_property(tmp_path):
    root = _make_corpus(tmp_path)
    store = LocalArtifactStore(root)
    assert store.root == root
