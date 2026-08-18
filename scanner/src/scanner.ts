// The scan orchestration. Two phases: (1) walk + stat-classify every file, updating path
// rows and reconciling deletions, deciding which files need a (re)hash; (2) a bounded pool
// hashes just those, appending an identity row in batched transactions (durable within
// `batchSize` files / `batchIntervalMs`, whichever first — a crash loses at most the last
// batch). Then an optional scrub sampler, the publish step, and the run summary.

import { open, stat } from "node:fs/promises";
import { sep } from "node:path";
import { walkTree, type FileEntry } from "./walk.ts";
import { Manifest } from "./manifest.ts";
import { DEFAULT_IGNORE_PATTERNS, identityKey, type IdentityState, type ScanMode, type ScanSummary } from "./schema.ts";
import { discoverNativeHasher, type HasherFactory, type Hasher, type NativeHasher } from "./hasher.ts";
import { Logger, humanBytes, humanCount, humanDuration, humanRate } from "./log.ts";

export const DEFAULT_CHUNK = 4 * 1024 * 1024;
export const DEFAULT_CONCURRENCY = 4;
/** Files at or above this size are routed to the native b3sum path instead of in-process
 * WASM (when a b3sum binary is available) — see hasher.ts's discoverNativeHasher. */
export const DEFAULT_NATIVE_THRESHOLD = 1024 * 1024; // 1 MiB
/** b3sum is internally multithreaded (rayon, all cores) — spawning several at once doesn't
 * help and just contends for the same cores, so this is NOT multiplied by --concurrency. */
export const DEFAULT_NATIVE_CONCURRENCY = 2;
/** non-TTY progress heartbeat: one line per this many hashed files... */
export const HASH_PROGRESS_EVERY = 16;
/** ...but never silent longer than this during a stretch of huge files (hashed count stuck
 * mid-file for a long time) — see log.ts's Logger.progress() for the 1s-min-spacing clamp
 * that sits on top of both triggers. */
export const HASH_PROGRESS_FLOOR_MS = 30_000;

export interface ScanOptions {
  root: string; // absolute
  manifestDir: string; // absolute
  factory: HasherFactory;
  log: Logger;
  concurrency?: number;
  /** Native (b3sum) pool size — see `--native-concurrency` (default DEFAULT_NATIVE_CONCURRENCY).
   * `_nativeConcurrency` (test/tuning hook) wins if both are set. */
  nativeConcurrency?: number;
  full?: boolean; // force re-hash of every file (also disables the inode-migration heuristic and all seeding)
  scrub?: number; // re-hash N random files as a bit-rot check
  chunkBytes?: number;
  /** Explicit manifest.sqlite paths to seed identities/paths from before the walk starts
   * (repeatable). Ignored (not even validated) when `full` is set — full means trust nothing. */
  seedFrom?: string[];
  /** Extra basename patterns (repeatable `--ignore`) appended to the ignore deny-list — see
   * schema.ts's DEFAULT_IGNORE_PATTERNS for the matching rules. */
  ignorePatterns?: string[];
  /** Drop the built-in DEFAULT_IGNORE_PATTERNS; `ignorePatterns` above still applies on top. */
  noDefaultIgnores?: boolean;
  /** Explicit b3sum binary path (--b3sum). Unset falls through to auto-discovery (a binary
   * beside the running executable, then PATH). */
  b3sumPath?: string;
  /** Files at/above this size use native b3sum instead of WASM, when a b3sum is available
   * (default DEFAULT_NATIVE_THRESHOLD, 1 MiB). */
  nativeThresholdBytes?: number;
  /** test hook: throw after N successful hashes (each already applied to the open batch) to simulate a kill. */
  _faultAfterHashes?: number;
  /** test/tuning hook: identity batch commit thresholds (default 64 files / 5000ms). */
  _identityBatchSize?: number;
  _identityBatchIntervalMs?: number;
  /** test hook: skip native-hasher discovery entirely — deterministic "nothing found" runs
   * regardless of what's actually on the test host's PATH. */
  _noNativeHasher?: boolean;
  /** test/tuning hook: override the native-hash concurrency cap (default DEFAULT_NATIVE_CONCURRENCY). */
  _nativeConcurrency?: number;
  /** test/tuning hook: override the non-TTY hash-progress cadence (default HASH_PROGRESS_EVERY). */
  _hashProgressEvery?: number;
  /** test/tuning hook: override the non-TTY hash-progress stall floor in ms (default HASH_PROGRESS_FLOOR_MS). */
  _hashProgressFloorMs?: number;
  /** test hook: override the hash-phase ticker's own interval (default 1000ms) — lets a test
   * observe the stall floor without waiting a full tick. */
  _hashProgressTickMs?: number;
}

class SimulatedInterrupt extends Error {}

async function hashFile(abspath: string, hasher: Hasher, chunkBytes: number): Promise<{ digest: string; bytes: bigint }> {
  const fh = await open(abspath, "r");
  const buf = Buffer.allocUnsafe(chunkBytes);
  let bytes = 0n;
  try {
    while (true) {
      const { bytesRead } = await fh.read(buf, 0, chunkBytes, null);
      if (bytesRead === 0) break;
      hasher.update(buf.subarray(0, bytesRead));
      bytes += BigInt(bytesRead);
    }
  } finally {
    await fh.close();
  }
  return { digest: hasher.digest(), bytes };
}

/** Fisher-Yates shuffle, in place. */
function shuffle<T>(items: T[]): void {
  for (let i = items.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [items[i], items[j]] = [items[j]!, items[i]!];
  }
}

/** Run `worker` over `items` with at most `k` in flight. */
async function runPool<T>(items: T[], k: number, worker: (item: T) => Promise<void>): Promise<void> {
  let next = 0;
  const runner = async (): Promise<void> => {
    for (;;) {
      const i = next++;
      if (i >= items.length) return;
      await worker(items[i]!);
    }
  };
  await Promise.all(Array.from({ length: Math.min(Math.max(1, k), items.length || 1) }, runner));
}

export async function scan(opts: ScanOptions): Promise<ScanSummary> {
  const { root, log } = opts;
  const k = opts.concurrency ?? DEFAULT_CONCURRENCY;
  const chunkBytes = opts.chunkBytes ?? DEFAULT_CHUNK;
  const full = opts.full ?? false;

  const mf = await Manifest.open(opts.manifestDir, root, log, {
    batchSize: opts._identityBatchSize,
    batchIntervalMs: opts._identityBatchIntervalMs,
  });
  const isCold = mf.isEmpty();
  const mode: ScanMode = isCold ? "cold" : "incremental";
  const gen = mf.generation + 1;

  // The manifest dir sits under root by default; exclude its subtree from the walk.
  const manifestUnderRoot = opts.manifestDir === root || opts.manifestDir.startsWith(root + sep);
  const excludeAbs = manifestUnderRoot ? opts.manifestDir : null;

  const summary: ScanSummary = {
    mode,
    generation: gen,
    filesSeen: 0,
    hashed: 0,
    hashedNative: 0,
    moved: 0,
    migrated: 0,
    seeded: 0,
    deleted: 0,
    skipped: 0,
    ignored: 0,
    scrubbed: 0,
    corrupt: 0,
    bytesHashed: "0",
    elapsedMs: 0,
  };

  mf.genOpen(mode, gen);
  log.info(`scan ${mode} generation ${gen}: ${root}  (concurrency ${k}${full ? ", full re-hash" : ""})`);

  // Explicit --seed-from sources import before the walk starts. Ignored entirely under
  // --full: full means "trust nothing, ignore every cache, including seeds."
  if (!full && opts.seedFrom && opts.seedFrom.length > 0) {
    for (const src of opts.seedFrom) {
      const imported = await mf.seedFrom(src, "", gen, /* explicit */ true);
      if (imported !== null) {
        summary.seeded += imported;
        log.info(`seeded ${humanCount(imported)} identities from --seed-from ${src}`);
      }
    }
  }

  try {
    return await runScanBody(mf, opts, summary, gen, full, k, chunkBytes, excludeAbs);
  } finally {
    // Always roll back any open batch and close the connection — even on interrupt, so a
    // killed run leaves state.sqlite consistent (crash marker: this generation's finished_at
    // stays NULL) for the next resume.
    await mf.close();
  }
}

async function runScanBody(
  mf: Manifest,
  opts: ScanOptions,
  summary: ScanSummary,
  gen: number,
  full: boolean,
  k: number,
  chunkBytes: number,
  excludeAbs: string | null,
): Promise<ScanSummary> {
  const { root, log, factory } = opts;
  const started = performance.now();

  // Custom --ignore patterns always apply, layered on top of the built-in defaults unless
  // --no-default-ignores dropped them.
  const ignorePatterns = [
    ...(opts.noDefaultIgnores ? [] : DEFAULT_IGNORE_PATTERNS),
    ...(opts.ignorePatterns ?? []),
  ];

  // ── phase 1: walk + classify ──────────────────────────────────────────────────
  const toHash: FileEntry[] = [];
  let bytesToHash = 0n;
  const queuedKeys = new Set<string>(); // identities already queued this run (dedupe hardlinks)
  let walkCount = 0;

  mf.beginWalk();
  for await (const entry of walkTree(root, excludeAbs, ignorePatterns)) {
    if (entry.kind === "skip") {
      summary.skipped++;
      mf.putSkip(entry.relpath, entry.reason, gen);
      log.debug(`skip ${entry.relpath} (${entry.reason})`);
      continue;
    }
    if (entry.kind === "ignored") {
      // Never marked seen: a previously-indexed junk row (predating the deny-list, or newly
      // matched by a --ignore addition) reconciles away as a deletion via the normal
      // "not seen this walk" path — no special-case cleanup needed.
      summary.ignored++;
      log.debug(`ignored ${entry.relpath} (${entry.isDir ? "dir pruned" : "file"})`);
      continue;
    }
    if (entry.kind === "nested-manifest") {
      if (full) {
        log.debug(`nested manifest at ${entry.relpath || "."} — auto-seed disabled under --full`);
        continue;
      }
      const imported = await mf.seedFrom(entry.abspath, entry.relpath, gen, /* explicit */ false);
      if (imported !== null) {
        summary.seeded += imported;
        log.info(`seeded ${humanCount(imported)} identities from nested manifest at ${entry.relpath || "."}`);
      }
      continue;
    }
    summary.filesSeen++;
    mf.markSeen(entry.relpath);

    const prevPath = mf.getPathIdentity(entry.relpath);
    const pathChanged = !prevPath || prevPath.dev !== entry.dev || prevPath.ino !== entry.ino;

    // Inode-migration heuristic (FUSE/shfs remounts, e.g. unRAID's /mnt/user): the SAME path
    // now presents a NEW (dev,ino). If the OLD identity that path referenced has an exactly
    // matching (size, mtimeNs), carry its blake3 forward onto the new identity — zero re-hash.
    // Disabled under --full, which means "ignore every cache, including this one."
    let migrated = false;
    if (!full && prevPath && pathChanged) {
      const oldIdentity = mf.getIdentity(prevPath.dev, prevPath.ino);
      if (oldIdentity && oldIdentity.size === entry.size && oldIdentity.mtimeNs === entry.mtimeNs) {
        mf.putMigratedIdentity(entry.dev, entry.ino, entry.size, entry.mtimeNs, oldIdentity.blake3, gen);
        summary.migrated++;
        migrated = true;
      }
    }

    const key = identityKey(entry.dev, entry.ino);
    const existing = migrated ? undefined : mf.getIdentity(entry.dev, entry.ino);
    const contentKnown = migrated || (!!existing && existing.size === entry.size && existing.mtimeNs === entry.mtimeNs);
    // Identities are materialized as they're hashed, so a second hardlink/path to the same
    // inode in this run must dedupe against what's already queued, not just prior state.
    const needHash = !queuedKeys.has(key) && !migrated && (full || !contentKnown);

    if (pathChanged) {
      // A new path onto an already-known, unchanged identity is a rename or new hardlink to
      // pre-existing content: zero re-hash. (A brand-new file is counted by `hashed`.)
      if (!prevPath && contentKnown) summary.moved++;
      mf.putPath(entry.relpath, entry.dev, entry.ino, gen);
    }

    if (needHash) {
      queuedKeys.add(key);
      toHash.push(entry);
      bytesToHash += entry.size;
    }

    if (++walkCount % 2000 === 0) log.progress(`walk: ${humanCount(walkCount)} files, ${humanCount(toHash.length)} to hash`);
  }
  log.endProgress();

  summary.deleted = mf.reconcileDeletions();
  mf.commitWalk();
  log.info(
    `walk done: ${humanCount(summary.filesSeen)} files seen, ${humanCount(toHash.length)} to hash ` +
      `(${humanBytes(bytesToHash)}), ${humanCount(summary.moved)} moved, ${humanCount(summary.migrated)} migrated, ` +
      `${humanCount(summary.deleted)} deleted, ${humanCount(summary.skipped)} skipped, ` +
      `${humanCount(summary.ignored)} ignored`,
  );

  // ── phase 2: hash pool(s) ─────────────────────────────────────────────────────────
  // Route files at/above the native threshold to a discovered b3sum binary (multi-core,
  // reads the file itself) and everything else to the in-process WASM pool, run concurrently.
  const nativeHasher: NativeHasher | null = opts._noNativeHasher ? null : await discoverNativeHasher(opts.b3sumPath, log);
  const nativeThreshold = BigInt(opts.nativeThresholdBytes ?? DEFAULT_NATIVE_THRESHOLD);
  const wasmQueue: FileEntry[] = [];
  const nativeQueue: FileEntry[] = [];
  for (const entry of toHash) {
    if (nativeHasher && entry.size >= nativeThreshold) nativeQueue.push(entry);
    else wasmQueue.push(entry);
  }
  // unRAID's file-based array places every file on exactly one physical disk, and allocation
  // policy tends to put a whole directory's files on the same disk — so the native queue,
  // built in walk (directory) order, has long same-disk runs. A pool of size K>1 draining it
  // in order would mostly contend for the same spindle instead of fanning out across disks.
  // Shuffling decorrelates queue order from directory/disk locality. Order was never load-bearing
  // for resume correctness (identities commit independently, keyed by dev/ino), so this is safe.
  // WASM queue is untouched — small files, spawn/seek locality doesn't matter there.
  shuffle(nativeQueue);

  let hashedBytes = 0n;
  const hashStart = performance.now();
  const hashProgressEvery = opts._hashProgressEvery ?? HASH_PROGRESS_EVERY;
  const hashProgressFloorMs = opts._hashProgressFloorMs ?? HASH_PROGRESS_FLOOR_MS;
  let lastHashProgressAt = hashStart;

  const hashProgressMsg = (): string => {
    const elapsed = performance.now() - hashStart;
    return (
      `hash: ${humanCount(summary.hashed)}/${humanCount(toHash.length)} files, ` +
      `${humanBytes(hashedBytes)}/${humanBytes(bytesToHash)}, ${humanRate(hashedBytes, elapsed)}`
    );
  };
  const emitHashProgress = (): void => {
    log.progress(hashProgressMsg());
    lastHashProgressAt = performance.now();
  };

  let ticker: ReturnType<typeof setInterval> | null = null;
  if (toHash.length > 0 && !process.env.ATH_SCAN_NO_TICKER) {
    ticker = setInterval(() => {
      // TTY: redraw every tick, unchanged (Logger always rewrites on a TTY regardless of how
      // often it's called). non-TTY: the every-N-hashed-files trigger below is the primary
      // heartbeat cadence; this tick only forces a line once the stall floor is crossed, so a
      // stretch of huge files (hashed count not advancing) still heartbeats.
      if (process.stderr.isTTY || performance.now() - lastHashProgressAt >= hashProgressFloorMs) {
        emitHashProgress();
      }
    }, opts._hashProgressTickMs ?? 1000);
  }

  // Shared by both pools: bumps summary.hashed, fires the count-driven heartbeat, and is the
  // one place the fault-injection test hook can interrupt (used by exactly one pool in every
  // existing test, since fixtures are always far below the native threshold).
  const recordHashed = (): void => {
    summary.hashed++;
    if (summary.hashed % hashProgressEvery === 0) emitHashProgress();
    if (opts._faultAfterHashes !== undefined && summary.hashed >= opts._faultAfterHashes) {
      throw new SimulatedInterrupt(`fault after ${summary.hashed} hashes`);
    }
  };

  try {
    // allSettled, not all: if one pool's worker throws (e.g. the fault-injection hook), we
    // still want the other pool to reach a clean stopping point before genClose/mf.close() —
    // otherwise an orphaned worker could touch `mf` after the connection is closed.
    const results = await Promise.allSettled([
      runPool(wasmQueue, k, async (entry) => {
        let hasher: Hasher;
        let result: { digest: string; bytes: bigint };
        try {
          hasher = await factory.create();
          result = await hashFile(entry.abspath, hasher, chunkBytes);
        } catch (e) {
          // file vanished or turned unreadable between the walk and the hash — log-and-skip
          const code = (e as { code?: string })?.code?.toLowerCase() ?? "eunknown";
          summary.skipped++;
          mf.putSkip(entry.relpath, code, gen);
          log.debug(`skip ${entry.relpath} during hash (${code})`);
          return;
        }
        mf.putIdentity(entry.dev, entry.ino, entry.size, entry.mtimeNs, result.digest, gen);
        hashedBytes += result.bytes;
        recordHashed();
      }),
      runPool(nativeQueue, opts._nativeConcurrency ?? opts.nativeConcurrency ?? DEFAULT_NATIVE_CONCURRENCY, async (entry) => {
        let digest: string;
        try {
          digest = await nativeHasher!.hashFile(entry.abspath);
        } catch (e) {
          // b3sum failure (nonzero exit, bad output, vanished file) — log-and-skip, never abort.
          summary.skipped++;
          mf.putSkip(entry.relpath, "b3sum-failed", gen);
          log.debug(`skip ${entry.relpath} during native hash (${(e as Error).message})`);
          return;
        }
        mf.putIdentity(entry.dev, entry.ino, entry.size, entry.mtimeNs, digest, gen);
        // b3sum reads the file itself — no chunked-read loop here to count bytes off of, so
        // this is the walk-time stat size rather than an actually-observed read count.
        hashedBytes += entry.size;
        summary.hashedNative++;
        recordHashed();
      }),
    ]);
    const rejected = results.find((r): r is PromiseRejectedResult => r.status === "rejected");
    if (rejected) throw rejected.reason;
  } finally {
    if (ticker) clearInterval(ticker);
    log.endProgress();
  }
  mf.flushBatch(); // commit whatever's left in the final partial batch — only reached on success
  summary.bytesHashed = hashedBytes.toString();

  // ── optional scrub ──────────────────────────────────────────────────────────────
  if (opts.scrub && opts.scrub > 0) {
    const res = await scrubSample(mf, root, opts.scrub, gen, factory, chunkBytes, log);
    summary.scrubbed = res.scrubbed;
    summary.corrupt = res.corrupt;
  }

  summary.elapsedMs = Math.round(performance.now() - started);
  mf.genClose(summary); // only reached on the success path
  await mf.publish(); // unveil this complete generation to remote readers
  return summary;
}

/** Re-hash N randomly-sampled identities and compare to the stored digest. */
async function scrubSample(
  mf: Manifest,
  root: string,
  n: number,
  gen: number,
  factory: HasherFactory,
  chunkBytes: number,
  log: Logger,
): Promise<{ scrubbed: number; corrupt: number }> {
  const sample = mf.scrubSample(n);

  let scrubbed = 0;
  let corrupt = 0;
  for (const row of sample) {
    const id: IdentityState = { dev: row.dev, ino: row.ino, size: row.size, mtimeNs: row.mtimeNs, blake3: row.blake3, generation: 0 };
    const relpath = row.path;
    const abspath = root + sep + (sep === "/" ? relpath : relpath.split("/").join(sep));
    let st;
    try {
      st = await stat(abspath, { bigint: true });
    } catch {
      continue; // vanished; the next stat-walk reconciles it
    }
    if (st.size !== id.size || st.mtimeNs !== id.mtimeNs) continue; // legitimately changed; not a scrub verdict
    let hasher: Hasher;
    let digest: string;
    try {
      hasher = await factory.create();
      ({ digest } = await hashFile(abspath, hasher, chunkBytes));
    } catch {
      continue;
    }
    scrubbed++;
    if (digest !== id.blake3) {
      corrupt++;
      mf.putScrubCorrupt(id, relpath, digest, gen);
      log.error(`SCRUB CORRUPTION: ${relpath} — stored ${id.blake3.slice(0, 16)}… != actual ${digest.slice(0, 16)}… at a stable stat tuple`);
    }
  }
  log.info(`scrub: ${scrubbed} re-hashed, ${corrupt} corrupt`);
  return { scrubbed, corrupt };
}

/** Standalone compaction: drop orphaned identities, VACUUM, publish. */
export async function compact(root: string, manifestDir: string, log: Logger): Promise<void> {
  const started = performance.now();
  const mf = await Manifest.open(manifestDir, root, log);
  const gen = mf.generation + 1;
  mf.genOpen("compact", gen);
  const res = mf.compact(gen);
  const summary: ScanSummary = {
    mode: "compact",
    generation: gen,
    filesSeen: 0,
    hashed: 0,
    hashedNative: 0,
    moved: 0,
    migrated: 0,
    seeded: 0,
    deleted: res.orphansDropped,
    skipped: 0,
    ignored: 0,
    scrubbed: 0,
    corrupt: 0,
    bytesHashed: "0",
    elapsedMs: Math.round(performance.now() - started),
  };
  mf.genClose(summary);
  await mf.publish();
  await mf.close();
  log.info(`compact generation ${gen}: ${humanCount(res.identities)} identities, ${humanCount(res.paths)} paths, ${humanCount(res.orphansDropped)} orphans dropped`);
}

export function formatSummary(s: ScanSummary, root: string): string {
  const rate = s.elapsedMs > 0 ? humanRate(BigInt(s.bytesHashed), s.elapsedMs) : "—";
  const lines = [
    `scan summary — generation ${s.generation} (${s.mode})`,
    `  root          ${root}`,
    `  files seen    ${humanCount(s.filesSeen)}`,
    `  hashed        ${humanCount(s.hashed)}  (${humanBytes(BigInt(s.bytesHashed))})`,
    `  hashed native ${humanCount(s.hashedNative)}`,
    `  moved         ${humanCount(s.moved)}`,
    `  migrated      ${humanCount(s.migrated)}`,
    `  seeded        ${humanCount(s.seeded)}`,
    `  deleted       ${humanCount(s.deleted)}`,
    `  skipped       ${humanCount(s.skipped)}`,
    `  ignored       ${humanCount(s.ignored)}`,
    `  scrubbed      ${humanCount(s.scrubbed)}   corrupt ${humanCount(s.corrupt)}`,
    `  bytes hashed  ${humanBytes(BigInt(s.bytesHashed))}`,
    `  elapsed       ${humanDuration(s.elapsedMs)}`,
    `  hash rate     ${rate}`,
  ];
  return lines.join("\n");
}
