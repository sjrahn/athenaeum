"""`corpus location move` — relocating a record's standalone copy between store
locations (spec/corpus.md §12.1.1, "Move semantics" paragraph, v22).

Test files use `.json` payloads for the same reason `test_location_promote.py` does:
`application/json` ships a default mime schema, so a real record can be minted for it.
"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

import blake3
import pytest

from corpus import config as config_mod
from corpus import containment, hashing, locationindex, paths, records, schemas
from corpus._cli import draft as draft_cli
from corpus._cli import ingest as ingest_cli
from corpus._cli import location as location_cli
from corpus._cli import promote as promote_cli
from corpus.store import LocalArtifactStore


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)  # empty -> packaged defaults
    schemas.cache_clear()
    return root


def _write_toml(root: Path, text: str) -> None:
    (root / "corpus.toml").write_text(text, "utf-8")


def _store_loc(root: Path, name: str, path: Path, *, extra: str = "") -> None:
    existing = (root / "corpus.toml").read_text("utf-8") if (root / "corpus.toml").is_file() else ""
    existing += f"""
[[corpus.location]]
name = "{name}"
kind = "store"
path = "{path}"
{extra}
"""
    _write_toml(root, existing)


def _ingest_json(root: Path, data: bytes) -> str:
    capture = root / "capture"
    capture.mkdir(exist_ok=True)
    staged = capture / "a.json"
    staged.write_bytes(data)
    assert ingest_cli._ingest_one(root, staged) == 0
    return blake3.blake3(data).hexdigest()


def _move(root: Path, record: str, dest: str) -> int:
    return location_cli.run(
        argparse.Namespace(
            action="move", record=record, dest=dest, all_from=None, corpus_root=str(root)
        )
    )


def _move_all_from(root: Path, source: str, dest: str) -> int:
    return location_cli.run(
        argparse.Namespace(
            action="move", record=None, dest=dest, all_from=source, corpus_root=str(root)
        )
    )


# ---------- co-located <-> store location ---------- #


def test_move_co_located_to_store_location(tmp_path, capsys):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"
    data = b'{"case": "co-located to store"}\n'
    rid = _ingest_json(root, data)
    _store_loc(root, "bulk", bulk)

    assert paths.artifact_path(root, rid, "json").is_file()

    assert _move(root, rid, "bulk") == 0
    out = capsys.readouterr().out
    assert "moved" in out

    dest_file = bulk / paths.shard(rid) / f"{rid}.json"
    assert dest_file.is_file()
    assert dest_file.read_bytes() == data
    assert not paths.artifact_path(root, rid, "json").exists()

    # Record still resolves its bytes through the store location.
    resolved = containment.ensure_local_bytes(root, rid, "json")
    assert resolved == dest_file


def test_move_store_location_back_to_corpus(tmp_path):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"
    data = b'{"case": "back to corpus"}\n'
    rid = _ingest_json(root, data)
    _store_loc(root, "bulk", bulk)
    assert _move(root, rid, "bulk") == 0

    assert _move(root, rid, "corpus") == 0

    co_located = paths.artifact_path(root, rid, "json")
    assert co_located.is_file()
    assert co_located.read_bytes() == data
    dest_file = bulk / paths.shard(rid) / f"{rid}.json"
    assert not dest_file.exists()


# ---------- no-op / idempotence ---------- #


def test_move_already_at_dest_is_a_noop(tmp_path, capsys):
    root = _corpus(tmp_path)
    data = b'{"case": "already home"}\n'
    rid = _ingest_json(root, data)

    assert _move(root, rid, "corpus") == 0
    out = capsys.readouterr().out
    assert "no-op" in out
    assert paths.artifact_path(root, rid, "json").is_file()


def test_move_idempotent_when_dest_already_holds_identical_bytes(tmp_path, capsys):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"
    data = b'{"case": "dest already has it"}\n'
    rid = _ingest_json(root, data)
    _store_loc(root, "bulk", bulk)

    # Pre-populate the destination with identical bytes via a prior successful move,
    # then put a fresh co-located copy back to exercise the idempotent path directly.
    dest_file = bulk / paths.shard(rid) / f"{rid}.json"
    dest_file.parent.mkdir(parents=True)
    dest_file.write_bytes(data)

    src_file = paths.artifact_path(root, rid, "json")
    assert src_file.is_file()

    assert _move(root, rid, "bulk") == 0
    out = capsys.readouterr().out
    assert "identical bytes" in out
    assert not src_file.exists()
    assert dest_file.read_bytes() == data


# ---------- refusals ---------- #


def test_move_refuses_when_dest_holds_different_bytes(tmp_path, capsys):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"
    data = b'{"case": "mismatch"}\n'
    rid = _ingest_json(root, data)
    _store_loc(root, "bulk", bulk)

    dest_file = bulk / paths.shard(rid) / f"{rid}.json"
    dest_file.parent.mkdir(parents=True)
    dest_file.write_bytes(b'{"case": "corrupted resident"}\n')

    src_file = paths.artifact_path(root, rid, "json")

    with pytest.raises(SystemExit, match="DIFFERENT"):
        _move(root, rid, "bulk")

    # Nothing touched: source intact, corrupted destination left as-is.
    assert src_file.is_file()
    assert src_file.read_bytes() == data
    assert dest_file.read_bytes() == b'{"case": "corrupted resident"}\n'


def test_move_refuses_on_tampered_source(tmp_path):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"
    data = b'{"case": "tampered source"}\n'
    rid = _ingest_json(root, data)
    _store_loc(root, "bulk", bulk)

    src_file = paths.artifact_path(root, rid, "json")
    # Tamper the on-disk bytes so they no longer hash to the record id.
    src_file.write_bytes(b'{"case": "tampered source, corrupted"}\n')

    with pytest.raises(SystemExit, match="failed to verify"):
        _move(root, rid, "bulk")

    # Source left in place (still tampered — move never touches a failed source);
    # nothing landed at the destination.
    assert src_file.is_file()
    dest_file = bulk / paths.shard(rid) / f"{rid}.json"
    assert not dest_file.exists()
    assert not dest_file.with_name(dest_file.name + ".part").exists()


def test_move_refuses_attached_resident_record(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    data = b'{"case": "attached only"}\n'
    f.write_bytes(data)

    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "loc"
kind = "attached"
path = "{tree}"
""",
    )
    attached = config_mod.load_config(root).locations[0]
    locationindex.attest_location(root, attached)

    assert (
        location_cli.run(
            argparse.Namespace(
                action="promote",
                name="loc",
                relpath="a.json",
                all_matching=None,
                source_urls=[],
                corpus_root=str(root),
            )
        )
        == 0
    )
    rid = hashing.hash_file(f, also=())["blake3"]
    assert not LocalArtifactStore(root).is_local(rid, "json")

    with pytest.raises(SystemExit, match="attached-location"):
        _move(root, rid, "corpus")


def test_move_refuses_containment_only_record(tmp_path):
    root = _corpus(tmp_path)
    z = tmp_path / "b.zip"
    payload = b'{"case": "containment only"}\n'
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("note.json", payload)
        # A second member keeps this a genuine multi-member zip-manifest — a ONE-file
        # zip now collapses at ingest (spec §2, v32: the payload-identity principle),
        # which would mint `note.json` directly as a standalone record rather than
        # leaving it the containment-only member this test needs.
        zf.writestr("README.txt", b"one note\n")

    capture = root / "capture"
    capture.mkdir()
    staged = capture / z.name
    shutil.copy(z, staged)
    assert ingest_cli._ingest_one(root, staged) == 0
    cid = hashing.hash_file(z, also=())["blake3"]

    post = records.load(paths.record_path(root, cid))
    draft_cli.derive_record(post, root)
    records.dump(post, paths.record_path(root, cid))

    assert (
        promote_cli.run(
            argparse.Namespace(
                uri=f"corpus://{cid}?path=note.json", json=False, corpus_root=str(root)
            )
        )
        == 0
    )
    pid = blake3.blake3(payload).hexdigest()
    assert not LocalArtifactStore(root).is_local(pid, "json")

    with pytest.raises(SystemExit, match="containment-only"):
        _move(root, pid, "corpus")


def test_move_unknown_dest_is_actionable(tmp_path):
    root = _corpus(tmp_path)
    data = b'{"case": "unknown dest"}\n'
    rid = _ingest_json(root, data)

    with pytest.raises(SystemExit, match="no location named"):
        _move(root, rid, "nowhere")


def test_move_dest_attached_location_is_rejected(tmp_path):
    root = _corpus(tmp_path)
    data = b'{"case": "attached dest"}\n'
    rid = _ingest_json(root, data)

    tree = tmp_path / "tree"
    tree.mkdir()
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "att"
kind = "attached"
path = "{tree}"
""",
    )

    with pytest.raises(SystemExit, match="not a"):
        _move(root, rid, "att")


# ---------- batch move (--all-from) ---------- #


def test_move_all_from_corpus_migrates_every_standalone_copy(tmp_path, capsys):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"
    rid_a = _ingest_json(root, b'{"case": "batch a"}\n')
    rid_b = _ingest_json(root, b'{"case": "batch b"}\n')
    _store_loc(root, "bulk", bulk)

    assert _move_all_from(root, "corpus", "bulk") == 0
    out = capsys.readouterr().out
    assert "moved" in out

    assert not paths.artifact_path(root, rid_a, "json").exists()
    assert not paths.artifact_path(root, rid_b, "json").exists()
    assert (bulk / paths.shard(rid_a) / f"{rid_a}.json").is_file()
    assert (bulk / paths.shard(rid_b) / f"{rid_b}.json").is_file()


def test_move_all_from_skips_containment_only_and_attached_resident(tmp_path):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"

    # A standalone co-located record — the one thing --all-from corpus should move.
    rid_standalone = _ingest_json(root, b'{"case": "standalone"}\n')

    # An attached-resident record: its bytes live in an operator-managed tree, never
    # under the co-located artifacts/ tree, so --all-from corpus can't see it either.
    tree = tmp_path / "tree"
    tree.mkdir()
    attached_file = tree / "a.json"
    attached_file.write_bytes(b'{"case": "attached resident"}\n')
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "loc"
kind = "attached"
path = "{tree}"
""",
    )
    attached = config_mod.load_config(root).locations[0]
    locationindex.attest_location(root, attached)
    assert (
        location_cli.run(
            argparse.Namespace(
                action="promote",
                name="loc",
                relpath="a.json",
                all_matching=None,
                source_urls=[],
                corpus_root=str(root),
            )
        )
        == 0
    )
    rid_attached = hashing.hash_file(attached_file, also=())["blake3"]

    # A containment-only member: no standalone file at all, so it can never appear
    # under the co-located artifacts/ tree that --all-from walks.
    z = tmp_path / "b.zip"
    payload = b'{"case": "containment only"}\n'
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("note.json", payload)
        # A second member keeps this a genuine multi-member zip-manifest — a ONE-file
        # zip now collapses at ingest (spec §2, v32: the payload-identity principle),
        # which would mint `note.json` directly as a standalone record rather than
        # leaving it the containment-only member this test needs.
        zf.writestr("README.txt", b"one note\n")
    capture = root / "capture"
    capture.mkdir(exist_ok=True)
    staged = capture / z.name
    shutil.copy(z, staged)
    assert ingest_cli._ingest_one(root, staged) == 0
    cid = hashing.hash_file(z, also=())["blake3"]
    post = records.load(paths.record_path(root, cid))
    draft_cli.derive_record(post, root)
    records.dump(post, paths.record_path(root, cid))
    assert (
        promote_cli.run(
            argparse.Namespace(
                uri=f"corpus://{cid}?path=note.json", json=False, corpus_root=str(root)
            )
        )
        == 0
    )
    pid = blake3.blake3(payload).hexdigest()

    _store_loc(root, "bulk", bulk)

    assert _move_all_from(root, "corpus", "bulk") == 0

    assert (bulk / paths.shard(rid_standalone) / f"{rid_standalone}.json").is_file()
    # The containment-only member never had a standalone file to migrate.
    assert not (bulk / paths.shard(pid) / f"{pid}.json").exists()
    # The attached-resident record's bytes never entered the co-located tree either —
    # its original is untouched and no copy landed at the destination.
    assert attached_file.is_file()
    assert not (bulk / paths.shard(rid_attached) / f"{rid_attached}.json").exists()


def test_move_all_from_continues_past_per_record_failures(tmp_path, capsys):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"
    rid_ok = _ingest_json(root, b'{"case": "will succeed"}\n')
    rid_bad = _ingest_json(root, b'{"case": "will fail"}\n')
    _store_loc(root, "bulk", bulk)

    # Pre-corrupt the destination for rid_bad so its move refuses.
    bad_dest = bulk / paths.shard(rid_bad) / f"{rid_bad}.json"
    bad_dest.parent.mkdir(parents=True)
    bad_dest.write_bytes(b'{"case": "corrupted resident"}\n')

    assert _move_all_from(root, "corpus", "bulk") == 1
    err = capsys.readouterr().err
    assert rid_bad in err

    # The good record still moved despite the other's failure.
    assert not paths.artifact_path(root, rid_ok, "json").exists()
    assert (bulk / paths.shard(rid_ok) / f"{rid_ok}.json").is_file()
    # The bad one's source is untouched — its corrupted destination is left as-is.
    assert paths.artifact_path(root, rid_bad, "json").is_file()
    assert bad_dest.read_bytes() == b'{"case": "corrupted resident"}\n'


def test_move_all_from_unknown_source_is_actionable(tmp_path):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"
    _store_loc(root, "bulk", bulk)

    with pytest.raises(SystemExit, match="no location named"):
        _move_all_from(root, "nowhere", "bulk")


def test_move_all_from_attached_source_is_rejected(tmp_path):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"
    _store_loc(root, "bulk", bulk)
    tree = tmp_path / "tree"
    tree.mkdir()
    existing = (root / "corpus.toml").read_text("utf-8")
    existing += f"""
[[corpus.location]]
name = "att"
kind = "attached"
path = "{tree}"
"""
    _write_toml(root, existing)

    with pytest.raises(SystemExit, match="not a"):
        _move_all_from(root, "att", "bulk")


def test_move_all_from_empty_source_is_a_clean_noop(tmp_path, capsys):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"
    _store_loc(root, "bulk", bulk)

    assert _move_all_from(root, "corpus", "bulk") == 0
    out = capsys.readouterr().out
    assert "no records found" in out


# ---------- location list ---------- #


def test_location_list_shows_store_locations(tmp_path, capsys):
    root = _corpus(tmp_path)
    default_path = tmp_path / "default"
    claim_path = tmp_path / "claim"
    plain_path = tmp_path / "plain"
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "default"
kind = "store"
path = "{default_path}"
ingest = true

[[corpus.location]]
name = "claim"
kind = "store"
path = "{claim_path}"
ingest = ["application/x-openzim"]

[[corpus.location]]
name = "plain"
kind = "store"
path = "{plain_path}"
""",
    )

    assert location_cli.run(argparse.Namespace(action="list", corpus_root=str(root))) == 0
    out = capsys.readouterr().out

    assert "default" in out and "kind=store" in out and "ingest: default" in out
    assert "claim" in out and "ingest: application/x-openzim" in out
    plain_line = next(line for line in out.splitlines() if line.startswith("plain"))
    assert "ingest:" not in plain_line
