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
an append-only JSONL journal plus a compacted snapshot, both living on the share under
`.athenaeum/`. A cold pass hashes everything once; thereafter an incremental stat-walk
re-hashes only new/changed tuples, drops deleted paths, and (optionally) re-hashes a random
sample to catch silent bit-rot. Hashing is in-process via hash-wasm (the pipeline is
disk-bound, so WASM's throughput is sufficient and the embedded-binary hazards are avoided);
the hasher sits behind a two-method `update`/`digest` interface so a native binding remains a
leaf swap. Everything on the share except `.athenaeum/` is treated as strictly read-only.

## Install / build

Requires [Bun](https://bun.sh). Run from source, or compile a self-contained single-file
binary (the Bun runtime is embedded; the host needs no Bun, no Node, no repo):

```bash
bun install
bun test                      # the suite
bun run build                 # -> dist/ath-scan          (linux x64)
bun run build:arm64           # -> dist/ath-scan-arm64     (linux arm64)
```

Drop `dist/ath-scan` on the share host and add a systemd timer (below). hash-wasm bundles its
WASM inside the JS, so the compiled binary is genuinely self-contained — no temp extraction,
no per-arch native blobs, no noexec-mount hazard.

## Usage

```
ath-scan <root> [options]           incremental scan (first run on a root = cold full pass)
ath-scan <root> --bench             benchmark hash vs read throughput; write no manifest
ath-scan <root> --compact           fold the journal into a fresh snapshot

  --full                 force a re-hash of every file (ignore the stat cache)
  --scrub <N>            re-hash N random files as a bit-rot check (mismatch => exit 2)
  --concurrency <K>      files hashed in parallel (default 4; spinning rust peaks at 2-4)
  --manifest-dir <path>  manifest location (default <root>/.athenaeum); use when the share
                         is read-only to the scanner user
  --json                 emit the run summary / bench result as JSON on stdout
  --quiet | --verbose    log level
  --version | --help

Exit codes:  0 ok   1 usage/error   2 scrub found corruption
```

The scanner reads content only under `<root>` and writes only under the manifest dir. Human
logs and progress go to stderr; the summary block (or `--json`) goes to stdout.

### What a run reports

```
scan summary — generation 7 (incremental)
  root          /srv/film
  files seen    124,003
  hashed        12  (48.20 GiB)
  moved         3
  deleted       1
  skipped       0
  scrubbed      16   corrupt 0
  bytes hashed  48.20 GiB
  elapsed       0:03:12
  hash rate     0.86 GiB/s
```

`moved` counts path rows added that referenced an already-known identity (renames and new
hardlinks — zero re-hash). A rename shows as one `moved` + one `deleted`.

## Interrupt-safety & resume

The cold pass on a real share runs for days. Identity rows are fsynced **per file**, so a
`kill -9` mid-pass loses at most the file being hashed. Re-running simply resumes: the
stat-walk re-classifies, finds the already-hashed tuples in the journal, and hashes only
what's left. Compaction is temp-then-`rename` (atomic) and ordered so a crash mid-compaction
leaves a consistent, replayable state either way.

## systemd timer (example)

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

Compaction is cheap; run it weekly (`ExecStart=… --compact`) to keep the journal small.

## Prototype boundaries / notes

- **Hashing is single-threaded.** `--concurrency K` overlaps file **reads** (async I/O) with
  hashing, which is the right lever on disk-bound spinning rust. It does **not** hash on K
  cores — hash-wasm's `update()` is synchronous JS. For an NVMe-backed residence where you
  want to saturate multiple cores, the pool must move to Bun `Worker` threads (each with its
  own WASM instance). The `update`/`digest` interface already isolates that change.
- **`--bench` read throughput is whatever the OS serves.** On a cache-warm tree it measures
  memory bandwidth, not disk; the true cold-share read rate is the first cold pass itself.
- **On-host, local filesystem only.** The `(dev,ino)` identity model needs real inodes; do
  not point this at an SMB/NFS mount (synthetic inodes).
- Scope is deliberately small: no replication, no routing, no corpus integration — those are
  later arc work. The manifest schema is the contract that outlives the prototype.
