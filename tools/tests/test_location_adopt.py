"""`corpus location adopt` — non-destructive custody transfer from an attached
location to a store (spec/corpus.md §12.1.1, "Adoption" paragraph, v23).

Test files use `.json` payloads for the same reason `test_location_promote.py` does:
`application/json` ships a default mime schema, so a real record can be minted for it.
"""

from __future__ import annotations

import argparse
import stat
from pathlib import Path

from corpus import config as config_mod
from corpus import containment, hashing, locationindex, paths, schemas
from corpus._cli import location as location_cli


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _attach(root: Path, tree: Path, *, name: str = "loc") -> config_mod.LocationConfig:
    (root / "corpus.toml").write_text(
        f"""
[[corpus.location]]
name = "{name}"
kind = "attached"
path = "{tree}"
""",
        "utf-8",
    )
    loc = config_mod.load_config(root).locations[0]
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


def _adopt(
    root: Path, name: str, dest: str, relpath: str | None = None, *, reclaim: bool = False
) -> int:
    return location_cli.run(
        argparse.Namespace(
            action="adopt",
            name=name,
            dest=dest,
            relpath=relpath,
            reclaim=reclaim,
            corpus_root=str(root),
        )
    )


# ---------- happy path ---------- #


def test_adopt_single_file_copies_without_touching_original(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    data = b'{"case": "adopt one"}\n'
    f.write_bytes(data)
    _attach(root, tree)
    assert _promote(root, "loc", "a.json") == 0
    rid = hashing.hash_file(f, also=())["blake3"]

    bulk = tmp_path / "bulk"
    _add_store(root, "bulk", bulk)

    assert _adopt(root, "loc", "bulk") == 0
    out = capsys.readouterr().out
    assert "adopted" in out

    dest_file = bulk / paths.shard(rid) / f"{rid}.json"
    assert dest_file.is_file()
    assert dest_file.read_bytes() == data

    # The attached original stays exactly where it is.
    assert f.is_file()
    assert f.read_bytes() == data

    # ...and its location-index row persists (never cleared by adoption).
    with locationindex.open_index(root) as conn:
        row = conn.execute(
            "SELECT hash FROM locations WHERE location = ? AND relpath = ?", ("loc", "a.json")
        ).fetchone()
    assert row is not None
    assert row[0] == rid

    # Resolution now serves the STORE copy — store locations precede the attached
    # index in route order (spec §12.1.1).
    resolved = containment.ensure_local_bytes(root, rid, "json")
    assert resolved == dest_file


def test_adopt_all_current_rows_when_relpath_omitted(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.json").write_bytes(b'{"n": "a"}\n')
    (tree / "b.json").write_bytes(b'{"n": "b"}\n')
    _attach(root, tree)
    assert _promote(root, "loc", "a.json") == 0
    assert _promote(root, "loc", "b.json") == 0

    bulk = tmp_path / "bulk"
    _add_store(root, "bulk", bulk)

    assert _adopt(root, "loc", "bulk") == 0

    rid_a = hashing.hash_file(tree / "a.json", also=())["blake3"]
    rid_b = hashing.hash_file(tree / "b.json", also=())["blake3"]
    assert (bulk / paths.shard(rid_a) / f"{rid_a}.json").is_file()
    assert (bulk / paths.shard(rid_b) / f"{rid_b}.json").is_file()
    assert (tree / "a.json").is_file()
    assert (tree / "b.json").is_file()


# ---------- idempotence ---------- #


def test_re_adopt_is_idempotent(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    data = b'{"case": "idempotent"}\n'
    f.write_bytes(data)
    _attach(root, tree)
    assert _promote(root, "loc", "a.json") == 0
    rid = hashing.hash_file(f, also=())["blake3"]

    bulk = tmp_path / "bulk"
    _add_store(root, "bulk", bulk)

    assert _adopt(root, "loc", "bulk") == 0
    capsys.readouterr()

    assert _adopt(root, "loc", "bulk") == 0
    out = capsys.readouterr().out
    assert "already present" in out

    dest_file = bulk / paths.shard(rid) / f"{rid}.json"
    assert dest_file.read_bytes() == data
    assert f.is_file()


# ---------- refusals ---------- #


def test_adopt_refuses_file_with_no_promoted_record(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    f.write_bytes(b'{"case": "never promoted"}\n')
    _attach(root, tree)
    # Attested, but never promoted — no record exists for its hash.

    bulk = tmp_path / "bulk"
    _add_store(root, "bulk", bulk)

    assert _adopt(root, "loc", "bulk", "a.json") == 1
    err = capsys.readouterr().err
    assert "no promoted record" in err
    assert "promote" in err

    # Nothing landed at the destination; original untouched.
    assert not bulk.exists() or not list(bulk.rglob("*.json"))
    assert f.is_file()


def test_adopt_refuses_stale_index_row(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    f.write_bytes(b'{"case": "will go stale"}\n')
    _attach(root, tree)
    assert _promote(root, "loc", "a.json") == 0

    # Mutate after attest without re-attesting: the index row's pins now mismatch.
    f.write_bytes(b'{"case": "mutated after attest, not re-attested"}\n')

    bulk = tmp_path / "bulk"
    _add_store(root, "bulk", bulk)

    assert _adopt(root, "loc", "bulk", "a.json") == 1
    err = capsys.readouterr().err
    assert "stale" in err
    assert "corpus location attest" in err


# ---------- --reclaim ---------- #


def test_reclaim_removes_original_after_verified_copy(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    data = b'{"case": "reclaim me"}\n'
    f.write_bytes(data)
    _attach(root, tree)
    assert _promote(root, "loc", "a.json") == 0
    rid = hashing.hash_file(f, also=())["blake3"]

    bulk = tmp_path / "bulk"
    _add_store(root, "bulk", bulk)

    assert _adopt(root, "loc", "bulk", "a.json", reclaim=True) == 0

    dest_file = bulk / paths.shard(rid) / f"{rid}.json"
    assert dest_file.is_file()
    assert dest_file.read_bytes() == data
    assert not f.exists()

    # Record still resolves (through the store copy now).
    resolved = containment.ensure_local_bytes(root, rid, "json")
    assert resolved == dest_file


def test_reclaim_on_read_only_tree_reports_but_adoption_still_succeeds(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    data = b'{"case": "read-only reclaim"}\n'
    f.write_bytes(data)
    _attach(root, tree)
    assert _promote(root, "loc", "a.json") == 0
    rid = hashing.hash_file(f, also=())["blake3"]

    bulk = tmp_path / "bulk"
    _add_store(root, "bulk", bulk)

    # Make the attached tree's directory read-only so unlink() (which needs to
    # rewrite the directory entry, not the file itself) fails.
    tree.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        assert _adopt(root, "loc", "bulk", "a.json", reclaim=True) == 0
        captured = capsys.readouterr()
        assert "reclaim failed" in captured.out
        assert "warning" in captured.err

        dest_file = bulk / paths.shard(rid) / f"{rid}.json"
        assert dest_file.is_file()
        assert dest_file.read_bytes() == data
        # The original is still there — the read-only tree refused the removal.
        assert f.is_file()
    finally:
        tree.chmod(stat.S_IRWXU)


# ---------- destination refusal ---------- #


def test_adopt_refuses_when_dest_holds_different_bytes(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    data = b'{"case": "dest mismatch"}\n'
    f.write_bytes(data)
    _attach(root, tree)
    assert _promote(root, "loc", "a.json") == 0
    rid = hashing.hash_file(f, also=())["blake3"]

    bulk = tmp_path / "bulk"
    dest_file = bulk / paths.shard(rid) / f"{rid}.json"
    dest_file.parent.mkdir(parents=True)
    dest_file.write_bytes(b'{"case": "corrupted resident"}\n')
    _add_store(root, "bulk", bulk)

    assert _adopt(root, "loc", "bulk", "a.json") == 1
    err = capsys.readouterr().err
    assert "DIFFERENT" in err

    # Nothing touched: original intact, corrupted destination left as-is.
    assert f.is_file()
    assert f.read_bytes() == data
    assert dest_file.read_bytes() == b'{"case": "corrupted resident"}\n'
