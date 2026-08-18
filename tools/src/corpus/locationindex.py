"""The attached-location index — the derived map for the third route class (spec
§12.1.1, §12.9.2).

SQLite at `<corpus_root>/cache/locations.db` — in the `hashindex.py` mold (§12.9.1):
untracked, never authoritative, gc-excluded by name (§12.8) because recomputation
needs *bytes*, which for a multi-GB attached tree is hours, not milliseconds. A missing
row means "unattested", never a failure.

Row shape `(hash, location, relpath, size, mtime)` (§12.9.2): `hash` is the bare-hex
blake3 (the corpus identity algorithm, §2); `location` names the `[[corpus.location]]`
entry (`config.py`); `relpath` is the file's path relative to the location's root,
POSIX-separated; `size` + `mtime` (`st_mtime_ns`, exact int compare — no float fuzz)
are the **staleness pins** an attached file's mutability demands (§12.1.1). Primary key
`(location, relpath)` — one row per file; an index on `hash` serves `route_for`'s
lookup.

An attested file may have no record yet — pre-promotion, this index is the only memory
of its hash (§12.9.2), unlike `hashes.db` whose rows are keyed by `record_id` and so
cannot hold a pre-promotion row at all. The attest pass therefore does NOT opportunis-
tically fill `hashes.db` while hashing here (§12.9.1's "hash while bytes are in hand"
principle otherwise suggests it) — there is no record to key that row on yet. That
fill happens at promotion instead, a later wave (§12.1.1: "promotion mints records
without moving bytes").
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from . import config as config_mod
from . import hashing, paths

_SCHEMA = """
CREATE TABLE IF NOT EXISTS locations (
    hash     TEXT NOT NULL,
    location TEXT NOT NULL,
    relpath  TEXT NOT NULL,
    size     INTEGER NOT NULL,
    mtime    INTEGER NOT NULL,
    PRIMARY KEY (location, relpath)
);
CREATE INDEX IF NOT EXISTS idx_locations_hash ON locations (hash);
"""


def db_path(corpus_root: Path) -> Path:
    """`<corpus_root>/cache/locations.db` (spec §12.9.2). `cache/` is created if
    absent."""
    return paths.cache_dir(corpus_root) / "locations.db"


def connect(corpus_root: Path) -> sqlite3.Connection:
    """Open (creating if absent) the index at `db_path(corpus_root)`, WAL mode — the
    same resolver-cache posture as `hashindex.connect` (§12.9.1/§12.9.2: deployment
    state, not a service)."""
    path = db_path(corpus_root)
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


@contextmanager
def open_index(corpus_root: Path) -> Iterator[sqlite3.Connection]:
    """Context-managed `connect` — closes the connection on exit."""
    conn = connect(corpus_root)
    try:
        yield conn
    finally:
        conn.close()


def _iter_files(root: Path) -> Iterator[Path]:
    """Every regular file under `root`, skipping hidden dotfiles/dot-directories (an
    attached tree is operator-managed and may carry its own `.git`, `.DS_Store`, etc.
    — none of it is corpus content) and our own sidecar debris."""
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        yield p


def attest_location(
    corpus_root: Path,
    location: config_mod.LocationConfig,
    *,
    progress: Callable[[int], None] | None = None,
) -> dict[str, int]:
    """Walk `location`'s tree and bring its rows in `locations.db` up to date (spec
    §12.1.1's attest pass). Incremental by construction: a file whose `(size, mtime)`
    still match its existing row is left alone — NOT re-hashed — so a re-run over an
    unchanged tree hashes nothing. A new or changed file is streamed and blake3-hashed
    (1 MiB chunks, `hashing.hash_file`). A row whose file no longer exists is removed.

    `progress`, when given, is called with the running `files_seen` count as the walk
    proceeds (a caller wanting periodic feedback, e.g. every 500 files, checks the
    count itself — this only ever calls forward, never batches).

    Returns `{"files": total_seen, "hashed": n_new_or_changed, "unchanged": n,
    "removed": n}`.
    """
    root = location.path
    if not root.is_dir():
        raise ValueError(
            f"attached location {location.name!r}: path {root} is not a directory "
            f"(check corpus.toml [[corpus.location]])."
        )

    files_seen = 0
    hashed = 0
    unchanged = 0

    with open_index(corpus_root) as conn:
        cur = conn.execute(
            "SELECT relpath, size, mtime FROM locations WHERE location = ?",
            (location.name,),
        )
        existing = {relpath: (size, mtime) for relpath, size, mtime in cur.fetchall()}
        seen_relpaths: set[str] = set()
        upserts: list[tuple[str, str, str, int, int]] = []

        for path in _iter_files(root):
            relpath = path.relative_to(root).as_posix()
            seen_relpaths.add(relpath)
            files_seen += 1
            st = path.stat()
            size = st.st_size
            mtime = st.st_mtime_ns

            if existing.get(relpath) == (size, mtime):
                unchanged += 1
            else:
                digest = hashing.hash_file(path, also=())["blake3"]
                upserts.append((digest, location.name, relpath, size, mtime))
                hashed += 1

            if progress is not None and files_seen % 500 == 0:
                progress(files_seen)

        if upserts:
            conn.executemany(
                "INSERT INTO locations (hash, location, relpath, size, mtime) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (location, relpath) DO UPDATE SET "
                "hash = excluded.hash, size = excluded.size, mtime = excluded.mtime",
                upserts,
            )

        removed_relpaths = set(existing) - seen_relpaths
        if removed_relpaths:
            conn.executemany(
                "DELETE FROM locations WHERE location = ? AND relpath = ?",
                [(location.name, rp) for rp in removed_relpaths],
            )

    return {
        "files": files_seen,
        "hashed": hashed,
        "unchanged": unchanged,
        "removed": len(removed_relpaths),
    }


def route_for(corpus_root: Path, hash_: str) -> Path | None:
    """Resolve `hash_` (bare-hex blake3) to an absolute path through the attached-
    location index, or `None` when unresolvable (spec §12.1.1). A hit requires both an
    indexed row AND the file's current `(size, mtime)` to still match the row's pins —
    the route serves bytes only while the pins hold. A stale or vanished file is
    reported as unresolvable here, never deleted: refresh happens only by re-attest,
    never silently at read time (§12.9.2).

    Several rows may share a hash (the same bytes attested under more than one
    location, or more than one path within one) — the first one whose pins still
    verify is returned; any route yields identical bytes (§2)."""
    with open_index(corpus_root) as conn:
        cur = conn.execute(
            "SELECT location, relpath, size, mtime FROM locations WHERE hash = ?",
            (hash_,),
        )
        rows = cur.fetchall()
    if not rows:
        return None

    by_name = {loc.name: loc.path for loc in config_mod.load_config(corpus_root).locations}
    for loc_name, relpath, size, mtime in rows:
        base = by_name.get(loc_name)
        if base is None:
            continue  # location no longer configured
        candidate = base / relpath
        try:
            st = candidate.stat()
        except OSError:
            continue  # vanished — stale, not deleted here (see docstring)
        if st.st_size == size and st.st_mtime_ns == mtime:
            return candidate
    return None


def stale_rows(corpus_root: Path) -> list[tuple[str, str, str]]:
    """`[(location, relpath, hash), ...]` for every row whose staleness pins mismatch
    or whose file has vanished (spec §12.1.1's health signal) — including rows whose
    `location` is no longer declared in `corpus.toml` at all."""
    by_name = {loc.name: loc.path for loc in config_mod.load_config(corpus_root).locations}
    out: list[tuple[str, str, str]] = []
    with open_index(corpus_root) as conn:
        cur = conn.execute("SELECT hash, location, relpath, size, mtime FROM locations")
        rows = cur.fetchall()
    for hash_, loc_name, relpath, size, mtime in rows:
        base = by_name.get(loc_name)
        if base is None:
            out.append((loc_name, relpath, hash_))
            continue
        candidate = base / relpath
        try:
            st = candidate.stat()
        except OSError:
            out.append((loc_name, relpath, hash_))
            continue
        if st.st_size != size or st.st_mtime_ns != mtime:
            out.append((loc_name, relpath, hash_))
    return out


def row_count(corpus_root: Path, location: str) -> int:
    """Count of indexed rows for one location — `corpus location list`'s per-row
    count."""
    with open_index(corpus_root) as conn:
        cur = conn.execute("SELECT COUNT(*) FROM locations WHERE location = ?", (location,))
        (n,) = cur.fetchone()
    return int(n)
