# ath-scan — the residence scanner

> Binary name `ath-scan` is **provisional** — rename to taste.

A standalone utility that runs **on a storage host** (the machine that owns a large
network share) and maintains a *presented manifest*: a continually-updated blake3 index of
every file on the share, written to a well-known directory on the share itself. With it, the
Athenaeum corpus tooling can treat a 300+TB read-only share as a self-describing,
content-addressed residence — resolving blake3 → path — **without ever walking or hashing it
over the wire**. A full hash pass over 10GbE is ~days per share; hashing has to live with the
bytes, so it does.

This is a prototype. It does the survey-and-present job and nothing else — no rclone, no
replication, no corpus-side integration. The one production-intent artifact here is
[`MANIFEST-SCHEMA.md`](./MANIFEST-SCHEMA.md), the cross-language contract the Python corpus
tooling reads.

## Design in one paragraph

Identity is keyed by the filesystem stat tuple `(device, inode, size, mtime_ns)` mapped to a
blake3 digest — git's index trick. blake3 is computed **once per content-version**; a
rename/move is a path-row update with zero re-hash; hardlinks collapse to one identity with
several paths; inode recycling is disarmed by `size`+`mtime_ns` in the tuple. The manifest is
two SQLite databases living on the share under `.athenaeum/`: `state.sqlite`, the scanner's
private working state (WAL mode), and `manifest.sqlite`, a checkpointed copy unveiled
atomically at the end of every successful run — the only file remote readers ever open. SQLite
gives indexed, on-disk lookups instead of replaying a full journal into memory, so JS memory
stays O(1) in tree size even on multi-million-file roots (see
[`MANIFEST-SCHEMA.md`](./MANIFEST-SCHEMA.md) for the schema and the full design rationale). A
cold pass hashes everything once; thereafter an incremental stat-walk re-hashes only new/changed
tuples, drops deleted paths, and (optionally) re-hashes a random sample to catch silent bit-rot.
Hashing is in-process via hash-wasm (the pipeline is disk-bound, so WASM's throughput is
sufficient and the embedded-binary hazards are avoided); the hasher sits behind a two-method
`update`/`digest` interface so a native binding remains a leaf swap. Everything on the share
except `.athenaeum/` is treated as strictly read-only.

## Install / build

Requires [Bun](https://bun.sh) (`bun:sqlite` is built in — no extra dependency, and it
compiles straight into the single-file binary). Run from source, or compile a self-contained
single-file binary (the Bun runtime is embedded; the host needs no Bun, no Node, no repo):

```bash
bun install
bun test                      # the suite
bun run build                 # -> dist/ath-scan          (linux x64)
bun run build:arm64           # -> dist/ath-scan-arm64     (linux arm64)
```

Drop `dist/ath-scan` on the share host and schedule it (systemd timer or unRAID User Scripts,
both below). hash-wasm bundles its WASM inside the JS and `bun:sqlite` is a native Bun
built-in, so the compiled binary is genuinely self-contained — no temp extraction, no
per-arch native blobs to manage separately, no noexec-mount hazard.

## Usage

```
ath-scan <root> [options]           incremental scan (first run on a root = cold full pass)
ath-scan <root> --bench             benchmark hash vs read throughput; write no manifest
ath-scan <root> --compact           drop orphaned identities, VACUUM, republish

  --full                 force a re-hash of every file (ignores the stat cache AND the
                         inode-migration heuristic — trust nothing, verify everything)
  --scrub <N>            re-hash N random files as a bit-rot check (mismatch => exit 2)
  --concurrency <K>      files hashed in parallel (default 4; spinning rust peaks at 2-4)
  --manifest-dir <path>  manifest location (default <root>/.athenaeum); use when the share
                         is read-only to the scanner user
  --json                 emit the run summary / bench result as JSON on stdout
  --quiet | --verbose    log level
  --version | --help
```

Exit codes:  0 ok   1 usage/error   2 scrub found corruption

The scanner reads content only under `<root>` and writes only under the manifest dir. Human
logs and progress go to stderr; the summary block (or `--json`) goes to stdout.

### What a run reports

```
scan summary — generation 7 (incremental)
  root          /srv/film
  files seen    124,003
  hashed        12  (48.20 GiB)
  moved         3
  migrated      0
  deleted       1
  skipped       0
  scrubbed      16   corrupt 0
  bytes hashed  48.20 GiB
  elapsed       0:03:12
  hash rate     0.86 GiB/s
```

`moved` counts path rows added that referenced an already-known identity via a *different*
path (renames and new hardlinks — zero re-hash). A rename shows as one `moved` + one
`deleted`. `migrated` counts the *same* path landing on a *new* inode at an unchanged
`(size, mtime_ns)` — the inode-migration heuristic (see below) — also zero re-hash.

## Interrupt-safety & resume

The cold pass on a real share runs for days. Identity rows (the expensive-to-redo work —
each one required an actual file read + hash) are committed in batches of at most 64 files
or 5 seconds, whichever comes first, so a `kill -9` mid-pass loses at most the in-flight
batch. Re-running simply resumes: the stat-walk re-classifies, finds the already-committed
tuples, and hashes only what's left — including re-hashing the handful of files from a lost
batch, never more. Publishing (`state.sqlite` → `manifest.sqlite`) only happens after a
generation closes successfully, so an interrupted run changes nothing a remote reader can
see; the previous complete generation stays published until the next one finishes. See
[`MANIFEST-SCHEMA.md`](./MANIFEST-SCHEMA.md) for the full publish protocol and generation
bookkeeping.

## Inode-migration heuristic

Some filesystems don't guarantee stable inodes across a remount even when the file itself
never moved — notably FUSE-backed union filesystems like unRAID's `shfs`, which backs
`/mnt/user/<share>/...`. When that happens, a naive stat-tuple scanner sees every file as
brand new and re-hashes the whole tree. `ath-scan` detects it instead: if a known path now
resolves to a new `(dev, ino)` but the size and mtime are byte-for-byte what the old identity
recorded, it carries the old blake3 forward with zero re-hash and counts it under `migrated`.
This is disabled under `--full`. See the "New in v2" section of
[`MANIFEST-SCHEMA.md`](./MANIFEST-SCHEMA.md) for the exact rule.

## systemd timer (generic host)

Cold pass once (foreground, may take days), then a periodic incremental with a light scrub:

```ini
# /etc/systemd/system/ath-scan-film.service
[Unit]
Description=ath-scan residence scan (film share)
[Service]
Type=oneshot
Nice=10
IOSchedulingClass=idle
ExecStart=/usr/local/bin/ath-scan /srv/film --concurrency 3 --scrub 200
```

```ini
# /etc/systemd/system/ath-scan-film.timer
[Unit]
Description=periodic ath-scan of the film share
[Timer]
OnCalendar=daily
Persistent=true
[Install]
WantedBy=timers.target
```

Compaction is cheap; run it weekly (`ExecStart=… --compact`) to keep `state.sqlite` and
`manifest.sqlite` tight.

## unRAID deployment

unRAID has no systemd unit files of its own to drop into (the OS partition doesn't persist
across reboots), so the usual pattern is:

1. **Binary on persistent storage.** Compile with `bun run build` and copy
   `dist/ath-scan` to somewhere under `/mnt/user/appdata/`, e.g.
   `/mnt/user/appdata/ath-scan/ath-scan` — anything under `/boot/config/` or `/mnt/user/`
   survives a reboot; `/usr/local/bin` on the OS partition does not.
2. **Schedule via the User Scripts plugin** (Community Applications → *User Scripts*). Create
   a script, e.g.:
   ```bash
   #!/bin/bash
   /mnt/user/appdata/ath-scan/ath-scan /mnt/user/film --concurrency 3 --scrub 100
   ```
   and set its cron schedule (User Scripts exposes this directly — daily overnight is
   typical for a large media share).
3. **Point it at the subtree that matters**, e.g. `/mnt/user/film` rather than all of
   `/mnt/user` — scope the scan the same way you'd scope any other maintenance job on the
   array.
4. **The inode-migration heuristic exists for exactly this deployment.** unRAID's `shfs`
   (the FUSE layer presenting `/mnt/user/...` as a union of the array's disks) does not
   guarantee an inode number survives an array start/stop, a disk rebuild, or certain
   config changes, even for a file that never moved or changed. Without the heuristic
   (see above), that would look like a whole-tree content change and trigger a full re-hash.
   `--full` still bypasses it, if you specifically want a verify-everything pass.

## Prototype boundaries / notes

- **Hashing is single-threaded.** `--concurrency K` overlaps file **reads** (async I/O) with
  hashing, which is the right lever on disk-bound spinning rust. It does **not** hash on K
  cores — hash-wasm's `update()` is synchronous JS. For an NVMe-backed residence where you
  want to saturate multiple cores, the pool must move to Bun `Worker` threads (each with its
  own WASM instance). The `update`/`digest` interface already isolates that change.
- **`--bench` read throughput is whatever the OS serves.** On a cache-warm tree it measures
  memory bandwidth, not disk; the true cold-share read rate is the first cold pass itself.
- **On-host, local filesystem only.** The `(dev,ino)` identity model needs real inodes; do
  not point this at an SMB/NFS mount (synthetic inodes) — `/mnt/user/...` on unRAID is a
  local FUSE mount and is fine (that's what the migration heuristic is for); a share mounted
  *from* another host over SMB/NFS is not.
- Scope is deliberately small: no replication, no routing, no corpus integration — those are
  later arc work. The manifest schema is the contract that outlives the prototype.
