"""Presented manifests — the manifest-contract-v2 reader, `source` provenance, staleness
tolerance, and CLI attest routing (spec §12.1.1, §12.9.2, v24 amendment).

`_make_manifest` below builds a fake residence-scanner `manifest.sqlite` by hand, via
raw `sqlite3`, matching the pinned contract exactly (a separate agent builds the real
writer) — these tests are entirely independent of any real scanner.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pytest

from corpus import config as config_mod
from corpus import locationindex
from corpus._cli import location as location_cli


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _attach_presenting(root: Path, tree: Path, *, name: str = "loc") -> config_mod.LocationConfig:
    (root / "corpus.toml").write_text(
        f"""
[[corpus.location]]
name = "{name}"
kind = "attached"
path = "{tree}"
manifest = true
""",
        "utf-8",
    )
    return next(loc for loc in config_mod.load_config(root).locations if loc.name == name)


_MANIFEST_SCHEMA_V2 = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE identities (
  dev INTEGER NOT NULL, ino INTEGER NOT NULL,
  size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
  blake3 TEXT NOT NULL, generation INTEGER NOT NULL,
  PRIMARY KEY (dev, ino)
) WITHOUT ROWID;
CREATE TABLE paths (
  path TEXT PRIMARY KEY, dev INTEGER NOT NULL, ino INTEGER NOT NULL,
  generation INTEGER NOT NULL
) WITHOUT ROWID;
CREATE TABLE generations (
  generation INTEGER PRIMARY KEY, mode TEXT NOT NULL, scanner TEXT NOT NULL,
  started_at TEXT NOT NULL, finished_at TEXT, summary_json TEXT
);
CREATE TABLE events (
  id INTEGER PRIMARY KEY, generation INTEGER NOT NULL, type TEXT NOT NULL,
  path TEXT NOT NULL, detail_json TEXT NOT NULL
);
"""

# v3 (spec §12.1.1 (25), "Catalog-metadata amendment"): identities grows the light-
# catalog columns — ctime_ns/btime_ns/mode are stat facts this reader never imports
# (they "stay queryable in the cached manifest"); mime_claim is the one column
# locationindex.attest_from_manifest actually copies forward.
_MANIFEST_SCHEMA_V3 = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE identities (
  dev INTEGER NOT NULL, ino INTEGER NOT NULL,
  size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
  ctime_ns INTEGER, btime_ns INTEGER, mode INTEGER, mime_claim TEXT,
  blake3 TEXT NOT NULL, generation INTEGER NOT NULL,
  PRIMARY KEY (dev, ino)
) WITHOUT ROWID;
CREATE TABLE paths (
  path TEXT PRIMARY KEY, dev INTEGER NOT NULL, ino INTEGER NOT NULL,
  generation INTEGER NOT NULL
) WITHOUT ROWID;
CREATE TABLE generations (
  generation INTEGER PRIMARY KEY, mode TEXT NOT NULL, scanner TEXT NOT NULL,
  started_at TEXT NOT NULL, finished_at TEXT, summary_json TEXT
);
CREATE TABLE events (
  id INTEGER PRIMARY KEY, generation INTEGER NOT NULL, type TEXT NOT NULL,
  path TEXT NOT NULL, detail_json TEXT NOT NULL
);
"""


def _make_manifest(
    manifest_path: Path,
    *,
    entries: list[dict],
    generation: int = 1,
    finished: bool = True,
    also_open_generation: bool = False,
    user_version: int = 2,
) -> None:
    """Build a fake contract-v2-or-v3 manifest.sqlite (spec §12.1.1 (24)/(25)) at
    `manifest_path` (replacing any prior one — each call models the scanner
    republishing a whole new generation-checkpointed db). `entries`: dicts with
    `path`, `size`, `mtime_ns`, `blake3`, an optional `ino` (entries sharing an `ino`
    become hardlinks — one identity, one hash, two path rows), and — `user_version=3`
    only — an optional `mime_claim`. `finished=False` leaves the generation open (no
    `finished_at`) — the "scanner cold pass still running" refusal case."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.unlink(missing_ok=True)
    schema = _MANIFEST_SCHEMA_V3 if user_version >= 3 else _MANIFEST_SCHEMA_V2
    conn = sqlite3.connect(manifest_path)
    try:
        conn.executescript(schema)
        conn.execute(f"PRAGMA user_version = {int(user_version)}")
        conn.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            [
                ("schema", str(user_version)),
                ("scanner", "test-scanner@1"),
                ("root", "/fake/scanned/root"),
                ("created_at", "2026-01-01T00:00:00Z"),
            ],
        )
        finished_at = "2026-01-01T00:05:00Z" if finished else None
        conn.execute(
            "INSERT INTO generations (generation, mode, scanner, started_at, finished_at) "
            "VALUES (?, 'full', 'test-scanner@1', '2026-01-01T00:00:00Z', ?)",
            (generation, finished_at),
        )
        if also_open_generation:
            conn.execute(
                "INSERT INTO generations "
                "(generation, mode, scanner, started_at, finished_at) "
                "VALUES (?, 'incremental', 'test-scanner@1', '2026-01-02T00:00:00Z', NULL)",
                (generation + 1,),
            )

        seen_idents: set[int] = set()
        next_ino = 1
        for entry in entries:
            ino = entry.get("ino")
            if ino is None:
                ino = next_ino
                next_ino += 1
            if ino not in seen_idents:
                seen_idents.add(ino)
                if user_version >= 3:
                    conn.execute(
                        "INSERT INTO identities "
                        "(dev, ino, size, mtime_ns, ctime_ns, btime_ns, mode, "
                        "mime_claim, blake3, generation) "
                        "VALUES (1, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?)",
                        (
                            ino,
                            entry["size"],
                            entry["mtime_ns"],
                            entry.get("mime_claim"),
                            entry["blake3"],
                            generation,
                        ),
                    )
                else:
                    conn.execute(
                        "INSERT INTO identities "
                        "(dev, ino, size, mtime_ns, blake3, generation) "
                        "VALUES (1, ?, ?, ?, ?, ?)",
                        (ino, entry["size"], entry["mtime_ns"], entry["blake3"], generation),
                    )
            conn.execute(
                "INSERT INTO paths (path, dev, ino, generation) VALUES (?, 1, ?, ?)",
                (entry["path"], ino, generation),
            )
        conn.commit()
    finally:
        conn.close()


HASH_A = "a" * 64
HASH_B = "b" * 64


# ---------- import ---------- #


def test_import_lands_presented_rows_with_correct_pins(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    loc = _attach_presenting(root, tree)
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[{"path": "a.bin", "size": 5, "mtime_ns": 12345, "blake3": HASH_A}],
        generation=1,
    )

    outcome = locationindex.attest_from_manifest(root, loc)
    assert outcome == {"files": 1, "generation": 1, "skipped": False}

    with locationindex.open_index(root) as conn:
        row = conn.execute(
            "SELECT hash, size, mtime, source FROM locations WHERE location = ? "
            "AND relpath = ?",
            ("loc", "a.bin"),
        ).fetchone()
    assert row == (HASH_A, 5, 12345, "presented")


def test_hardlinks_produce_two_rows_one_hash(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    loc = _attach_presenting(root, tree)
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[
            {"path": "a.bin", "size": 5, "mtime_ns": 111, "blake3": HASH_A, "ino": 10},
            {"path": "a-link.bin", "size": 5, "mtime_ns": 111, "blake3": HASH_A, "ino": 10},
            {"path": "b.bin", "size": 7, "mtime_ns": 222, "blake3": HASH_B},
        ],
        generation=1,
    )

    outcome = locationindex.attest_from_manifest(root, loc)
    assert outcome == {"files": 3, "generation": 1, "skipped": False}

    with locationindex.open_index(root) as conn:
        rows = conn.execute(
            "SELECT relpath, hash FROM locations WHERE location = ? ORDER BY relpath",
            ("loc",),
        ).fetchall()
    assert rows == [("a-link.bin", HASH_A), ("a.bin", HASH_A), ("b.bin", HASH_B)]


def test_reattest_same_generation_noops(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    loc = _attach_presenting(root, tree)
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[{"path": "a.bin", "size": 5, "mtime_ns": 111, "blake3": HASH_A}],
        generation=1,
    )
    locationindex.attest_from_manifest(root, loc)

    outcome = locationindex.attest_from_manifest(root, loc)
    assert outcome == {"skipped": True, "generation": 1}


def test_force_reimports_same_generation(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    loc = _attach_presenting(root, tree)
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[{"path": "a.bin", "size": 5, "mtime_ns": 111, "blake3": HASH_A}],
        generation=1,
    )
    locationindex.attest_from_manifest(root, loc)

    outcome = locationindex.attest_from_manifest(root, loc, force=True)
    assert outcome == {"files": 1, "generation": 1, "skipped": False}


def test_new_generation_replaces_rows_including_deletions(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    loc = _attach_presenting(root, tree)
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[
            {"path": "a.bin", "size": 5, "mtime_ns": 111, "blake3": HASH_A},
            {"path": "b.bin", "size": 7, "mtime_ns": 222, "blake3": HASH_B},
        ],
        generation=1,
    )
    locationindex.attest_from_manifest(root, loc)

    # Generation 2: b.bin is gone, a.bin's content (and hash) changed.
    new_hash_a = "c" * 64
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[{"path": "a.bin", "size": 9, "mtime_ns": 333, "blake3": new_hash_a}],
        generation=2,
    )
    outcome = locationindex.attest_from_manifest(root, loc)
    assert outcome == {"files": 1, "generation": 2, "skipped": False}

    with locationindex.open_index(root) as conn:
        rows = conn.execute(
            "SELECT relpath, hash, size, mtime FROM locations WHERE location = ?",
            ("loc",),
        ).fetchall()
    assert rows == [("a.bin", new_hash_a, 9, 333)]

    with locationindex.open_index(root) as conn:
        gen = conn.execute(
            "SELECT generation FROM manifest_imports WHERE location = ?", ("loc",)
        ).fetchone()
    assert gen == (2,)


def test_wrong_user_version_refused(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    loc = _attach_presenting(root, tree)
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[{"path": "a.bin", "size": 5, "mtime_ns": 111, "blake3": HASH_A}],
        generation=1,
        user_version=1,
    )
    with pytest.raises(ValueError, match="schema version"):
        locationindex.attest_from_manifest(root, loc)


def test_missing_manifest_refused(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    loc = _attach_presenting(root, tree)
    with pytest.raises(ValueError, match="has not published a manifest"):
        locationindex.attest_from_manifest(root, loc)


def test_open_generation_only_manifest_refused(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    loc = _attach_presenting(root, tree)
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[{"path": "a.bin", "size": 5, "mtime_ns": 111, "blake3": HASH_A}],
        generation=1,
        finished=False,
    )
    with pytest.raises(ValueError, match="completed generation"):
        locationindex.attest_from_manifest(root, loc)


def test_open_generation_ignored_when_a_completed_one_exists(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    loc = _attach_presenting(root, tree)
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[{"path": "a.bin", "size": 5, "mtime_ns": 111, "blake3": HASH_A}],
        generation=1,
        finished=True,
        also_open_generation=True,
    )
    outcome = locationindex.attest_from_manifest(root, loc)
    # The current generation is the max COMPLETED one (1), not the open one (2).
    assert outcome == {"files": 1, "generation": 1, "skipped": False}


# ---------- walking attest still works, overwrites presented as computed ---------- #


def test_walking_attest_overwrites_presented_rows_as_computed(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.bin"
    data = b"hello world"
    f.write_bytes(data)
    loc = _attach_presenting(root, tree)

    from corpus import hashing

    real_hash = hashing.hash_file(f, also=())["blake3"]
    st = f.stat()
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[
            {
                "path": "a.bin",
                "size": st.st_size,
                "mtime_ns": st.st_mtime_ns,
                "blake3": real_hash,
            }
        ],
        generation=1,
    )
    locationindex.attest_from_manifest(root, loc)
    with locationindex.open_index(root) as conn:
        source = conn.execute(
            "SELECT source FROM locations WHERE location = ? AND relpath = ?",
            ("loc", "a.bin"),
        ).fetchone()
    assert source == ("presented",)

    # An ordinary walking attest (--walk at the CLI) overwrites it as computed, even
    # though the pins already match exactly.
    counts = locationindex.attest_location(root, loc)
    assert counts["files"] == 1
    assert counts["hashed"] == 1
    assert counts["unchanged"] == 0

    with locationindex.open_index(root) as conn:
        row = conn.execute(
            "SELECT hash, source FROM locations WHERE location = ? AND relpath = ?",
            ("loc", "a.bin"),
        ).fetchone()
    assert row == (real_hash, "computed")


# ---------- pins_match ---------- #


def test_pins_match_computed_requires_exact_mtime():
    assert locationindex.pins_match(10, 1_000_000, 10, 1_000_000, "computed") is True
    assert locationindex.pins_match(10, 1_000_000, 10, 1_000_050, "computed") is False


def test_pins_match_presented_tolerates_sub_100ns_drift():
    assert locationindex.pins_match(10, 1_000_000, 10, 1_000_050, "presented") is True
    assert locationindex.pins_match(10, 1_000_000, 10, 1_000_099, "presented") is True
    assert locationindex.pins_match(10, 1_000_000, 10, 1_000_100, "presented") is False


def test_pins_match_size_always_exact():
    assert locationindex.pins_match(10, 1_000_000, 11, 1_000_000, "computed") is False
    assert locationindex.pins_match(10, 1_000_000, 11, 1_000_000, "presented") is False


# ---------- CLI attest routing ---------- #


def _cli_attest(root: Path, name: str, *, walk: bool = False, force: bool = False) -> int:
    return location_cli.run(
        argparse.Namespace(
            action="attest", name=name, walk=walk, force=force, corpus_root=str(root)
        )
    )


def test_cli_attest_routes_to_manifest_by_default(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    _attach_presenting(root, tree)
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[{"path": "a.bin", "size": 5, "mtime_ns": 111, "blake3": HASH_A}],
        generation=1,
    )

    assert _cli_attest(root, "loc") == 0
    out = capsys.readouterr().out
    assert "imported 1 file(s)" in out
    assert "generation 1" in out

    with locationindex.open_index(root) as conn:
        source = conn.execute(
            "SELECT source FROM locations WHERE location = ? AND relpath = ?",
            ("loc", "a.bin"),
        ).fetchone()
    assert source == ("presented",)


def test_cli_attest_manifest_reattest_reports_noop(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    _attach_presenting(root, tree)
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[{"path": "a.bin", "size": 5, "mtime_ns": 111, "blake3": HASH_A}],
        generation=1,
    )
    assert _cli_attest(root, "loc") == 0
    capsys.readouterr()

    assert _cli_attest(root, "loc") == 0
    out = capsys.readouterr().out
    assert "already imported" in out
    assert "nothing to do" in out


def test_cli_attest_force_reimports(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    _attach_presenting(root, tree)
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[{"path": "a.bin", "size": 5, "mtime_ns": 111, "blake3": HASH_A}],
        generation=1,
    )
    assert _cli_attest(root, "loc") == 0
    capsys.readouterr()

    assert _cli_attest(root, "loc", force=True) == 0
    out = capsys.readouterr().out
    assert "imported 1 file(s)" in out


def test_cli_attest_walk_forces_walking_attest_on_presenting_location(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.bin"
    f.write_bytes(b"walked, not presented")
    _attach_presenting(root, tree)
    # No manifest published at all — --walk must not even try to read one.
    assert _cli_attest(root, "loc", walk=True) == 0
    out = capsys.readouterr().out
    assert "1 hashed" in out

    with locationindex.open_index(root) as conn:
        source = conn.execute(
            "SELECT source FROM locations WHERE location = ? AND relpath = ?",
            ("loc", "a.bin"),
        ).fetchone()
    assert source == ("computed",)


def test_cli_list_shows_manifest_marker(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    plain_tree = tmp_path / "plain"
    plain_tree.mkdir()
    _attach_presenting(root, tree)
    existing = (root / "corpus.toml").read_text("utf-8")
    existing += f"""
[[corpus.location]]
name = "plain"
kind = "attached"
path = "{plain_tree}"
"""
    (root / "corpus.toml").write_text(existing, "utf-8")

    rc = location_cli.run(argparse.Namespace(action="list", corpus_root=str(root)))
    assert rc == 0
    out = capsys.readouterr().out
    lines = {line.split(" ")[0]: line for line in out.splitlines()}
    assert lines["loc"].endswith("  manifest")
    assert not lines["plain"].endswith("  manifest")


def test_cli_list_shows_cost_when_declared(tmp_path, capsys):
    """`corpus location list` appends `cost=<N>` to a row when declared — attached and
    store alike (spec §12.1.1, v25 "Route preference")."""
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    bulk = tmp_path / "bulk"
    (root / "corpus.toml").write_text(
        f"""
[[corpus.location]]
name = "loc"
kind = "attached"
path = "{tree}"
cost = 30

[[corpus.location]]
name = "bulk"
kind = "store"
path = "{bulk}"
""",
        "utf-8",
    )

    rc = location_cli.run(argparse.Namespace(action="list", corpus_root=str(root)))
    assert rc == 0
    out = capsys.readouterr().out
    lines = {line.split(" ")[0]: line for line in out.splitlines()}
    assert "cost=30" in lines["loc"]
    assert "cost=" not in lines["bulk"]  # undeclared on bulk — nothing shown


# ---------- schema migration ---------- #


def test_old_schema_db_upgrades_on_connect_and_keeps_rows_computed(tmp_path):
    root = _corpus(tmp_path)
    db_path = locationindex.db_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Create a pre-v24 db by hand: the old schema, no `source` column.
    raw = sqlite3.connect(db_path)
    try:
        raw.executescript(
            """
            CREATE TABLE locations (
                hash     TEXT NOT NULL,
                location TEXT NOT NULL,
                relpath  TEXT NOT NULL,
                size     INTEGER NOT NULL,
                mtime    INTEGER NOT NULL,
                PRIMARY KEY (location, relpath)
            );
            CREATE INDEX idx_locations_hash ON locations (hash);
            """
        )
        raw.execute(
            "INSERT INTO locations (hash, location, relpath, size, mtime) "
            "VALUES (?, ?, ?, ?, ?)",
            (HASH_A, "loc", "a.bin", 5, 111),
        )
        raw.commit()
    finally:
        raw.close()

    with locationindex.open_index(root) as conn:
        row = conn.execute(
            "SELECT hash, size, mtime, source FROM locations WHERE location = ? "
            "AND relpath = ?",
            ("loc", "a.bin"),
        ).fetchone()
    assert row == (HASH_A, 5, 111, "computed")


def test_old_locations_db_gains_mime_claim_column_nullable(tmp_path):
    """A pre-v25 `locations.db` (no `mime_claim` column at all — v24's own `source`
    migration already applied) upgrades in place on `connect`; every pre-existing row
    lands with `mime_claim = NULL` (spec §12.1.1 (25))."""
    root = _corpus(tmp_path)
    db_path = locationindex.db_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    raw = sqlite3.connect(db_path)
    try:
        raw.executescript(
            """
            CREATE TABLE locations (
                hash     TEXT NOT NULL,
                location TEXT NOT NULL,
                relpath  TEXT NOT NULL,
                size     INTEGER NOT NULL,
                mtime    INTEGER NOT NULL,
                source   TEXT NOT NULL DEFAULT 'computed',
                PRIMARY KEY (location, relpath)
            );
            CREATE INDEX idx_locations_hash ON locations (hash);
            """
        )
        raw.execute(
            "INSERT INTO locations (hash, location, relpath, size, mtime, source) "
            "VALUES (?, ?, ?, ?, ?, 'computed')",
            (HASH_A, "loc", "a.bin", 5, 111),
        )
        raw.commit()
    finally:
        raw.close()

    with locationindex.open_index(root) as conn:
        row = conn.execute(
            "SELECT hash, size, mtime, source, mime_claim FROM locations "
            "WHERE location = ? AND relpath = ?",
            ("loc", "a.bin"),
        ).fetchone()
    assert row == (HASH_A, 5, 111, "computed", None)


# ---------- mime_claim import (spec §12.1.1 (25), v25 "Catalog-metadata amendment") ---------- #


def test_v3_manifest_import_lands_mime_claim(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    loc = _attach_presenting(root, tree)
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[
            {
                "path": "a.bin",
                "size": 5,
                "mtime_ns": 111,
                "blake3": HASH_A,
                "mime_claim": "application/x-openzim",
            },
            {"path": "b.bin", "size": 7, "mtime_ns": 222, "blake3": HASH_B},
        ],
        generation=1,
        user_version=3,
    )

    outcome = locationindex.attest_from_manifest(root, loc)
    assert outcome == {"files": 2, "generation": 1, "skipped": False}

    with locationindex.open_index(root) as conn:
        rows = conn.execute(
            "SELECT relpath, mime_claim FROM locations WHERE location = ? "
            "ORDER BY relpath",
            ("loc",),
        ).fetchall()
    assert rows == [("a.bin", "application/x-openzim"), ("b.bin", None)]


def test_v2_manifest_import_lands_null_mime_claim(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    loc = _attach_presenting(root, tree)
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[{"path": "a.bin", "size": 5, "mtime_ns": 111, "blake3": HASH_A}],
        generation=1,
        user_version=2,
    )

    outcome = locationindex.attest_from_manifest(root, loc)
    assert outcome == {"files": 1, "generation": 1, "skipped": False}

    with locationindex.open_index(root) as conn:
        row = conn.execute(
            "SELECT mime_claim FROM locations WHERE location = ? AND relpath = ?",
            ("loc", "a.bin"),
        ).fetchone()
    assert row == (None,)


def test_v3_schema_version_accepted_alongside_v2(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    loc = _attach_presenting(root, tree)
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[{"path": "a.bin", "size": 5, "mtime_ns": 111, "blake3": HASH_A}],
        generation=1,
        user_version=3,
    )
    # No ValueError — v3 is accepted exactly like v2.
    outcome = locationindex.attest_from_manifest(root, loc)
    assert outcome["skipped"] is False


def test_unknown_schema_version_error_names_both_accepted(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    loc = _attach_presenting(root, tree)
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[{"path": "a.bin", "size": 5, "mtime_ns": 111, "blake3": HASH_A}],
        generation=1,
        user_version=4,
    )
    with pytest.raises(ValueError, match="2 or 3"):
        locationindex.attest_from_manifest(root, loc)


def test_walking_attest_clears_mime_claim_on_a_previously_presented_row(tmp_path):
    """A walking attest always overwrites a presented row as computed (existing
    behavior); it must also clear any `mime_claim` that row carried — a computed row
    never sniffs bytes, so it never carries a claim (spec §12.1.1 (25))."""
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.bin"
    data = b"walked after presented"
    f.write_bytes(data)
    loc = _attach_presenting(root, tree)

    from corpus import hashing

    real_hash = hashing.hash_file(f, also=())["blake3"]
    st = f.stat()
    _make_manifest(
        tree / ".athenaeum" / "manifest.sqlite",
        entries=[
            {
                "path": "a.bin",
                "size": st.st_size,
                "mtime_ns": st.st_mtime_ns,
                "blake3": real_hash,
                "mime_claim": "application/octet-stream",
            }
        ],
        generation=1,
        user_version=3,
    )
    locationindex.attest_from_manifest(root, loc)
    with locationindex.open_index(root) as conn:
        claim = conn.execute(
            "SELECT mime_claim FROM locations WHERE location = ? AND relpath = ?",
            ("loc", "a.bin"),
        ).fetchone()
    assert claim == ("application/octet-stream",)

    locationindex.attest_location(root, loc)
    with locationindex.open_index(root) as conn:
        row = conn.execute(
            "SELECT source, mime_claim FROM locations WHERE location = ? AND relpath = ?",
            ("loc", "a.bin"),
        ).fetchone()
    assert row == ("computed", None)
