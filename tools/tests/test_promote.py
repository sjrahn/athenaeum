"""`corpus promote` — minting a first-class record for a container member (spec §8.1).

The bytes never leave the container: promote streams + blake3-verifies the member against its
embed's recorded transport, MIME-detects it, and emits a stub whose first origin records the
containment lineage. Re-promoting folds like a re-capture; a hash mismatch is a hard error.
"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

import blake3
import frontmatter
import pytest

from corpus import hashing, paths, records, resolver, schemas, touches
from corpus._cli import draft as draft_cli
from corpus._cli import ingest as ingest_cli
from corpus._cli import promote as promote_cli
from corpus.store import LocalArtifactStore

_PAYLOAD = b"promote me, i live in a zip\n"
_MEMBERS = {
    "note.txt": _PAYLOAD,
    "mail.mbox": b"From a@b Mon Jan  1 00:00:00 2020\nSubject: hi\n\nbody\n",
    "data.json": b'{"k": 1}\n',
}


def _b3(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _container(tmp_path: Path, root: Path, members: dict[str, bytes] | None = None) -> str:
    z = tmp_path / "b.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for name, data in (members if members is not None else _MEMBERS).items():
            zf.writestr(name, data)
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / z.name
    shutil.copy(z, staged)
    assert ingest_cli._ingest_one(root, staged) == 0
    cid = hashing.hash_file(z)["blake3"]
    post = records.load(paths.record_path(root, cid))
    draft_cli.derive_record(post, root)
    records.dump(post, paths.record_path(root, cid))
    return cid


def _promote(root: Path, uri: str) -> int:
    return promote_cli.run(argparse.Namespace(uri=uri, json=False, corpus_root=str(root)))


def _origins(root: Path, rid: str) -> list[dict]:
    return list(records.iter_origin_blocks(records.load(paths.record_path(root, rid))))


# ---------- happy path ---------- #


def test_promote_mints_stub_with_containment_lineage(tmp_path):
    root = _corpus(tmp_path)
    cid = _container(tmp_path, root)
    uri = f"corpus://{cid}?path=note.txt"
    assert _promote(root, uri) == 0

    pid = _b3(_PAYLOAD)
    post = records.load(paths.record_path(root, pid))
    assert post.metadata["id"] == pid
    assert records.derived_state(post) == "proxy"
    assert records.media_type_for(post) == "text/plain"
    assert touches.touch_list(post) == [touches.script_identifier("promote")]
    # Origin records the containment lineage AS HISTORY (uri + member metadata).
    origin = _origins(root, pid)[0]["fields"]
    assert origin["uri"] == uri
    assert origin["filename"] == "note.txt"
    assert "source_modified" in origin
    # Bytes were NOT copied to artifacts/.
    assert not LocalArtifactStore(root).is_local(pid, "txt")


def test_promote_mbox_member_detects_and_hashes(tmp_path):
    root = _corpus(tmp_path)
    cid = _container(tmp_path, root)
    assert _promote(root, f"corpus://{cid}?path=mail.mbox") == 0

    pid = _b3(_MEMBERS["mail.mbox"])
    post = records.load(paths.record_path(root, pid))
    assert records.media_type_for(post) == "application/mbox"  # `From ` magic, not the .mbox ext
    # The mbox schema declares transport_algos: [sha256] → the promoted stub carries it.
    transport = post.metadata.get("transport")
    assert str(transport).startswith("sha256:")
    assert str(transport).split(":", 1)[1] == hashing.hash_bytes(_MEMBERS["mail.mbox"])["sha256"]


def test_promote_json_member_cheap_path_and_resolves(tmp_path):
    root = _corpus(tmp_path)
    cid = _container(tmp_path, root)
    assert _promote(root, f"corpus://{cid}?path=data.json") == 0

    pid = _b3(_MEMBERS["data.json"])
    out = resolver.resolve(f"corpus://{pid}", root)
    assert out.read_bytes() == _MEMBERS["data.json"]


# ---------- verification + folding ---------- #


def test_promote_hash_mismatch_is_a_hard_error(tmp_path):
    root = _corpus(tmp_path)
    cid = _container(tmp_path, root)
    # Corrupt the container's recorded transport for note.txt so the streamed bytes won't match.
    cpost = records.load(paths.record_path(root, cid))
    for emb in cpost.metadata["_embeds"]:
        if emb["address"] == "path=note.txt":
            emb["transport"] = "blake3:" + "0" * 64
    records.dump(cpost, paths.record_path(root, cid))

    with pytest.raises(SystemExit, match="hash mismatch"):
        _promote(root, f"corpus://{cid}?path=note.txt")


def test_re_promote_folds_without_duplicating_origin(tmp_path):
    root = _corpus(tmp_path)
    cid = _container(tmp_path, root)
    uri = f"corpus://{cid}?path=note.txt"
    _promote(root, uri)
    _promote(root, uri)  # second promote of the same member

    pid = _b3(_PAYLOAD)
    origins = _origins(root, pid)
    assert len(origins) == 1  # the containment origin was not duplicated
    # touch coalesces the two promote passes.
    assert touches.touch_list(records.load(paths.record_path(root, pid))) == [
        touches.script_identifier("promote") + "_2"
    ]


def test_promote_folds_into_existing_standalone(tmp_path):
    root = _corpus(tmp_path)
    cid = _container(tmp_path, root)
    pid = _b3(_PAYLOAD)

    # A standalone record for the same bytes already exists (an earlier ingest, §5.2).
    prior = frontmatter.Post("")
    prior.metadata.update({"id": pid, "touch": "corpus.ingest@0"})
    records.set_artifact_block(prior, mime="text/plain", fields={})
    records.append_origin_block(prior, snapshot=touches.now_iso(), fields={"filename": "local.txt"})
    records.dump(prior, paths.record_path(root, pid))

    uri = f"corpus://{cid}?path=note.txt"
    assert _promote(root, uri) == 0
    origins = _origins(root, pid)
    # The prior local-file origin is kept; the containment origin is appended (not replaced).
    assert len(origins) == 2
    uris = {(o["fields"].get("uri")) for o in origins}
    assert uri in uris


def test_bare_uri_is_rejected(tmp_path):
    root = _corpus(tmp_path)
    cid = _container(tmp_path, root)
    with pytest.raises(SystemExit, match="member address"):
        _promote(root, f"corpus://{cid}")


def test_missing_embed_is_rejected(tmp_path):
    root = _corpus(tmp_path)
    cid = _container(tmp_path, root)
    with pytest.raises(SystemExit, match="no embed"):
        _promote(root, f"corpus://{cid}?path=nonexistent.txt")
