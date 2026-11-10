# ath-scan — the residence scanner

A standalone utility that runs **on a storage host** (the machine whose filesystem holds a large
share) and keeps a *published manifest* there: a continually updated BLAKE3 index of every file
on the share, written to `.athenaeum/` on the share itself. With it, `ath` treats the share as an
**observed tree** (spec/athenaeum.md §18.5): custody resolves BLAKE3 → path from the manifest
alone, **without ever walking or hashing the share over the wire**. A full hash pass over 10GbE
takes days per share; hashing has to live with the bytes, so it does.

The scanner is part of the `ath` workspace (`packages/scanner`) and ships as its own binary,
`ath-scan`. Its manifest is its own versioned contract, [`MANIFEST-SCHEMA.md`](./MANIFEST-SCHEMA.md);
`ath`'s custody reader (`packages/custody`, the observed-tree driver) is the reader it is kept
in step with. The scanner only surveys and publishes: copies, replication and policy are
custody's, on the instance side.

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
Hashing defaults to in-process hash-wasm behind a two-method `update`/`digest` interface — but
measured on the real deployment host that assumption inverted: WASM does ~58.77 MiB/s in-memory
against a ~159 MiB/s disk read path, i.e. the pipeline is **hash-bound**, not disk-bound. Files
at or above a size threshold (default 1 MiB) are routed instead to a discovered native `b3sum`
binary (multi-core via rayon) when one is available; see "Native b3sum hashing" below. Everything
on the share except `.athenaeum/` is treated as strictly read-only.

## Install / build

Requires [Bun](https://bun.sh) (`bun:sqlite` is built in — no extra dependency, and it
compiles straight into the single-file binary). It builds with the rest of the workspace, into a
self-contained single-file binary (the Bun runtime is embedded; the host needs no Bun, no Node,
no repo):

```bash
cd ath
bun install
bun test packages/scanner     # the scanner's suite
bun run build                 # -> dist/ath, dist/ath-scan                (linux x64)
bun run build:arm64           # -> dist/ath-arm64, dist/ath-scan-arm64    (linux arm64)
```

`ath-scan --version` names the scanner's version and the manifest schema it writes; every
generation records that version in the manifest. Drop `dist/ath-scan` on the share host, a
native `b3sum` beside it (see "Native b3sum hashing"), and schedule it (systemd timer or unRAID
User Scripts, both below). hash-wasm bundles its WASM inside the JS and `bun:sqlite` is a native Bun
built-in, so the compiled binary is genuinely self-contained — no temp extraction, no
per-arch native blobs to manage separately, no noexec-mount hazard.

## Usage

```
ath-scan <root> [options]           incremental scan (first run on a root = cold full pass)
ath-scan <root> --bench             benchmark hash vs read throughput; write no manifest
ath-scan <root> --compact           drop orphaned identities, VACUUM, republish
ath-scan <root> --paths-from <file|->  targeted update of the listed paths (see below)
ath-scan <root> --dry-run [...]     what the run would hash, move and delete; writes nothing
ath-scan <root> --publish           publish generations recorded with --no-publish
ath-scan <root> --testimony <path>  what the published manifest observed of one file, as testimony

  --full                 force a re-hash of every file (ignores the stat cache, the
                         inode-migration heuristic, AND all seeding — trust nothing, verify
                         everything)
  --scrub <N>            re-hash N random files as a bit-rot check (mismatch => exit 2)
  --concurrency <K>      files hashed in parallel (default 4; spinning rust peaks at 2-4)
  --manifest-dir <path>  manifest location (default <root>/.athenaeum); use when the share
                         is read-only to the scanner user
  --seed-from <path>     adopt identities from another manifest.sqlite before scanning (a
                         file path, or a directory holding .athenaeum/manifest.sqlite);
                         repeatable; errors combined with --full
  --b3sum <path>         native b3sum binary for large files (default: auto-discover one
                         beside this executable, then on PATH; WASM-only if none verifies)
  --native-threshold <bytes>  files at/above this size use native b3sum instead of WASM,
                         when one is available (default 1048576, i.e. 1 MiB)
  --native-concurrency <K>  concurrent native b3sum spawns (default 2); multi-disk arrays
                         (e.g. unRAID) benefit from 4-8 since each hasher pins one spindle;
                         b3sum is itself CPU-multithreaded, so a pure-NVMe root rarely needs
                         more than 2
  --ignore <pattern>     extra basename to skip (repeatable); trailing "*" is a prefix match;
                         layers on top of the built-in junk deny-list — see "Ignoring
                         filesystem-metadata junk" below
  --no-default-ignores   drop the built-in deny-list; --ignore patterns still apply
  --exclude <glob>       a path relative to the root to leave out (repeatable) — see "Path
                         excludes" below
  --no-publish           record the generation in the state without publishing it
  --max-delete <pct>     the deletion limit (default 5%, past 100 paths) — see below
  --allow-deletions      let this run past the deletion limit
  --status-file <path>   keep the run's progress as JSON in <path> — see below
  --json                 emit the run summary / bench result as JSON on stdout
  --quiet | --verbose    log level
  --version | --help
```

Exit codes:

| code | meaning |
|---|---|
| 0 | ok; for a dry run, the run would be accepted |
| 1 | usage or error |
| 2 | the scrub found corruption (the generation is still recorded and published) |
| 3 | the deletion limit refused the generation and nothing was written; for a dry run, it would refuse |
| 4 | another scan holds this manifest (the run lock); nothing was done |

The scanner reads content only under `<root>` and writes only under the manifest dir. Human
logs and progress go to stderr; the summary block (or `--json`) goes to stdout.

### What a run reports

```
scan summary — generation 7 (incremental)
  root          /srv/film
  files seen    124,003
  hashed        12  (48.20 GiB)
  hashed native 9
  moved         3
  migrated      0
  seeded        0
  deleted       1
  skipped       0
  ignored       39
  scrubbed      16   corrupt 0
  sniffed       11
  bytes hashed  48.20 GiB
  elapsed       0:03:12
  hash rate     0.86 GiB/s
```

`moved` counts path rows added that referenced an already-known identity via a *different*
path (renames and new hardlinks — zero re-hash). A rename shows as one `moved` + one
`deleted`. `migrated` counts the *same* path landing on a *new* inode at an unchanged
`(size, mtime_ns)` — the inode-migration heuristic (see below) — also zero re-hash. `seeded`
counts identity rows adopted from another manifest this run — a nested child root's manifest
(auto-detected) or an explicit `--seed-from` source — see "Manifest seeding" below. `hashed
native` is the subset of `hashed` that went through native b3sum rather than WASM — see
"Native b3sum hashing" below. `ignored` counts files and pruned directories skipped by the
junk deny-list this walk — see "Ignoring filesystem-metadata junk" below. `sniffed` counts
`mime_claim` values written this run (new files plus backfilled pre-existing ones) — see
"Catalog metadata" below.

## Following a share as it changes

A full walk stats every file. To keep a manifest current between walks, a wrapper that watches the
share (inotify, on unRAID the backing `/mnt/diskN` and pool mounts, each path mapped to its
`/mnt/user/<share>` path) hands the scanner what changed:

```bash
printf '%s\n' film/new.mkv film/old-name.mkv film/renamed-dir | \
  ath-scan /mnt/user/media --paths-from - --no-publish
```

- **Targeted runs** (`--paths-from <file|->`, one path per line relative to the root) classify
  only the listed paths: a file as it is now, a directory as a whole subtree (a renamed or
  removed directory is one event, not one per file), and a path that is gone deletes its rows
  and every row under it. List both sides of a rename. A targeted run is a generation of its
  own (mode `targeted`) and needs a manifest a full walk began. It does everything else as a
  full walk does: excludes, ignores, the deletion limit, hashing, `--scrub` — and, as there, a
  listed path it cannot read (a permissions error) counts under `skipped` and its rows go.
- **A refused batch stays refused.** When the deletion limit refuses a targeted run (exit 3,
  the counts in `--json`), nothing of it is recorded and a later full walk sees the same
  deletions. Keep the batch, show the counts, and run it again with `--allow-deletions` once
  they are confirmed real.
- **The state lives on the share.** `state.sqlite` is in `<root>/.athenaeum/`, on whichever disk
  holds that directory; every targeted run writes it and every publish writes the manifest
  beside it, so that disk stays spun up while updates flow. Readers find the manifest only
  there.
- **Publishing is separate.** A publish copies the whole state database to `manifest.sqlite`
  (a few hundred MB per million files) and every reader re-reads it, so publish on a slower
  clock than you update: run targeted updates with `--no-publish`, and `ath-scan <root>
  --publish` every hour or so; it publishes only when the state finished a generation the
  manifest lacks.
- **A periodic full walk stays** as the net for missed events (with the directory cache warm,
  it touches no platter where nothing changed).
- **The run lock** (`<manifest dir>/scan.lock`) lets one run write a manifest's state at a time;
  a second exits 4 at once, and the wrapper retries later. A lock left by a process that is
  gone is taken over.

## The deletion limit

A walk that cannot see part of the tree reads it as deleted — a disk dropping out of a union
mount, an unmounted share, a directory gone unreadable. Before the walk commits, a generation
that would delete more than 5% of the paths the manifest held (once that is more than 100
paths) is refused: nothing of the walk is written, the published manifest stays as it was, and
the scanner exits 3. `--max-delete <pct>` sets the share; `--allow-deletions` lets one run
through after you have checked the deletions are real. A newly excluded subtree reads as
deletions too.

## Dry runs

`--dry-run` walks and classifies as the run would (full or targeted, seeds included), reports
how many files it would hash, move, migrate and delete and whether the deletion limit would
refuse it, and abandons everything — nothing is hashed, written (beyond upgrading a v2 state to
v3 in place and recording the host on a state that lacks it) or published, and no file's bytes
are read. It is the preflight for adopting an
earlier manifest: `toHash` near zero means its hashes carry over. Exit 0 if the run would be
accepted, 3 if the limit would refuse it.

## Path excludes

`--exclude <glob>` (repeatable) leaves out paths by their path relative to the root, beside the
basename deny-list below. A pattern names files or directories, and a matched directory is
pruned, never entered. A trailing `/` (or `/**`) makes it name directories only. `*` stays
within one path segment, `**` crosses them:

| pattern | leaves out |
|---|---|
| `downloads/` | the root's `downloads` directory |
| `**/incomplete/` | every directory named `incomplete` |
| `**/*.part` | every `*.part` file |
| `*.tmp` | `*.tmp` files at the root only |

Full and targeted runs honour the same excludes, so pass the same ones to both. What a walk
indexed before a pattern was added reconciles away as deletions.

## Status file

`--status-file <path>` keeps one JSON object describing the run, rewritten whole (temp, then
rename) every couple of seconds and at each change of phase. Put it on a RAM filesystem
(`/var/log` on unRAID) so a status page never wakes a disk. Every field is present from the
first write:

```json
{
  "root": "/mnt/user/film",
  "phase": "hash",
  "mode": "incremental",
  "generation": 42,
  "dryRun": false,
  "pid": 12345,
  "host": "farspark",
  "started_at": "2026-11-10T01:22:45.282Z",
  "updated_at": "2026-11-10T03:10:02.913Z",
  "filesSeen": 1250311,
  "toHash": 812,
  "bytesToHash": "96412844032",
  "hashed": 304,
  "bytesHashed": "35123118080",
  "published": false,
  "summary": null,
  "error": null
}
```

| field | |
|---|---|
| `phase` | `walk` · `hash` · `scrub` · `publish` · `done` · `refused` (the deletion limit) · `failed` |
| `mode` | `cold` · `incremental` · `targeted` (null until the run has opened the manifest) |
| `generation` | the generation the run writes (null as for `mode`) |
| `dryRun` | true for `--dry-run` |
| `pid`, `host`, `started_at`, `updated_at` | the process, and when it started and last wrote the file (ISO 8601 UTC); a `pid` gone with `phase` not `done`/`refused`/`failed` is a run that died |
| `filesSeen`, `toHash` | files the walk has classified, and how many of them need hashing |
| `bytesToHash`, `bytesHashed` | byte counts as decimal strings (they can pass 2^53) |
| `hashed` | files hashed so far |
| `published` | whether the finished generation was published (false under `--no-publish`) |
| `summary` | at `done`: the run summary (`--json`'s object), or a dry run's report |
| `error` | at `refused` or `failed`: the message |

Fields may be added; none is removed or renamed without a note in this section. The run
summary of a finished generation is also `--json` on stdout and `generations.summary_json` in
the manifest.

## Ignoring filesystem-metadata junk

The walk skips a small, **curated positive list** of filesystem-metadata basenames — it does
**not** blanket-skip hidden dotfiles, since many dotfiles (`.config`, `.gitignore`, ...) are
wanted content, not junk. Motivating incident: an unRAID share accumulated 37 macOS
AppleDouble `._*` sidecar files and 2 `.__*`-style lock files; Samba vetoes `._*` over SMB, so
once indexed those rows are permanently unreachable ("stale") from any SMB-mounted reader.

The default deny-list (basename match; a matched directory is **pruned** — its subtree is
never entered):

```
.DS_Store   ._*   .AppleDouble   .AppleDesktop   .TemporaryItems   .Trashes
.Spotlight-V100   .fseventsd   .DocumentRevisions-V100   Thumbs.db   desktop.ini
@eaDir   .@__thumb
```

`._*` deliberately also catches `.__*`-style lock names, matching Samba's own veto behavior.
A pattern ending in `*` is a prefix match; every other entry is an exact basename match.

- `--ignore <pattern>` (repeatable) adds more basenames/prefixes on top of the defaults.
- `--no-default-ignores` drops the built-in list entirely; any `--ignore` patterns given still
  apply on top of nothing.

A file or directory matched by the deny-list is **never marked seen** for this walk — so a
junk row indexed by an earlier run (before the list existed, or before a `--ignore` addition)
reconciles away as an ordinary deletion on the next scan, with no special-case cleanup.

## Manifest seeding: subdir scanned first, root scanned later

Each scan root owns its own `.athenaeum/` manifest, keyed by the filesystem's own `(dev, ino)`
identity — which is root-independent. That means a **parent** root scanned later can adopt a
**child** subdirectory's already-computed hashes wholesale, as long as the files haven't
changed since the child was scanned (the usual stat-tuple check still applies and disposes
over a stale claim). This matters for a share that gets scanned bottom-up over time — e.g. a
fast NVMe cache scanned as its own root today, later folded into a scan of the slower array
it lands on.

**Nested `.athenaeum` is never content.** Any directory literally named `.athenaeum`, at any
depth, is excluded from the walk unconditionally — never descended into, never yielded as a
path, never hashed — regardless of `--full`. Manifest directories are infrastructure, never
indexed as content.

**Auto-seed (default).** When the walk lists a directory that itself has a `.athenaeum`
subdirectory with a published `manifest.sqlite` — i.e. that directory is itself a previously
scanned root — the scanner imports its identities and paths into its own state *before*
classifying any file at or below that directory. Existing rows always win (`INSERT OR
IGNORE`); a file that changed since the child's scan is caught by the ordinary stat-tuple
check and re-hashed normally. The run's `seeded` count reports how many identity rows were
adopted this way. **Disabled entirely under `--full`** (logged at debug level) — the
unconditional `.athenaeum` exclusion still applies, so nothing under a nested manifest dir is
ever indexed as content, but its sibling files get re-hashed like everything else under
`--full`.

**`--seed-from <path>` (explicit, repeatable).** Point a scan at another manifest.sqlite
directly — a file path, or a directory containing `.athenaeum/manifest.sqlite` — to seed from
it before the walk starts, regardless of whether it's nested under the current root. Typical
use: you're re-running a scan under a new `--manifest-dir`, or against a portable copy of a
tree elsewhere with the same relative layout, and want to avoid a full re-hash. Give it
multiple times to seed from more than one source. Combining `--seed-from` with `--full` is a
usage error (full means ignore every cache, including seeds); a nonexistent path is a hard
error, as is a source manifest whose schema version doesn't match (an operator named this
file explicitly, so a mismatch fails loudly rather than silently skipping). Auto-seed treats
the same mismatch more gently — it warns and skips that one manifest, since a big scan
touching many nested roots must not die over one stale child.

## Native b3sum hashing

Measured on the real deployment host (12900H): hash-wasm does ~58.77 MiB/s hashing in memory,
while the disk read path does ~159 MiB/s — the pipeline is **hash-bound**, inverting the
original disk-bound assumption. Fix: files at/above `--native-threshold` (default 1 MiB) are
hashed by spawning a real `b3sum` binary instead — real b3sum is multi-core (rayon), so it can
comfortably out-run both WASM and the disk. Small files stay on WASM (spawn overhead isn't
worth it below the threshold), and the whole feature degrades gracefully to WASM-only if no
b3sum is available or it fails verification — this is opt-in-by-availability, not opt-in-by-flag.

**Deployment**: download the official static `b3sum` release binary (from the
[BLAKE3 releases](https://github.com/BLAKE3-team/BLAKE3/releases)) and drop it beside
`dist/ath-scan` on the share host — discovery checks a file literally named `b3sum` in the
same directory as the running executable before falling through to PATH. `--b3sum <path>`
overrides discovery entirely.

**Verification**: a discovered binary is checked once at startup — `b3sum --version` must
exit 0, and it must reproduce hash-wasm's BLAKE3 digest of a small known vector (written to a
temp file). Either check failing refuses the binary with a warning and falls back to WASM —
this never aborts a run over a bad/wrong/missing b3sum.

**Concurrency**: b3sum is internally multithreaded, so on a pure-NVMe/SSD root spawning
several at once just makes them contend for the same cores instead of helping — native
hashing defaults to 2 concurrent spawns, independent of `--concurrency` (which still governs
the WASM pool for small files, run concurrently alongside the native pool). On a multi-disk
array where each file lives wholly on one physical disk (e.g. unRAID's file-based array),
that default leaves throughput on the table: one b3sum stream tops out at one spindle's read
speed, so aggregate throughput scales with how many *distinct disks* are being read from at
once, not with CPU. `--native-concurrency <K>` raises the pool size — 4-8 is a reasonable
starting point on such arrays. The native queue is also shuffled before pooling, since
unRAID's allocation policy tends to place a whole directory's files on the same disk and the
queue is built in walk (directory) order — without shuffling, adjacent queue entries would
likely be same-disk and a bigger pool would just contend harder rather than fanning out.

**Per-file failures** (nonzero exit, bad output, a file that vanishes mid-hash) are logged and
skipped the same way an unreadable file is — reason `b3sum-failed` — never abort the run.

## Catalog metadata

Schema v3 grows the manifest from a residence map into a **light catalog** (spec/athenaeum.md §18.5): four nullable columns on `identities` — `ctime_ns`, `btime_ns`, `mode`,
`mime_claim` — so format-and-placement questions are answerable straight from the manifest,
without a reader touching bytes over the wire. See
[`MANIFEST-SCHEMA.md`](./MANIFEST-SCHEMA.md)'s "Catalog metadata (v3)" section for the
column-by-column contract; this is the operator-facing summary.

**What's captured, and when**: the three stat facts come from the walk's existing `lstat` —
free, since it already stats every file. They're written when a new identity is hashed, and
**refreshed** on every later walk for a known, unchanged identity whenever they've drifted
(a `chmod` is the common case: it changes `ctime`/`mode` but not `mtime`, so it costs zero
re-hashes) or are still NULL. `mime_claim` is sniffed from the leading bytes (capped at 16
KiB) once per new identity — free on the WASM hash path (piggybacked on the first chunk
already being read), one small extra bounded read on the native b3sum path (which otherwise
never touches the bytes itself in-process). A pre-v3 tree gets caught up gradually: any known
identity whose `mime_claim` is still NULL gets sniffed (and written) the next time its path is
walked, no re-hash — the `sniffed` summary field counts these.

**Why `atime` is excluded**: access time is the one stat field that changes on a *read*, not a
write — capturing it would make every scan (which reads every new/changed file to hash it, and
every scrubbed file to verify it) perturb the very metadata it's recording, and many
filesystems mount with `relatime`/`noatime` anyway, making it unreliable as a signal even when
present. `ctime`/`btime`/`mode` don't have that problem: nothing in a normal scan run touches
them.

**The sniffer is deliberately coarse**, by design (`src/sniff.ts`): magic bytes first (JPEG,
PNG, GIF, WebP, WAV, AVI, BMP, TIFF, HEIC/HEIF, MP4/M4A/M4V/MOV, MKV/WebM, MP3, FLAC, OGG, PDF,
ZIP, gzip, xz, zstd, 7z, RAR, tar, SQLite3), then a small extension fallback for text-ish
formats magic can't settle (`.srt`, `.json`, `.csv`, `.md`), then a last-resort "looks like
UTF-8/ASCII text" heuristic, else `null`. A ZIP is always `application/zip` — this never opens
the archive to guess `.docx`/`.xlsx`/etc from its members. **`mime_claim` is advisory, not
authoritative** — `ath`'s own content-based format detection (spec §10.1) is the one thing that gets
to decide what a file actually is; nothing normative may ever depend on this claim. Treat it
as a cheap first filter, never a verdict.

## Non-TTY progress heartbeat

Piped to a file, over plain ssh, or run from cron/User Scripts, stderr isn't a TTY, so the
`\r`-rewrite progress ticker (meaningless without a terminal) is replaced with plain,
newline-terminated heartbeat lines — otherwise a multi-day cold pass's log would go completely
silent between "walk done" and the final summary. The walk prints one every 2,000 files and at
least every 30 seconds however few files it has reached, so a slow stat-walk over cold
directories never looks hung. Cadence: one line
every 16 hashed files, with a 1-second minimum spacing between lines (so a burst of tiny files
crossing that boundary rapidly doesn't flood a cron log), and a 30-second time floor so a
stretch of huge files (hashed count not advancing for a long time) still heartbeats. TTY
behavior (the `\r` rewrite, once a second) is unchanged.

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

`journalctl -u ath-scan-film` stays observable during a long run: stderr isn't a TTY under
systemd, so progress prints as rate-limited plain lines rather than the `\r`-rewrite ticker
(see "Non-TTY progress heartbeat" above) — no more silence between "walk done" and the summary.

## unRAID deployment

unRAID has no systemd unit files of its own to drop into (the OS partition doesn't persist
across reboots), so:

1. **Binary on persistent storage.** `dist/ath-scan` and a static `b3sum` side by side under
   `/boot/config/…` (the flash drive) or `/mnt/user/appdata/ath-scan/` — both survive a
   reboot; `/usr/local/bin` on the OS partition does not. `appdata` usually lives on the cache
   pool, so running the binary from there wakes no array disk.
2. **Scan user shares, with the direct byte path.** Point it at `/mnt/user/<share>` with
   `--byte-path unraid` (below): the walk, the identities and every path come from the share
   view — the names the instance will use — while hashing reads go straight to the backing
   `/mnt/diskN`. Do **not** scan `/mnt/diskN` roots: their paths are not the share's, and the
   mover or unbalance relocating a file between disks would read as a deletion and a new file.
   One root, and so one manifest, per share that matters, rather than all of `/mnt/user`.
3. **Schedule via the User Scripts plugin** (Community Applications → *User Scripts*), e.g.:
   ```bash
   #!/bin/bash
   mkdir -p /var/log/ath-scan
   /mnt/user/appdata/ath-scan/ath-scan /mnt/user/film --byte-path unraid \
     --native-concurrency 2 --scrub 50 --status-file /var/log/ath-scan/film.status.json \
     --json > /var/log/ath-scan/film.json
   ```
   User Scripts' log view is a plain (non-TTY) pipe, so it gets the rate-limited heartbeat
   lines on stderr rather than a silent multi-day gap; the run summary goes to stdout (`--json`
   for a machine-readable one) and the progress to the status file. `/var/log` is in RAM on
   unRAID, so a status page that reads them wakes no disk. Between full walks, a watcher hands
   targeted updates over (see "Following a share as it changes").
4. **Load and heat.** There is no bandwidth limit; the levers are how many files are read at
   once. `--byte-path unraid` sizes the native (b3sum) pool to the number of disks with work
   queued, up to 8; set `--native-concurrency 1`–`2` explicitly to keep a hot shelf cool, and
   `--concurrency` (default 4) bounds the small-file pool. The pool spreads reads across disks
   (fewest active readers first); it does not work through one disk at a time.
5. **Parity checks and a degraded array.** The scanner does not look for either. Have the
   wrapper skip a run while a check is in progress or a disk is missing, or stop the scan when
   one starts: an interrupted run publishes nothing and the next resumes per file (see
   "Interrupt-safety & resume"). The deletion limit is the last line: a walk that cannot see a
   disk's files is refused before it writes (exit 3).
6. **Spin-down and cadence.** An incremental run walks the whole tree and `lstat`s every file
   through `shfs`; any directory or inode the kernel no longer caches is read from its disk,
   which spins it up — so a run wakes every disk under the share unless their metadata stays
   cached. The *Dynamix Cache Directories* plugin (`cache_dirs`) keeps it in RAM; then an
   incremental walk over unchanged files touches no platter and only new or changed files are
   read. Without it, run weekly per share, staggered, outside parity windows; with it, daily
   overnight is fine. `--scrub N` re-reads N random files each run and wakes their disks: keep
   it small, or scrub on the weekly run only. A cold pass takes days per share; run them one
   share at a time.
7. **The inode-migration heuristic exists for exactly this deployment.** `shfs` (the FUSE layer
   presenting `/mnt/user/...` as a union of the array's disks) does not guarantee an inode
   number survives an array start/stop, a disk rebuild, or certain config changes, even for a
   file that never moved or changed. Without the heuristic (see above), that would look like a
   whole-tree content change and trigger a full re-hash. `--full` still bypasses it, if you
   specifically want a verify-everything pass.

**Earlier manifests.** A scan picks up the `state.sqlite` an earlier run left under the same
manifest directory and resumes from it: a schema-v2 state (scanner 0.2.x) is migrated to v3 in
place, a v3 one is used as it is, and one begun before the manifest recorded its host gains it
on that run. A v1 manifest (scanner 0.1, the `snapshot.jsonl`/`manifest.jsonl` pair) has no
migration: start a cold pass. An interrupted cold pass has published nothing yet: what it
hashed lives only in `state.sqlite`, so leave that file where it is (copy it only while no scan
runs). A `--dry-run` first says how much of it carries over. A manifest
under another directory is adopted with `--seed-from`, which imports its identities and its
paths unchanged: a file keeps its hash when its `(dev, ino, size, mtime)` still matches, or when
its path matches with the same size and mtime. Seeding a share's root from a scan of a
*parent* root (`/mnt/user` whole) therefore carries hashes over by inode only, which `shfs`
does not keep across an array restart; keep the roots the earlier scans used where you can.
`--byte-path` changes only where hashing reads come from, never the manifest, so runs with and
without it mix freely.

**The instance side.** `ath` reads an observed tree by path: the host running `ath` (and
`athd`) mounts each share — read-only is enough — and declares it once, which writes the
store's id to `<share>/.athenaeum/store.yaml` (the one write, so that mount, or a hand-placed
file, must allow it):

```bash
ath store add film --role observed --path /mnt/farspark/film
```

Custody opens `.athenaeum/manifest.sqlite` read-only through the mount (NFS is the safer of the
two network filesystems for SQLite; the published file is never written in place, only
replaced whole), `ath custody inventory film` brings it into the host's index, and `athd`
re-inventories when it sees a new generation. `ath custody where <blake3>` and
`ath custody report film` answer from the index; ingest and resolve read a file's bytes through
the mount. Never point the scanner itself at a network mount (see below).

## unRAID direct byte path

`/mnt/user/<share>` is `shfs`, a FUSE union of the array's disks — convenient, but it caps
*aggregate* read throughput well below what the underlying disks can do individually (measured
on the real deployment host: ~130 MiB/s through shfs, regardless of how many disks are actually
involved). `--byte-path unraid` bypasses FUSE for the hashing reads themselves, while changing
nothing else: **the share view is the truth.** The walk, identity (`dev`/`ino` from the
share-side `lstat`), paths, and every published manifest field are still derived from
`/mnt/user/...`, exactly as without the flag — the manifest a direct-path scan produces is
byte-identical to one from a plain scan of the same tree. The only thing that changes is *where
the bytes for hashing come from*.

**How it works**: unRAID tags every file with a `system.LOCATION` xattr naming its backing
storage element — a disk (`disk7`) or a cache/pool name (`warm`). The real bytes live at
`/mnt/<element>/<path relative to /mnt/user/>`. For each file about to be hashed, the scanner
reads that xattr, computes the candidate backing path, and `lstat`s it: only if `size` **and**
`mtime_ns` match the share-side stat *exactly* does it trust the backing path and read from
there (`directReads` in the summary); any mismatch, or an xattr/`lstat` failure, falls back to
the ordinary share-path read (`directFallbacks`). This applies uniformly to the in-process WASM
hasher, the native b3sum path, and scrub re-reads.

**Mover-race safety**: the unRAID mover can relocate a file between disks at any time, including
between this scanner's pin-verify `lstat` and the read that follows it. If a direct-path read
fails mid-flight (a nonzero b3sum exit, a read error) after the pin verified, the scanner
retries **once**, against the share path, before falling into the ordinary per-file skip
handling — so a mover race costs one extra read, never a wrongly-skipped or wrongly-hashed file.

**Disk-aware native scheduling**: with a resolver active, the native (b3sum) queue is no longer
just shuffled — each file's element is resolved at enqueue time and the pool always pulls the
next file from whichever element currently has the fewest active readers, so K workers
naturally fan out across up to K distinct disks instead of piling onto whichever file happened
to be shuffled first. Files whose element couldn't be resolved land in an unordered bucket read
via the share path.

**Auto concurrency**: when `--byte-path unraid` is active and `--native-concurrency` is *not*
given explicitly, the native pool size defaults to `min(max(distinct disk elements with queued
native work, 2), 8)` instead of the fixed default of 2 — since direct reads fan out across real
spindles rather than contending on `shfs`. Pass `--native-concurrency` explicitly to override.

```bash
ath-scan /mnt/user/film --byte-path unraid --scrub 100
```

Usage: only `unraid` is a valid `--byte-path` value; the root must be under `/mnt/user/` (an
operator error there is a startup error, not a silent no-op). A run using it logs one line up
front — `direct byte path: unraid` — and the end-of-scan summary gains two lines (`direct
reads`, `direct fallbacks`) whenever a resolver was active.

## Boundaries and notes

- **WASM hashing is single-threaded.** `--concurrency K` overlaps file **reads** (async I/O)
  with hashing, which is the right lever on disk-bound spinning rust, but doesn't hash on K
  cores — hash-wasm's `update()` is synchronous JS. Large files sidestep this entirely via
  native b3sum (real multi-core hashing — see "Native b3sum hashing" above); for an
  NVMe-backed residence with no b3sum available, small-file WASM hashing would still need to
  move to Bun `Worker` threads to saturate multiple cores. The `update`/`digest` interface
  already isolates that change.
- **`--bench` read throughput is whatever the OS serves.** On a cache-warm tree it measures
  memory bandwidth, not disk; the true cold-share read rate is the first cold pass itself.
- **On-host, local filesystem only.** The `(dev,ino)` identity model needs real inodes; do
  not point this at an SMB/NFS mount (synthetic inodes) — `/mnt/user/...` on unRAID is a
  local FUSE mount and is fine (that's what the migration heuristic is for); a share mounted
  *from* another host over SMB/NFS is not.
- Scope is deliberately small: survey and publish. Replication, policy and resolution are
  `ath`'s custody (spec §18), which reads the manifest through the contract.
