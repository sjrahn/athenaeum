"""The attached-location index — the derived map for the third route class (spec
§12.1.1, §12.9.2).

SQLite at `<corpus_root>/cache/locations.db` — in the `hashindex.py` mold (§12.9.1):
untracked, never authoritative, gc-excluded by name (§12.8) because recomputation
needs *bytes*, which for a multi-GB attached tree is hours, not milliseconds. A missing
row means "unattested", never a failure.

Row shape `(hash, location, relpath, size, mtime, source)` (§12.9.2, `source` added
§12.1.1 (24)): `hash` is the bare-hex blake3 (the corpus identity algorithm, §2);
`location` names the `[[corpus.location]]` entry (`config.py`); `relpath` is the
file's path relative to the location's root, POSIX-separated; `size` + `mtime`
(`st_mtime_ns`) are the **staleness pins** an attached file's mutability demands
(§12.1.1) — compared via `pins_match`, exactly for `source='computed'`, tolerant of
sub-100ns drift for `source='presented'` (see `pins_match`'s docstring). `source` is a
row's provenance: `'computed'` (an ordinary walking attest hashed the bytes itself) or
`'presented'` (imported from a residence scanner's manifest, §12.1.1 (24) — a host
claim the corpus has not independently observed). Primary key `(location, relpath)` —
one row per file; an index on `hash` serves `route_for`'s lookup.

`manifest_imports(location, generation, imported_at)` tracks, per presenting location,
the manifest generation last imported by `attest_from_manifest` — the no-op guard for a
re-attest against an unchanged manifest.

An attested file may have no record yet — pre-promotion, this index is the only memory
of its hash (§12.9.2), unlike `hashes.db` whose rows are keyed by `record_id` and so
cannot hold a pre-promotion row at all. The attest pass therefore does NOT opportunis-
tically fill `hashes.db` while hashing here (§12.9.1's "hash while bytes are in hand"
principle otherwise suggests it) — there is no record to key that row on yet. That
fill happens at promotion instead, a later wave (§12.1.1: "promotion mints records
without moving bytes").
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from . import config as config_mod
from . import hashing, paths, touches

_SCHEMA = """
CREATE TABLE IF NOT EXISTS locations (
    hash     TEXT NOT NULL,
    location TEXT NOT NULL,
    relpath  TEXT NOT NULL,
    size     INTEGER NOT NULL,
    mtime    INTEGER NOT NULL,
    source   TEXT NOT NULL DEFAULT 'computed',
    PRIMARY KEY (location, relpath)
);
CREATE INDEX IF NOT EXISTS idx_locations_hash ON locations (hash);
CREATE TABLE IF NOT EXISTS manifest_imports (
    location    TEXT PRIMARY KEY,
    generation  INTEGER NOT NULL,
    imported_at TEXT NOT NULL
);
"""

#: The manifest contract version this reader is pinned to (spec §12.1.1 (24)) — the
#: writer's own versioned cross-language contract, deliberately outside this spec.
MANIFEST_SCHEMA_VERSION = 2

#: Filesystem-metadata junk excluded from the walking attest — a CURATED POSITIVE
#: deny-list, deliberately NOT "skip every hidden dotfile": an attached tree may carry
#: wanted dotfile content (`.config`, `.git`, ...) which the walking attest now indexes
#: like any other file. A trailing `*` is a prefix match (see `_is_ignored_name`); every
#: other entry is an exact basename match. A matched directory is pruned — its subtree is
#: never walked. This is the Python half of a two-language shared list: the residence
#: scanner's `scanner/src/schema.ts` DEFAULT_IGNORE_PATTERNS is the sibling copy and must
#: be kept in sync by hand — there's no single build step spanning both languages.
_DEFAULT_IGNORE_PATTERNS: tuple[str, ...] = (
    ".DS_Store",
    "._*",
    ".AppleDouble",
    ".AppleDesktop",
    ".TemporaryItems",
    ".Trashes",
    ".Spotlight-V100",
    ".fseventsd",
    ".DocumentRevisions-V100",
    "Thumbs.db",
    "desktop.ini",
    "@eaDir",
    ".@__thumb",
)


def _is_ignored_name(name: str, patterns: tuple[str, ...] = _DEFAULT_IGNORE_PATTERNS) -> bool:
    """Whether basename `name` matches any pattern in `patterns` — a trailing `*` is a
    prefix match, everything else is an exact match. Mirrors the scanner's
    `matchesIgnorePattern`/`isIgnoredName` in `scanner/src/walk.ts`."""
    for pattern in patterns:
        if pattern.endswith("*"):
            if name.startswith(pattern[:-1]):
                return True
        elif name == pattern:
            return True
    return False


def db_path(corpus_root: Path) -> Path:
    """`<corpus_root>/cache/locations.db` (spec §12.9.2). `cache/` is created if
    absent."""
    return paths.cache_dir(corpus_root) / "locations.db"


def _migrate_source_column(conn: sqlite3.Connection) -> None:
    """Add `locations.source` (spec §12.1.1 (24)) to a pre-v24 db in place. Every row a
    pre-v24 db could hold came from a walking attest, so the upgrade defaults them all
    to `'computed'` — exactly what they always were."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(locations)")}
    if "source" not in cols:
        conn.execute("ALTER TABLE locations ADD COLUMN source TEXT NOT NULL DEFAULT 'computed'")


def connect(corpus_root: Path) -> sqlite3.Connection:
    """Open (creating if absent) the index at `db_path(corpus_root)`, WAL mode — the
    same resolver-cache posture as `hashindex.connect` (§12.9.1/§12.9.2: deployment
    state, not a service)."""
    path = db_path(corpus_root)
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    _migrate_source_column(conn)
    return conn


def pins_match(
    row_size: int, row_mtime: int, st_size: int, st_mtime_ns: int, source: str
) -> bool:
    """Whether a location-index row's staleness pins still match a fresh `os.stat()`
    (spec §12.1.1 (24)). `size` is always compared exactly. `mtime` is compared exactly
    for `source='computed'` (attest hashed these bytes itself, on this host, through
    this same filesystem view) but tolerates sub-100ns drift for `source='presented'`:
    a scanner-published row's mtime was captured on the remote host's *local*
    filesystem, while our stat crosses an SMB/NFS mount that widens NT time to 100ns
    granularity — the low digits can differ without the file having changed, so
    presented rows compare at 100ns resolution (`// 100`) rather than the raw ns int."""
    if row_size != st_size:
        return False
    if source == "presented":
        return row_mtime // 100 == st_mtime_ns // 100
    return row_mtime == st_mtime_ns


@contextmanager
def open_index(corpus_root: Path) -> Iterator[sqlite3.Connection]:
    """Context-managed `connect` — closes the connection on exit."""
    conn = connect(corpus_root)
    try:
        yield conn
    finally:
        conn.close()


def _iter_files(root: Path) -> Iterator[Path]:
    """Every regular file under `root`, skipping the filesystem-metadata junk deny-list
    (`_DEFAULT_IGNORE_PATTERNS`, above — a matched directory is pruned, its subtree never
    walked) plus `.athenaeum` (the residence scanner's manifest dir — infrastructure,
    never content, always pruned unconditionally). This is NOT a blanket hidden-dotfile
    skip: an attached tree's other dotfiles (`.config`, `.git`, ...) are ordinary content
    and are indexed like anything else."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".athenaeum" and not _is_ignored_name(d)]
        for name in filenames:
            if _is_ignored_name(name):
                continue
            p = Path(dirpath) / name
            if p.is_file():
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
            "SELECT relpath, size, mtime, source FROM locations WHERE location = ?",
            (location.name,),
        )
        existing = {
            relpath: (size, mtime, source) for relpath, size, mtime, source in cur.fetchall()
        }
        seen_relpaths: set[str] = set()
        upserts: list[tuple[str, str, str, int, int]] = []

        for path in _iter_files(root):
            relpath = path.relative_to(root).as_posix()
            seen_relpaths.add(relpath)
            files_seen += 1
            st = path.stat()
            size = st.st_size
            mtime = st.st_mtime_ns

            prior = existing.get(relpath)
            # A `presented` row is never left standing by a walking attest — even one
            # whose pins happen to match exactly gets re-hashed so it becomes `computed`
            # (spec §12.1.1 (24)'s re-verification path: `--walk` overwrites presented
            # rows, unconditionally).
            unchanged_computed = (
                prior is not None and prior[0] == size and prior[1] == mtime
                and prior[2] == "computed"
            )
            if unchanged_computed:
                unchanged += 1
            else:
                digest = hashing.hash_file(path, also=())["blake3"]
                upserts.append((digest, location.name, relpath, size, mtime))
                hashed += 1

            if progress is not None and files_seen % 500 == 0:
                progress(files_seen)

        if upserts:
            conn.executemany(
                "INSERT INTO locations (hash, location, relpath, size, mtime, source) "
                "VALUES (?, ?, ?, ?, ?, 'computed') "
                "ON CONFLICT (location, relpath) DO UPDATE SET "
                "hash = excluded.hash, size = excluded.size, mtime = excluded.mtime, "
                "source = excluded.source",
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


def attest_from_manifest(
    corpus_root: Path,
    location: config_mod.LocationConfig,
    *,
    force: bool = False,
) -> dict:
    """Import a presenting location's published `<location.path>/.athenaeum/
    manifest.sqlite` (spec §12.1.1 (24), manifest contract v2) — the residence
    scanner's own generation-checkpointed database — into `locations.db` as
    `source='presented'` rows, instead of walking the tree ourselves.

    Refuses (`ValueError`) when the scanner hasn't published a manifest yet, when its
    `PRAGMA user_version` isn't the pinned contract version 2, or when it carries no
    completed generation (`MAX(generation) WHERE finished_at IS NOT NULL` is `NULL` —
    the scanner's cold pass is still running). A no-op (`{"skipped": True, "generation":
    g}`) when the manifest's current generation already equals the one recorded in
    `manifest_imports` for this location, unless `force`. Otherwise every row for this
    location — both provenances, since a presenting location is now wholly
    manifest-described — is replaced in one transaction with one row per `(path x
    identity)` join (hardlinked paths share one identity and so one hash, but each
    still gets its own row), and `manifest_imports` is upserted to the new generation.
    Returns `{"files": n, "generation": g, "skipped": False}`.

    The manifest is copied to a temp file under the corpus cache dir before it is
    opened — never opened in place over SMB/NFS — and that copy is removed again once
    this returns (success or failure)."""
    manifest_path = location.path / ".athenaeum" / "manifest.sqlite"
    if not manifest_path.is_file():
        raise ValueError(
            f"attached location {location.name!r}: scanner has not published a "
            f"manifest at {manifest_path} (spec §12.1.1 (24)) — run the residence "
            f"scanner on the remote host first, or pass --walk for an ordinary "
            f"walking attest."
        )

    cache = paths.cache_dir(corpus_root)
    fd, tmp_name = tempfile.mkstemp(dir=cache, suffix=".manifest.sqlite")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        shutil.copyfile(manifest_path, tmp_path)
        mconn = sqlite3.connect(f"file:{tmp_path}?mode=ro", uri=True)
        try:
            (version,) = mconn.execute("PRAGMA user_version").fetchone()
            if version != MANIFEST_SCHEMA_VERSION:
                raise ValueError(
                    f"attached location {location.name!r}: manifest at {manifest_path} "
                    f"declares schema version {version}, expected "
                    f"{MANIFEST_SCHEMA_VERSION} (spec §12.1.1 (24), manifest contract "
                    f"v{MANIFEST_SCHEMA_VERSION}) — refusing to import."
                )
            (generation,) = mconn.execute(
                "SELECT MAX(generation) FROM generations WHERE finished_at IS NOT NULL"
            ).fetchone()
            if generation is None:
                raise ValueError(
                    f"attached location {location.name!r}: manifest at {manifest_path} "
                    f"has no completed generation yet (scanner cold pass still "
                    f"running?) — refusing to import."
                )

            with open_index(corpus_root) as conn:
                prior = conn.execute(
                    "SELECT generation FROM manifest_imports WHERE location = ?",
                    (location.name,),
                ).fetchone()
                if prior is not None and prior[0] == generation and not force:
                    return {"skipped": True, "generation": generation}

                rows = mconn.execute(
                    "SELECT p.path, i.size, i.mtime_ns, i.blake3 "
                    "FROM paths p JOIN identities i ON p.dev = i.dev AND p.ino = i.ino"
                ).fetchall()

                conn.execute("BEGIN")
                try:
                    conn.execute("DELETE FROM locations WHERE location = ?", (location.name,))
                    conn.executemany(
                        "INSERT INTO locations "
                        "(hash, location, relpath, size, mtime, source) "
                        "VALUES (?, ?, ?, ?, ?, 'presented')",
                        [
                            (blake3, location.name, path, size, mtime_ns)
                            for path, size, mtime_ns, blake3 in rows
                        ],
                    )
                    conn.execute(
                        "INSERT INTO manifest_imports (location, generation, imported_at) "
                        "VALUES (?, ?, ?) "
                        "ON CONFLICT (location) DO UPDATE SET "
                        "generation = excluded.generation, "
                        "imported_at = excluded.imported_at",
                        (location.name, generation, touches.now_iso()),
                    )
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
                else:
                    conn.execute("COMMIT")
        finally:
            mconn.close()
    finally:
        tmp_path.unlink(missing_ok=True)

    return {"files": len(rows), "generation": generation, "skipped": False}


def route_for(corpus_root: Path, hash_: str) -> Path | None:
    """Resolve `hash_` (bare-hex blake3) to an absolute path through the attached-
    location index, or `None` when unresolvable (spec §12.1.1). A hit requires both an
    indexed row AND the file's current `(size, mtime)` to still match the row's pins —
    the route serves bytes only while the pins hold. A stale or vanished file is
    reported as unresolvable here, never deleted: refresh happens only by re-attest,
    never silently at read time (§12.9.2).

    Several rows may share a hash (the same bytes attested under more than one
    location, or more than one path within one) — the first one whose pins still
    verify is returned; any route yields identical bytes (§2). Pins are compared via
    `pins_match` — exact for `source='computed'` rows, tolerant of sub-100ns mtime
    drift for `source='presented'` rows (§12.1.1 (24))."""
    with open_index(corpus_root) as conn:
        cur = conn.execute(
            "SELECT location, relpath, size, mtime, source FROM locations WHERE hash = ?",
            (hash_,),
        )
        rows = cur.fetchall()
    if not rows:
        return None

    by_name = {loc.name: loc.path for loc in config_mod.load_config(corpus_root).locations}
    for loc_name, relpath, size, mtime, source in rows:
        base = by_name.get(loc_name)
        if base is None:
            continue  # location no longer configured
        candidate = base / relpath
        try:
            st = candidate.stat()
        except OSError:
            continue  # vanished — stale, not deleted here (see docstring)
        if pins_match(size, mtime, st.st_size, st.st_mtime_ns, source):
            return candidate
    return None


def stale_rows(corpus_root: Path) -> list[tuple[str, str, str]]:
    """`[(location, relpath, hash), ...]` for every row whose staleness pins mismatch
    (via `pins_match`) or whose file has vanished (spec §12.1.1's health signal) —
    including rows whose `location` is no longer declared in `corpus.toml` at all."""
    by_name = {loc.name: loc.path for loc in config_mod.load_config(corpus_root).locations}
    out: list[tuple[str, str, str]] = []
    with open_index(corpus_root) as conn:
        cur = conn.execute("SELECT hash, location, relpath, size, mtime, source FROM locations")
        rows = cur.fetchall()
    for hash_, loc_name, relpath, size, mtime, source in rows:
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
        if not pins_match(size, mtime, st.st_size, st.st_mtime_ns, source):
            out.append((loc_name, relpath, hash_))
    return out


def current_rows_by_hash(corpus_root: Path) -> dict[str, list[tuple[str, str]]]:
    """`{hash: [(location, relpath), ...]}` for every row whose staleness pins still
    match (via `pins_match`; spec §12.1.1's adoption paragraph, v23: a health scan's
    join key for the **shadowed-copies** and **duplicate-residencies** signals). The
    current-row complement of `stale_rows`: a row whose location is no longer
    configured, whose file has vanished, or whose pins have drifted since attest is
    excluded here exactly as it is included there."""
    by_name = {loc.name: loc.path for loc in config_mod.load_config(corpus_root).locations}
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    with open_index(corpus_root) as conn:
        cur = conn.execute("SELECT hash, location, relpath, size, mtime, source FROM locations")
        rows = cur.fetchall()
    for hash_, loc_name, relpath, size, mtime, source in rows:
        base = by_name.get(loc_name)
        if base is None:
            continue
        candidate = base / relpath
        try:
            st = candidate.stat()
        except OSError:
            continue
        if pins_match(size, mtime, st.st_size, st.st_mtime_ns, source):
            out[hash_].append((loc_name, relpath))
    return dict(out)


def row_count(corpus_root: Path, location: str) -> int:
    """Count of indexed rows for one location — `corpus location list`'s per-row
    count."""
    with open_index(corpus_root) as conn:
        cur = conn.execute("SELECT COUNT(*) FROM locations WHERE location = ?", (location,))
        (n,) = cur.fetchone()
    return int(n)
