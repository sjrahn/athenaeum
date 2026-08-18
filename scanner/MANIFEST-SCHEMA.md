# Presented-manifest schema — v2

This is the **cross-language contract** between the scanner (TypeScript, the writer) and the
Athenaeum corpus tooling (Python, the reader). The scanner writes it; nothing else does.
The corpus side reads the manifest through the share mount and never walks or hashes the
share itself. Treat this document as authoritative and version it: any incompatible change
bumps `schema` (`PRAGMA user_version`) and is recorded in the changelog at the bottom.

`SCHEMA_VERSION = 2`.

## Files

A manifest lives in one directory (`--manifest-dir`, default `<root>/.athenaeum/`):

| File | Role |
|---|---|
| `state.sqlite` (+ `-wal`/`-shm` sidecars) | The scanner's **private** working state. WAL mode. Remote readers MUST NOT open this — it can be mid-write, and its WAL sidecars are meaningless off the writer. |
| `manifest.sqlite` | The **published** manifest: a complete, checkpointed copy of `state.sqlite`, unveiled atomically (temp-then-rename) at the end of every successful generation. **This is the only file readers open.** |

Both are ordinary SQLite3 database files, single-main-file (no WAL sidecars — `manifest.sqlite`
is always checkpointed with `PRAGMA wal_checkpoint(TRUNCATE)` before it's copied, so it opens
cleanly read-only or standalone).

## The number-encoding rule (this replaces v1's)

v1 encoded `dev`/`ino`/`size`/`mtimeNs` as **decimal strings** because JSON numbers are
IEEE-754 doubles and `mtimeNs` (nanoseconds since epoch, ~1.7×10¹⁸) exceeds 2^53. SQLite has
no such ceiling — its `INTEGER` columns are true 64-bit signed integers, and 1.7×10¹⁸ fits
comfortably under 2^63 (~9.2×10¹⁸). **All four identity numerics are ordinary SQLite
`INTEGER` columns in schema v2.** Read them as 64-bit integers (Python `int` — unbounded,
no special handling needed; a JS reader must use `BigInt`, e.g. `bun:sqlite`'s
`safeIntegers: true` or `better-sqlite3`'s equivalent — a bare JS `number` truncates them).

One place still carries the v1 decimal-string convention: `generations.summary_json` and
`events.detail_json` are free-form JSON blobs (not SQL columns), so any large numeric field
embedded in them (`bytesHashed`, and `size`/`mtime_ns` inside a `scrub-corrupt` event's
detail) is still a decimal string — JSON's precision ceiling doesn't care what SQLite can
store natively.

## The identity model (unchanged from v1)

- An **identity** is one content-version of one inode, keyed by `(dev, ino)`. Its value is
  `(size, mtime_ns) → blake3`. There is at most one live identity per `(dev, ino)`; a content
  change (new `size` or `mtime_ns`) replaces it.
- A **path** maps a POSIX path (relative to the scanned root) to an identity `(dev, ino)`.
- **Hardlinks** are multiple paths sharing one `(dev, ino)` — one identity, several path
  rows, hashed once.
- **Renames/moves** change only the path row; the identity (and its `blake3`) is untouched
  and never re-hashed.
- **Inode recycling** (an inode number reused by a different file) is caught because the new
  file almost certainly has a different `size`/`mtime_ns`; the stat tuple mismatch forces a
  re-hash. The scrub sampler is the backstop against the astronomically-unlikely full-tuple
  collision and against silent bit-rot.

The scanner trusts `mtime_ns` as the change signal (every incremental backup tool's trade).
This is sound only because the scanner runs **on the share host against a local filesystem**
with real, stable inodes.

### New in v2: the inode-migration heuristic

Some filesystems the scanner runs against aren't quite "real, stable inodes" — notably
FUSE-backed union filesystems like unRAID's `shfs` (`/mnt/user/...`), where a remount or
array-config change can hand back a **different inode number for the same file** even though
the bytes and mtime are untouched. Treated naively, that looks like an entirely new,
never-seen file and forces a full re-hash of the whole tree.

The scanner detects this case during the walk: when a **known path** now resolves to a
**new** `(dev, ino)`, but the identity the path *used to* reference has an **exactly
matching** `(size, mtime_ns)`, the scanner writes a new identity row for the new `(dev, ino)`
carrying the **old** `blake3` forward — no re-hash. This is counted in `ScanSummary.migrated`
(distinct from `moved`, which is renames/hardlinks onto an *already-known* identity via a
*different* path). The heuristic is disabled under `--full`, which means "trust nothing,
re-hash everything." After a mass inode migration the old identity rows become orphans;
`--compact`'s orphan sweep drops them.

## Schema (identical on both databases)

```sql
PRAGMA user_version = 2;

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- keys: 'schema'='2', 'scanner'=<version that created this state.sqlite>,
--       'root'=<absolute scanned root, informational — paths are root-relative>,
--       'created_at'=<ISO-8601 UTC, set once at creation, never rewritten>

CREATE TABLE identities (
  dev INTEGER NOT NULL, ino INTEGER NOT NULL,
  size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
  blake3 TEXT NOT NULL, generation INTEGER NOT NULL,
  PRIMARY KEY (dev, ino)
) WITHOUT ROWID;
CREATE INDEX idx_identities_blake3 ON identities(blake3);

CREATE TABLE paths (
  path TEXT PRIMARY KEY, dev INTEGER NOT NULL, ino INTEGER NOT NULL,
  generation INTEGER NOT NULL
) WITHOUT ROWID;
CREATE INDEX idx_paths_identity ON paths(dev, ino);

CREATE TABLE generations (
  generation INTEGER PRIMARY KEY, mode TEXT NOT NULL, scanner TEXT NOT NULL,
  started_at TEXT NOT NULL, finished_at TEXT, summary_json TEXT
);

CREATE TABLE events (
  id INTEGER PRIMARY KEY, generation INTEGER NOT NULL, type TEXT NOT NULL,
  path TEXT NOT NULL, detail_json TEXT NOT NULL
);
```

### `meta`

Informational key/value pairs, written once when `state.sqlite` is created and never rewritten.

### `identities`

One row per live `(dev, ino)`. `blake3` is 64-character lowercase hex (BLAKE3-256).
`generation` is the generation that produced this content-version (the scan run, compaction,
or migration-carry that last wrote it).

### `paths`

One row per live path. `path` is POSIX, `/`-separated, relative to the scanned root.
`generation` is the generation that last wrote this mapping — it is **not** touched on scans
where the path's `(dev, ino)` didn't change (so a stable tree produces near-zero path writes
per incremental run; this is a performance property, not just bookkeeping).

### `generations`

One row per scan run or compaction. **A generation is complete iff `finished_at IS NOT
NULL`.** A row with `finished_at IS NULL` is an interrupted run — its identity/path rows up
to the last committed batch are still valid, it simply never finished, and it **stays NULL
forever** (the next run opens a *new* generation number rather than resuming the same one —
this NULL is the crash marker). `summary_json` is the `ScanSummary` JSON, set at close:
`{ mode, generation, filesSeen, hashed, moved, migrated, deleted, skipped, scrubbed, corrupt,
bytesHashed (decimal string), elapsedMs }`.

### `events`

Append-only audit trail; never mutates `identities` or `paths`. `type` is `'skip'` or
`'scrub-corrupt'`.

- `skip` — a file the scanner could not index (unreadable, or a special file —
  fifo/socket/device). `detail_json = { "reason": "eacces" | "eio" | "special-file" | ... }`
  (lowercased errno, or `"special-file"`). Symlinks are silently not-indexed and produce no
  skip event.
- `scrub-corrupt` — the scrub sampler re-hashed a file whose stat tuple was unchanged but
  whose content no longer matches the stored `blake3` — probable bit-rot or silent mutation.
  The run exits nonzero (2). The scanner does **not** auto-correct the identity row — that's
  a human/tooling decision.
  `detail_json = { "expected": <hex>, "actual": <hex>, "size": "<decimal string>",
  "mtime_ns": "<decimal string>", "detected_at": "<ISO-8601 UTC>" }`.

## Generation semantics

`generation` is a monotonically increasing integer, bumped once at the start of every
state-mutating operation (each scan run and each compaction). On open, the scanner's current
generation is `MAX(generation)` across `generations` (an interrupted generation still counts
— the next run becomes `generation + 1`, it does not retry the same number). Every
identity/path row carries the generation that wrote it.

## The publish protocol

`manifest.sqlite` is unveiled only after a **complete** generation:

1. `PRAGMA wal_checkpoint(TRUNCATE)` on `state.sqlite` — folds the WAL back into the main
   file and truncates it, so the main file alone is a complete, self-contained snapshot.
2. Copy `state.sqlite`'s bytes to `manifest.sqlite.tmp`.
3. `fsync` the copy, then `rename` it over `manifest.sqlite` (atomic on the same filesystem).
4. `fsync` the containing directory (best-effort — tolerated if unsupported).

A run that never reaches a successful `genClose` (killed mid-walk, mid-hash, or a scrub that
finds no corruption but the process dies before close) **publishes nothing** — the previous
`manifest.sqlite`, from the last complete generation, is left untouched. Any stale
`manifest.sqlite.tmp` from an interrupted publish is cleaned up the next time the scanner
opens the manifest dir.

Compaction (`--compact`) closes and publishes its own generation the same way — a compacted
tree is a normal complete generation, not a special case.

## Reader procedure (the corpus side)

1. Open `manifest.sqlite` **read-only**, or copy it to local storage first and open the copy
   — never open `state.sqlite`, and never write to `manifest.sqlite`.
2. Check `PRAGMA user_version` — must equal `2`. A mismatch means an incompatible schema; do
   not attempt to read it as v2.
3. Find the current generation: `SELECT MAX(generation) FROM generations WHERE finished_at IS
   NOT NULL`. Rows from a still-open (interrupted) generation may be present (they travel
   with the file since it's a whole-file copy) — ignore them; they represent a run that never
   completed on the writer side.
4. Resolve residence — path, size, mtime, blake3 — with the reader join:
   ```sql
   SELECT p.path, i.size, i.mtime_ns, i.blake3
   FROM paths p JOIN identities i ON p.dev = i.dev AND p.ino = i.ino
   ```
5. **Resolving a blake3 → paths** (promote-by-hash): `SELECT path FROM paths p JOIN
   identities i ON p.dev=i.dev AND p.ino=i.ino WHERE i.blake3 = ?` — the `idx_identities_blake3`
   index makes this an indexed lookup, not a table scan. An identity with zero referencing
   paths is stale (a deleted file not yet compacted away) and won't appear in this join.
6. **Comparing `mtime_ns` across an SMB mount**: if the reader is comparing timestamps it
   independently observed via SMB against `mtime_ns` in the manifest, compare at **100ns
   granularity**, not nanosecond — SMB carries NT time (100ns ticks since 1601), and the
   conversion to/from Unix nanoseconds is only exact to that resolution.

## Compaction & orphan sweep

`--compact`:

1. Delete identities referenced by zero live paths (orphans — deleted files not yet swept).
2. `VACUUM` (reclaims the space; SQLite's own housekeeping — no bespoke fold/reset step is
   needed, unlike v1's journal-into-snapshot rewrite).
3. Close and publish the compaction's own generation.

## Changelog

- **v2** (2026-08-18) — replaced the JSONL journal/snapshot pair with SQLite (`state.sqlite`
  private / `manifest.sqlite` published). Rationale: v1 required replaying the entire journal
  and snapshot into two in-memory `Map`s on every open — linear RAM and startup cost in tree
  size, which doesn't scale to multi-million-file share roots. SQLite gives indexed,
  on-disk lookups instead: O(1) JS memory regardless of tree size. This also killed the
  decimal-string-bigint rule for `dev`/`ino`/`size`/`mtime_ns` (native SQLite `INTEGER` is
  64-bit; JSON numbers aren't) and added the inode-migration heuristic (`migrated` in
  `ScanSummary`) for FUSE/shfs-style filesystems where inodes don't survive a remount.
  **v1 had zero deployed readers, so no migration path is provided** — a v1 manifest
  directory (`snapshot.jsonl` / `manifest.jsonl`) is simply incompatible; start a fresh cold
  pass with the v2 scanner.
- **v1** (2026-07-13) — initial schema: header / gen-open / gen-close / identity / path /
  path-delete / scrub-corrupt / skip; `(dev,ino,size,mtimeNs)` identity model; decimal-string
  encoding for the four identity numerics. Superseded by v2.
