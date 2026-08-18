"""The `osm-pbf` format adapter — resolves native ids against an OpenStreetMap
PBF extract (Geofabrik, …; spec/ledger.md §6.5). Optional dependency:
`osmium` (the `osm` extra, `pyproject.toml`). Guard-imported so this module —
and `refdata.adapters` importing it — loads cleanly without the extra;
`available()` reports the guarded truth.

Unlike ZIM, a PBF is a compressed stream with **no random access by element
id and no search index of its own**. This adapter needs a one-time sidecar
SQLite index, built by scanning the file once (`build_index`, module-level —
part of this adapter's public surface, called by the `ath ref index` CLI
verb, not by this module) — absent or stale, `resolve_entry`/`search_entries`
raise `refdata.errors.MirrorUnindexed` rather than crash or silently degrade
(§6.5: "content resolution … absent … reports unverifiable, never failure").

Native id grammar: `{node|way|relation}/{decimal id}` (e.g. `way/12345`).
OSM has no redirects, so `canonical_id == native_id` always — unlike ZIM,
which follows a redirect to report a different canonical path.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Callable
from pathlib import Path

from ..errors import EntryNotFound, MirrorCorrupt, MirrorUnindexed
from . import AdapterResult, AdapterSearchHit

try:
    import osmium as _osmium  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised by the no-extra environment
    _osmium = None

# Bump only on a sidecar schema change — `index_state` treats a mismatch as
# staleness, forcing a rebuild rather than reading a schema this code no
# longer understands.
_BUILDER = "osm-refidx@1"
_BATCH_SIZE = 50_000

_NATIVE_ID_RE = re.compile(r"^(node|way|relation)/([0-9]+)$")
_ETYPE_FROM_CODE = {"n": "node", "w": "way", "r": "relation"}
# Preference chain for an element's display name (empirically the common OSM
# naming tags, in order of specificity/reliability); the first present,
# non-empty value wins.
_NAME_TAGS = ("name", "name:en", "official_name", "alt_name")
# The common OSM top-level classifying keys, most identity-bearing first —
# search context uses the first of these present on an element's tags.
_CONTEXT_TAGS = (
    "place", "boundary", "amenity", "shop", "leisure", "tourism", "natural",
    "historic", "man_made", "landuse", "building", "highway", "railway",
    "waterway", "aeroway", "power", "office", "craft", "sport",
)


def available() -> bool:
    return _osmium is not None


def _sidecar_path(mirror_path: Path) -> Path:
    return Path(str(mirror_path) + ".refidx")


class _Handle:
    """An open `osm-pbf` mirror: the pbf path, plus a sidecar sqlite
    connection opened lazily on first use. The pbf itself needs no held-open
    handle (osmium reads it fresh per `build_index` call; `resolve_entry`/
    `search_entries` only ever touch the sidecar) — what this class caches,
    per `refdata`'s handle-cache contract, is the sqlite connection, since
    the sidecar may not exist yet when `open_archive` runs (the index is
    built after the mirror is registered) and connecting is what needs to
    happen lazily. Staleness is re-checked only when (re)opening the
    connection, not on every query — a live connection stays live until the
    handle itself is discarded (process-lifetime, per `refdata._HANDLES`)."""

    def __init__(self, mirror_path: Path) -> None:
        self.mirror_path = mirror_path
        self._conn: sqlite3.Connection | None = None

    def connection(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        state = index_state(self.mirror_path)
        if state != "indexed":
            raise MirrorUnindexed(
                f"{self.mirror_path}: sidecar index {_sidecar_path(self.mirror_path)} "
                f"is {state} — build it with `ath ref index <dataset>`"
            )
        self._conn = sqlite3.connect(str(_sidecar_path(self.mirror_path)))
        return self._conn


def open_archive(mirror_path: Path) -> _Handle:
    """Validate the pbf opens (a header read — the same "construction is
    where the library actually validates the file" empirical fact as libzim,
    confirmed against pyosmium 4.3.1: a truncated/corrupted pbf raises
    `RuntimeError` here, a missing path raises `RuntimeError` too) — wrapped
    as `MirrorCorrupt` so it joins the typed `RefdataError` hierarchy. The
    sidecar index is deliberately NOT checked here — a handle opened before
    the index exists must keep working once one is built later (see
    `_Handle.connection`, checked lazily per call instead)."""
    assert _osmium is not None, "osm-pbf adapter unavailable — check available() first"
    try:
        reader = _reader_header_only(mirror_path)
        reader.header()
        reader.close()
    except (RuntimeError, OSError) as exc:
        raise MirrorCorrupt(f"{mirror_path}: {exc}") from exc
    return _Handle(mirror_path)


def _reader_header_only(mirror_path: Path):  # type: ignore[no-untyped-def]
    """A Reader restricted to `osm_entity_bits.NOTHING` — a default Reader
    eagerly spins up threaded decompression of the whole file even when only
    `header()` is wanted (measured: ~38s of CPU on the 6 GB Canada extract vs
    ~1ms restricted; corrupt/missing files raise the same `RuntimeError`s
    either way)."""
    assert _osmium is not None
    return _osmium.io.Reader(str(mirror_path), _osmium.osm.osm_entity_bits.NOTHING)


def index_state(mirror_path: Path) -> str:
    """`"indexed"` | `"missing"` | `"stale"`. Stale covers both an
    index-schema mismatch (`builder` != current — read this code's sidecar
    with old assumptions rather than rebuild would be a silent bug) and a
    changed mirror (`source_size` != the pbf's current byte size — the
    cheapest drift signal available without re-scanning; content-addressed
    mirrors don't change size without changing bytes)."""
    sidecar = _sidecar_path(mirror_path)
    if not sidecar.is_file():
        return "missing"
    try:
        conn = sqlite3.connect(str(sidecar))
        try:
            meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return "stale"
    if meta.get("builder") != _BUILDER:
        return "stale"
    try:
        current_size = mirror_path.stat().st_size
    except OSError:
        return "stale"
    if meta.get("source_size") != str(current_size):
        return "stale"
    return "indexed"


def build_index(
    mirror_path: Path, *, progress: Callable[[int], None] | None = None
) -> dict[str, int]:
    """Scan `mirror_path` once, writing the sidecar SQLite index beside it
    (`_sidecar_path`). Tagged elements only: pyosmium's `EmptyTagFilter`
    drops untagged nodes — bare geometry vertices, never quotable content —
    before Python sees them, at C++ speed (~55M tagged elements / ~91s on
    the real 6 GB Canada Geofabrik extract). Inserts batch at `_BATCH_SIZE`
    rows (`executemany`); `progress`, if given, is called with the
    cumulative indexed-element count at each batch flush.

    Written atomically: built at `<sidecar>.tmp`, then `os.replace`d into
    place, so a reader (via `index_state`/`_Handle.connection`) never
    observes a half-built index — either the old one (or none), or the
    complete new one.

    Raises `MirrorCorrupt` if pyosmium can't read `mirror_path` as a pbf.
    """
    assert _osmium is not None, "osm-pbf adapter unavailable — check available() first"
    sidecar = _sidecar_path(mirror_path)
    tmp_path = Path(str(sidecar) + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    try:
        header = _reader_header_only(mirror_path).header()
        replication_timestamp = header.get("osmosis_replication_timestamp", "")
    except (RuntimeError, OSError) as exc:
        raise MirrorCorrupt(f"{mirror_path}: {exc}") from exc

    conn = sqlite3.connect(str(tmp_path))
    try:
        conn.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(
            "CREATE TABLE elements("
            "etype TEXT NOT NULL, id INTEGER NOT NULL, lat REAL, lon REAL, "
            "tags TEXT NOT NULL, PRIMARY KEY (etype, id)) WITHOUT ROWID"
        )
        conn.execute(
            "CREATE VIRTUAL TABLE names USING fts5(name, etype UNINDEXED, id UNINDEXED)"
        )

        element_batch: list[tuple[str, int, float | None, float | None, str]] = []
        name_batch: list[tuple[str, str, int]] = []
        elements = 0
        named = 0

        def flush() -> None:
            if element_batch:
                conn.executemany(
                    "INSERT INTO elements(etype, id, lat, lon, tags) VALUES (?,?,?,?,?)",
                    element_batch,
                )
                element_batch.clear()
            if name_batch:
                conn.executemany(
                    "INSERT INTO names(name, etype, id) VALUES (?,?,?)", name_batch
                )
                name_batch.clear()
            conn.commit()
            if progress is not None:
                progress(elements)

        try:
            processor = _osmium.FileProcessor(str(mirror_path)).with_filter(
                _osmium.filter.EmptyTagFilter()
            )
            for obj in processor:
                etype = _ETYPE_FROM_CODE[obj.type_str()]
                tags = {tag.k: tag.v for tag in obj.tags}
                lat, lon = (obj.lat, obj.lon) if etype == "node" else (None, None)
                element_batch.append((etype, obj.id, lat, lon, json.dumps(tags)))
                elements += 1
                name = _display_name(tags)
                if name is not None:
                    name_batch.append((name, etype, obj.id))
                    named += 1
                if len(element_batch) >= _BATCH_SIZE:
                    flush()
            flush()
        except RuntimeError as exc:
            raise MirrorCorrupt(f"{mirror_path}: {exc}") from exc

        # Merge the FTS index's write-side segments before first read: ~1,100
        # batch commits leave hundreds of unmerged b-tree segments, and every
        # MATCH walks all of them (measured: a two-token query on the Canada
        # extract ran >30s unmerged, sub-second after 'optimize').
        conn.execute("INSERT INTO names(names) VALUES ('optimize')")
        conn.executemany(
            "INSERT INTO meta(key, value) VALUES (?,?)",
            [
                ("builder", _BUILDER),
                ("source_size", str(mirror_path.stat().st_size)),
                ("source_replication_timestamp", replication_timestamp),
                ("elements", str(elements)),
                ("named", str(named)),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    os.replace(tmp_path, sidecar)
    return {"elements": elements, "named": named}


def _display_name(tags: dict[str, str]) -> str | None:
    for key in _NAME_TAGS:
        value = tags.get(key)
        if value:
            return value
    return None


def resolve_entry(handle: _Handle, native_id: str) -> AdapterResult:
    """Resolve `native_id` against the sidecar index. No redirects in OSM
    (unlike ZIM) — `canonical_id` is always the requested `native_id`.

    `text` is the stable quote-verification rendering: first line
    `"{etype} {id}"`; for nodes, then `"lat {lat:.7f}"` and `"lon
    {lon:.7f}"`; then one `"{key}={value}"` line per tag, sorted by key.
    Lines joined with `\\n`, no trailing newline."""
    etype, eid = _parse_native_id(native_id)
    conn = handle.connection()
    row = conn.execute(
        "SELECT lat, lon, tags FROM elements WHERE etype = ? AND id = ?", (etype, eid)
    ).fetchone()
    if row is None:
        raise EntryNotFound(
            f"no {etype} {eid} in {handle.mirror_path} "
            "(untagged elements are not indexed)"
        )
    lat, lon, tags_json = row
    tags: dict[str, str] = json.loads(tags_json)

    lines = [f"{etype} {eid}"]
    if etype == "node":
        lines.append(f"lat {lat:.7f}")
        lines.append(f"lon {lon:.7f}")
    lines.extend(f"{key}={tags[key]}" for key in sorted(tags))

    return AdapterResult(
        canonical_id=native_id,
        title=_display_name(tags),
        text="\n".join(lines),
        content_type="text/plain",
    )


def _parse_native_id(native_id: str) -> tuple[str, int]:
    match = _NATIVE_ID_RE.match(native_id)
    if match is None:
        raise EntryNotFound(
            f"{native_id!r} does not match the OSM native id grammar "
            "'{node|way|relation}/{decimal id}' (spec/ledger.md §6.5)"
        )
    return match.group(1), int(match.group(2))


_TOKEN_RE = re.compile(r"\w+")


def search_entries(
    handle: _Handle, query: str, limit: int, mode: str = "blend"
) -> list[AdapterSearchHit]:
    """Discovery step ahead of `resolve_entry` (spec/ledger.md §6.5): words
    in, candidate native ids out.

    OSM has exactly one indexed tier: display names (the sidecar `names`
    FTS5 table — the preference-chain name each element was given at index
    build time, `_display_name`). `"blend"` and `"suggest"` both search it
    identically (there is nothing to blend between, unlike ZIM's two
    independent indexes — kept as two mode names for interface symmetry with
    other adapters). `"fulltext"` — a search over tag values or geometry —
    is a legitimate absence for this format, not a missing index: it returns
    `[]` unconditionally, without even touching the sidecar (the format
    structurally has no such tier, distinct from a tier that exists but
    happens to be unbuilt). Any other `mode` is a caller bug, not a data
    condition — `ValueError`, matching the zim adapter's message shape.

    The query is tokenized defensively for FTS5 (`\\w+` word tokens, each
    double-quoted to neutralize FTS5 query-syntax characters, joined with
    implicit-AND spaces) — an empty token list (blank or punctuation-only
    query) is `[]`, not an FTS5 syntax error.

    Each hit additionally carries a `context` hint (`_search_context`) —
    first-scribe-pass finding: identically-titled hits (a common name
    repeated across a Geofabrik extract's whole province/country) are
    otherwise indistinguishable without resolving each one in turn; a
    classifying tag plus rough coordinates lets a scribe pick the right hit
    from the search results alone."""
    if mode not in ("blend", "suggest", "fulltext"):
        raise ValueError(f"unknown search mode {mode!r} (want 'blend', 'suggest', or 'fulltext')")
    if mode == "fulltext":
        return []

    tokens = _TOKEN_RE.findall(query)
    if not tokens:
        return []
    fts_query = " ".join(f'"{token}"' for token in tokens)

    conn = handle.connection()
    rows = conn.execute(
        "SELECT etype, id, name FROM names WHERE names MATCH ? ORDER BY bm25(names) LIMIT ?",
        (fts_query, limit),
    ).fetchall()
    return [
        AdapterSearchHit(
            native_id=f"{etype}/{eid}", title=name, context=_search_context(conn, etype, eid)
        )
        for etype, eid, name in rows
    ]


def _search_context(conn: sqlite3.Connection, etype: str, eid: int) -> str | None:
    """A short disambiguating hint for one search hit: `{key}={value}` for
    the first `_CONTEXT_TAGS` key present on the element, a `@{lat:.3f},
    {lon:.3f}` coordinate (~100 m — enough to tell provinces apart while
    keeping rows short) for nodes, joined with a single space — either part
    may be absent (a way with no classifying tag has no coordinates of its
    own; an element with no `_CONTEXT_TAGS` key has no classifying part).
    Both absent, or the element row missing (index inconsistency), is
    `None` — never a crash."""
    row = conn.execute(
        "SELECT lat, lon, tags FROM elements WHERE etype = ? AND id = ?", (etype, eid)
    ).fetchone()
    if row is None:
        return None
    lat, lon, tags_json = row
    tags: dict[str, str] = json.loads(tags_json)

    parts = []
    for key in _CONTEXT_TAGS:
        value = tags.get(key)
        if value:
            parts.append(f"{key}={value}")
            break
    if etype == "node" and lat is not None and lon is not None:
        parts.append(f"@{lat:.3f},{lon:.3f}")

    return " ".join(parts) if parts else None
