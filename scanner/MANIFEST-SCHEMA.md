# Presented-manifest schema — v1

This is the **cross-language contract** between the scanner (TypeScript, the writer) and the
Athenaeum corpus tooling (Python, the reader). The scanner writes it; nothing else does.
The corpus side reads the manifest through the share mount and never walks or hashes the
share itself. Treat this document as authoritative and version it: any incompatible change
bumps `schema` and is recorded in the changelog at the bottom.

`SCHEMA_VERSION = 1`.

## Files

A manifest lives in one directory (`--manifest-dir`, default `<root>/.athenaeum/`):

| File | Role |
|---|---|
| `snapshot.jsonl` | Compacted base: the full live state as of the last compaction. Optional (absent until the first `--compact`). |
| `manifest.jsonl` | Append-only journal: every change since the snapshot. Always present. |

**To reconstruct state**: parse `snapshot.jsonl` (if present) first, then `manifest.jsonl`,
applying rows in file order. Later rows override earlier ones. This is the only correct read
procedure.

Both files are **JSON Lines** (JSONL): UTF-8, one JSON object per line, `\n`-terminated, no
trailing commas, no wrapping array. The last line of `manifest.jsonl` may be a partial write
from an interrupted append — a reader MUST tolerate a final unparseable line by discarding
it (the scanner does the same, and re-fsyncs whole rows, so at most the last line is torn).

## The number-encoding rule (read this first)

The four filesystem-identity numerics — **`dev`, `ino`, `size`, `mtimeNs`** — are encoded as
**decimal strings**, never JSON numbers. `mtimeNs` (nanoseconds since the Unix epoch) exceeds
2^53 and would silently lose precision as an IEEE-754 double, which is what JSON numbers are
in most parsers. Readers MUST parse these four fields as arbitrary-precision integers
(Python `int`, JavaScript `BigInt`). `blake3` is a 64-character lowercase hex string.
`generation`, `schema`, and counts are ordinary JSON integers (safe, small). Timestamps are
ISO-8601 UTC strings.

## The identity model

- An **identity** is one content-version of one inode, keyed by `(dev, ino)`. Its value is
  `(size, mtimeNs) → blake3`. There is at most one live identity per `(dev, ino)`; a content
  change (new `size` or `mtimeNs`) replaces it.
- A **path** maps a POSIX path (relative to the scanned root) to an identity `(dev, ino)`.
- **Hardlinks** are multiple paths sharing one `(dev, ino)` — one identity, several path
  rows, hashed once.
- **Renames/moves** change only the path row; the identity (and its `blake3`) is untouched
  and never re-hashed.
- **Inode recycling** (an inode number reused by a different file) is caught because the new
  file almost certainly has a different `size`/`mtimeNs`; the stat tuple mismatch forces a
  re-hash. The scrub sampler is the backstop against the astronomically-unlikely full-tuple
  collision and against silent bit-rot.

The scanner trusts `mtimeNs` as the change signal (every incremental backup tool's trade).
This is sound only because the scanner runs **on the share host against a local filesystem**
with real, stable inodes — through an SMB/NFS mount inodes are synthetic and this model does
not hold.

## Row types

Every row has a `"type"` field. Unknown row types MUST be ignored by readers (forward
compatibility). Fields not listed are not part of the contract.

### `header`
First line of every file, written once at file creation.

| field | type | meaning |
|---|---|---|
| `type` | `"header"` | |
| `schema` | int | schema version (`1`) |
| `scanner` | string | scanner version that created the file |
| `root` | string | absolute path of the scanned root (informational; paths are root-relative) |
| `kind` | `"journal"` \| `"snapshot"` | which file this is |
| `generation` | int | generation counter at file creation |
| `createdAt` | string | ISO-8601 UTC |

### `gen-open`  *(journal only)*
Opens a generation — one scan run or one compaction.

| field | type | meaning |
|---|---|---|
| `type` | `"gen-open"` | |
| `generation` | int | this run's generation |
| `mode` | `"cold"` \| `"incremental"` \| `"scrub"` \| `"compact"` \| `"bench"` | run kind |
| `scanner` | string | scanner version |
| `startedAt` | string | ISO-8601 UTC |

### `gen-close`  *(journal only)*
Closes a generation with its summary. **A generation is complete iff its `gen-close` is
present.** A journal ending in a `gen-open` with no matching `gen-close` is an interrupted
run; its identity/path rows are still valid (each was fsynced), it simply did not finish.

| field | type | meaning |
|---|---|---|
| `type` | `"gen-close"` | |
| `generation` | int | |
| `finishedAt` | string | ISO-8601 UTC |
| `summary` | object | the run summary (see below) |

`summary`: `{ mode, generation, filesSeen, hashed, moved, deleted, skipped, scrubbed,
corrupt, bytesHashed (decimal string), elapsedMs }`.

### `identity`
A content-version. Applying it sets the live identity for `(dev, ino)`.

| field | type | meaning |
|---|---|---|
| `type` | `"identity"` | |
| `dev` | decimal string | device id |
| `ino` | decimal string | inode number |
| `size` | decimal string | file size in bytes |
| `mtimeNs` | decimal string | mtime, ns since epoch |
| `blake3` | hex string (64) | BLAKE3-256 of the file content |
| `generation` | int | generation that produced this content-version |

### `path`
A path → identity mapping. Applying it sets `path`'s target to `(dev, ino)`.

| field | type | meaning |
|---|---|---|
| `type` | `"path"` | |
| `path` | string | POSIX, relative to root, `/`-separated |
| `dev` | decimal string | identity key it references |
| `ino` | decimal string | |
| `generation` | int | generation that last wrote this mapping |

### `path-delete`
The path no longer exists. Applying it removes the path.

| field | type | meaning |
|---|---|---|
| `type` | `"path-delete"` | |
| `path` | string | |
| `generation` | int | |

### `scrub-corrupt`
The scrub sampler re-hashed a file whose stat tuple was unchanged but whose content no longer
matches the stored `blake3` — probable bit-rot or silent mutation. Emitted loudly; the run
exits nonzero. The scanner does **not** auto-correct the identity row — a human/tooling
decision. This row is an event, not state (it does not change identities or paths).

| field | type | meaning |
|---|---|---|
| `type` | `"scrub-corrupt"` | |
| `path` | string | the path scrubbed |
| `dev`, `ino`, `size`, `mtimeNs` | decimal strings | the identity's tuple |
| `expected` | hex string | blake3 stored in the identity |
| `actual` | hex string | blake3 recomputed during scrub |
| `generation` | int | |
| `detectedAt` | string | ISO-8601 UTC |

### `skip`
A file the scanner could not index (unreadable, or a special file — fifo/socket/device).
An audit trail; not state. Symlinks are silently not-indexed and produce no `skip` row.

| field | type | meaning |
|---|---|---|
| `type` | `"skip"` | |
| `path` | string | POSIX relative |
| `reason` | string | lowercased errno (`"eacces"`, `"eio"`, …) or `"special-file"` |
| `generation` | int | |

## Apply semantics (the reader's state machine)

Maintain two maps: `identities: (dev,ino) → {size, mtimeNs, blake3, generation}` and
`paths: relpath → {dev, ino, generation}`. Then, in file order (snapshot then journal):

- `identity` → `identities[(dev,ino)] = {…}`
- `path` → `paths[relpath] = {dev, ino, …}`
- `path-delete` → delete `paths[relpath]`
- `header`, `gen-open`, `gen-close`, `scrub-corrupt`, `skip` → no state change (metadata/events)

Re-applying a row already reflected in the snapshot is idempotent, so replaying the journal
over the snapshot is always safe (this is what makes the compaction crash-window harmless).

**Resolving a blake3 → paths** (the corpus side's promote-by-hash): invert `identities` on
`blake3`, then collect every `relpath` in `paths` whose `(dev,ino)` matches. **An identity
with zero referencing paths is stale** (a deleted file not yet compacted away) and should be
ignored for residence purposes.

## Generation semantics

`generation` is a monotonically increasing integer, bumped once at the start of every
state-mutating operation (each scan run and each compaction). It is a logical clock:

- The current generation on load is the maximum `generation` seen across all rows.
- Every identity/path row carries the generation that wrote it, so a reader can tell how
  recently each fact was confirmed.
- The snapshot `header.generation` is the generation at which the snapshot was taken.

## Compaction & ordering rules

`--compact` folds the journal into a fresh snapshot:

1. Build live state from the current `snapshot.jsonl` + `manifest.jsonl`.
2. Write `snapshot.jsonl` = one `header` (`kind:"snapshot"`), then one `identity` row per
   **referenced** identity, then one `path` row per live path. **Identities with zero paths
   are dropped here** (orphan collection). Written temp-then-`rename` (atomic).
3. Reset `manifest.jsonl` to a single `header` (`kind:"journal"`), also temp-then-`rename`.

Ordering within a snapshot is not semantically significant (state is a set), but the scanner
emits identities before paths for readability. A crash between steps 2 and 3 leaves a
complete new snapshot and a still-old journal whose rows are all ≤ the snapshot generation
and already reflected in it — replay is idempotent, so the state is correct either way.

## Changelog

- **v1** (2026-07-13) — initial schema: header / gen-open / gen-close / identity / path /
  path-delete / scrub-corrupt / skip; `(dev,ino,size,mtimeNs)` identity model; decimal-string
  encoding for the four identity numerics.
