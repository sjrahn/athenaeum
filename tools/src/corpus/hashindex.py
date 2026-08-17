"""The derived hash index — the query layer over every recipe value (spec §12.9.1).

SQLite at `<corpus_root>/cache/hashes.db` — deployment state in the resolver-cache mold
(§12.1): untracked, regenerable, never authoritative. A missing row means "unindexed",
never a failure — every reader here treats a miss as exactly that; nothing normative
depends on this index existing (§2).

Row shape `(record_id, recipe, algo, value, param)` (§12.9.1): `algo` is the §7.6 tag
(`sha256`, `blake3-64k`, `html-stampfree@1`) — `<algo>:<hex>` reassembles per §7.6,
version tag included for a procedure-versioned row; `param` distinguishes a multi-value
recipe's rows (the prefix ladder's rung length; a fingerprint's segment address, later)
and is the empty string otherwise. Primary key / upsert on
`(record_id, recipe, algo, param)`; an index on `(algo, value)` serves the join queries
the same-document duplicate signal and the grown-export prefix screen run (§12.9.1).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from . import paths, records

_SCHEMA = """
CREATE TABLE IF NOT EXISTS hashes (
    record_id TEXT NOT NULL,
    recipe    TEXT NOT NULL,
    algo      TEXT NOT NULL,
    value     TEXT NOT NULL,
    param     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (record_id, recipe, algo, param)
);
CREATE INDEX IF NOT EXISTS idx_hashes_algo_value ON hashes (algo, value);
CREATE INDEX IF NOT EXISTS idx_hashes_record ON hashes (record_id);
"""


@dataclass(frozen=True)
class HashRow:
    """One index row (spec §12.9.1's reference shape)."""

    record_id: str
    recipe: str
    algo: str
    value: str
    param: str = ""

    def encoded(self) -> str:
        """The `<algo>:<hex>` reassembly (spec §7.6)."""
        return f"{self.algo}:{self.value}"


def db_path(corpus_root: Path) -> Path:
    """`<corpus_root>/cache/hashes.db` (spec §12.9.1). `cache/` is created if absent."""
    return paths.cache_dir(corpus_root) / "hashes.db"


def connect(corpus_root: Path) -> sqlite3.Connection:
    """Open (creating if absent) the index at `db_path(corpus_root)`, WAL mode — safe
    for one writer plus concurrent readers, matching the resolver-cache posture this
    index shares (§12.9.1: deployment state, not a service)."""
    path = db_path(corpus_root)
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


@contextmanager
def open_index(corpus_root: Path) -> Iterator[sqlite3.Connection]:
    """Context-managed `connect` — closes the connection on exit. The convenience for a
    one-shot query or write; a caller doing many operations in one process may prefer
    to hold `connect()`'s connection open itself."""
    conn = connect(corpus_root)
    try:
        yield conn
    finally:
        conn.close()


def upsert_rows(conn: sqlite3.Connection, rows: Iterable[HashRow]) -> int:
    """Insert or replace `rows`, keyed on `(record_id, recipe, algo, param)`. Returns
    the row count written. Idempotent — re-upserting identical rows changes nothing."""
    rows = list(rows)
    if not rows:
        return 0
    conn.executemany(
        "INSERT INTO hashes (record_id, recipe, algo, value, param) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (record_id, recipe, algo, param) DO UPDATE SET value = excluded.value",
        [(r.record_id, r.recipe, r.algo, r.value, r.param) for r in rows],
    )
    return len(rows)


def rows_for(conn: sqlite3.Connection, record_id: str) -> list[HashRow]:
    """Every indexed row for `record_id` — empty when nothing is indexed for it."""
    cur = conn.execute(
        "SELECT record_id, recipe, algo, value, param FROM hashes WHERE record_id = ?",
        (record_id,),
    )
    return [HashRow(*row) for row in cur.fetchall()]


def values_by_algo(conn: sqlite3.Connection, algo: str) -> dict[str, list[str]]:
    """`{value: [record_id, ...]}` for every row tagged `algo` — the join-friendly
    shape the same-document / grown-export health signals consume (spec §12.9.1)."""
    cur = conn.execute(
        "SELECT value, record_id FROM hashes WHERE algo = ? ORDER BY value, record_id",
        (algo,),
    )
    out: dict[str, list[str]] = {}
    for value, record_id in cur.fetchall():
        out.setdefault(value, []).append(record_id)
    return out


def missing(
    conn: sqlite3.Connection, record_ids: Iterable[str], recipe_ids: Iterable[str]
) -> dict[str, list[str]]:
    """`{record_id: [recipe_id, ...]}` for every `(record_id, recipe_id)` pair in the
    cross product of `record_ids` x `recipe_ids` with NO row in the index — the
    backfill pass's worklist (§12.9.1). A recipe's presence is checked by `recipe`
    alone: ANY row for that recipe counts, so a multi-value recipe with only SOME
    rungs indexed (a short file that never reached the deeper rungs) is not "missing"
    on that account.
    """
    record_ids = list(dict.fromkeys(record_ids))
    recipe_ids = list(dict.fromkeys(recipe_ids))
    if not record_ids or not recipe_ids:
        return {}
    placeholders = ",".join("?" * len(record_ids))
    cur = conn.execute(
        f"SELECT DISTINCT record_id, recipe FROM hashes WHERE record_id IN ({placeholders})",
        record_ids,
    )
    present: dict[str, set[str]] = {}
    for record_id, recipe in cur.fetchall():
        present.setdefault(record_id, set()).add(recipe)
    out: dict[str, list[str]] = {}
    for record_id in record_ids:
        have = present.get(record_id, set())
        want = [r for r in recipe_ids if r not in have]
        if want:
            out[record_id] = want
    return out


def delete_record(conn: sqlite3.Connection, record_id: str) -> int:
    """Remove every row for `record_id` (a record deletion or supersession). Returns
    the count removed."""
    cur = conn.execute("DELETE FROM hashes WHERE record_id = ?", (record_id,))
    return cur.rowcount


def sync_from_records(corpus_root: Path, refs: Iterable[tuple[str, object]]) -> int:
    """Mirror every record-resident `hash:` value into the index (spec §12.9.1's
    record sync) — rebuildable from `records/` alone, no bytes needed. `refs` is
    `(record_id, post)` pairs; a caller already walking `records.load_all` hands them
    over directly rather than this module re-reading the corpus itself. Opens and
    closes its own connection. Returns the row count written.

    A record-resident value carries no recipe id of its own in the frontmatter — only
    its tag survives (§7.6) — so the recipe is recovered from the tag: a single-value
    recipe's id equals its tag, byte-stable or procedure-versioned alike (the prefix
    ladder is the one multi-value exception, and it is never record-resident, so this
    never needs to invert a rung tag back to `blake3-prefix-ladder`). A tag naming an
    unregistered recipe (a legacy/ad hoc `transport_algos` algorithm, §7.9) still syncs
    under its own tag as the recipe id — it never needed registry membership to be
    stored in the first place.
    """
    rows: list[HashRow] = []
    for record_id, post in refs:
        for tag, hexval in records.record_hashes(post).items():  # type: ignore[arg-type]
            rows.append(HashRow(record_id=record_id, recipe=tag, algo=tag, value=hexval))
    with open_index(corpus_root) as conn:
        return upsert_rows(conn, rows)
