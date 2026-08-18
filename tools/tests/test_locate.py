"""`corpus locate <blake3>` — the residency query (spec §12.1.1, §12.9.2, v24
"Residency query" amendment)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from corpus import config as config_mod
from corpus import hashing, locationindex, paths, schemas
from corpus._cli import dispatch
from corpus._cli import location as location_cli


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _attach(root: Path, tree: Path, *, name: str = "loc") -> config_mod.LocationConfig:
    existing = (root / "corpus.toml").read_text("utf-8") if (root / "corpus.toml").is_file() else ""
    existing += f"""
[[corpus.location]]
name = "{name}"
kind = "attached"
path = "{tree}"
"""
    (root / "corpus.toml").write_text(existing, "utf-8")
    loc = next(loc for loc in config_mod.load_config(root).locations if loc.name == name)
    locationindex.attest_location(root, loc)
    return loc


def _add_store(root: Path, name: str, path: Path) -> None:
    existing = (root / "corpus.toml").read_text("utf-8") if (root / "corpus.toml").is_file() else ""
    existing += f"""
[[corpus.location]]
name = "{name}"
kind = "store"
path = "{path}"
"""
    (root / "corpus.toml").write_text(existing, "utf-8")


def _promote(root: Path, name: str, relpath: str) -> int:
    return location_cli.run(
        argparse.Namespace(
            action="promote",
            name=name,
            relpath=relpath,
            all_matching=None,
            source_urls=[],
            corpus_root=str(root),
        )
    )


def _locate(root: Path, hash_: str, *, as_json: bool = False) -> int:
    argv = ["locate", hash_, "--corpus-root", str(root)]
    if as_json:
        argv.append("--json")
    return dispatch(argv)


# ---------- input validation ---------- #


def test_locate_rejects_short_prefix(tmp_path):
    root = _corpus(tmp_path)
    with pytest.raises(SystemExit, match="not a full 64-hex"):
        _locate(root, "abcd1234")


def test_locate_rejects_non_hex(tmp_path):
    root = _corpus(tmp_path)
    with pytest.raises(SystemExit, match="not a full 64-hex"):
        _locate(root, "z" * 64)


# ---------- nothing found ---------- #


def test_locate_nothing_found_exits_1(tmp_path, capsys):
    root = _corpus(tmp_path)
    rc = _locate(root, "0" * 64)
    assert rc == 1
    out = capsys.readouterr().out
    assert "nothing found" in out


# ---------- record + co-located artifact ---------- #


def test_locate_finds_record_and_co_located_artifact(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    f.write_bytes(b'{"case": "locate me"}\n')
    _attach(root, tree)
    assert _promote(root, "loc", "a.json") == 0
    rid = hashing.hash_file(f, also=())["blake3"]

    # `promote` with store_bytes=False never lands a co-located artifact — write one by
    # hand to exercise that leg of the search.
    apath = paths.artifact_path(root, rid, "json")
    apath.parent.mkdir(parents=True, exist_ok=True)
    apath.write_bytes(f.read_bytes())

    rc = _locate(root, rid)
    assert rc == 0
    out = capsys.readouterr().out
    assert f"records/{paths.shard(rid)}/{rid}.md" in out
    assert "artifacts" in out


def test_locate_finds_store_location_artifact(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    f.write_bytes(b'{"case": "in a store location"}\n')
    _attach(root, tree)
    assert _promote(root, "loc", "a.json") == 0
    rid = hashing.hash_file(f, also=())["blake3"]

    bulk = tmp_path / "bulk"
    _add_store(root, "bulk", bulk)
    assert location_cli.run(
        argparse.Namespace(
            action="adopt", name="loc", dest="bulk", relpath="a.json", reclaim=False,
            corpus_root=str(root),
        )
    ) == 0
    capsys.readouterr()

    rc = _locate(root, rid, as_json=True)
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["artifact"]["location"] == "bulk"


# ---------- attached rows: current vs stale ---------- #


def test_locate_reports_current_attached_row(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.bin"
    f.write_bytes(b"attached bytes")
    _attach(root, tree)
    rid = hashing.hash_file(f, also=())["blake3"]

    rc = _locate(root, rid, as_json=True)
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["record"] is None
    assert data["artifact"] is None
    assert len(data["attached"]) == 1
    row = data["attached"][0]
    assert row == {
        "location": "loc",
        "relpath": "a.bin",
        "source": "computed",
        "status": "current",
    }


def test_locate_reports_stale_attached_row(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.bin"
    f.write_bytes(b"attached bytes")
    _attach(root, tree)
    rid = hashing.hash_file(f, also=())["blake3"]

    # Mutate without re-attesting: the index row is now stale for the ORIGINAL hash.
    f.write_bytes(b"attached bytes, mutated")

    rc = _locate(root, rid, as_json=True)
    assert rc == 0  # the row is still found, just reported stale
    data = json.loads(capsys.readouterr().out)
    assert len(data["attached"]) == 1
    assert data["attached"][0]["status"] == "stale"


# ---------- --json shape ---------- #


def test_locate_json_shape_and_searched_field(tmp_path, capsys):
    root = _corpus(tmp_path)
    rc = _locate(root, "0" * 64, as_json=True)
    assert rc == 1
    data = json.loads(capsys.readouterr().out)
    assert data["hash"] == "0" * 64
    assert data["record"] is None
    assert data["artifact"] is None
    assert data["attached"] == []
    assert data["searched"] == [
        "record",
        "co-located + store artifacts",
        "attached-location index",
    ]
