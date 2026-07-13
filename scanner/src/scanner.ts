// The scan orchestration. Two phases: (1) walk + stat-classify every file, updating path
// rows and reconciling deletions, deciding which files need a (re)hash; (2) a bounded pool
// hashes just those, appending an identity row and fsyncing per file so a kill resumes
// without re-hashing completed work. Then an optional scrub sampler and the run summary.

import { open, stat } from "node:fs/promises";
import { sep } from "node:path";
import { walkTree, type FileEntry } from "./walk.ts";
import { Manifest, type IdentityState } from "./manifest.ts";
import { identityKey, type ScanMode, type ScanSummary } from "./schema.ts";
import type { HasherFactory, Hasher } from "./hasher.ts";
import { Logger, humanBytes, humanCount, humanDuration, humanRate } from "./log.ts";

export const DEFAULT_CHUNK = 4 * 1024 * 1024;
export const DEFAULT_CONCURRENCY = 4;

export interface ScanOptions {
  root: string; // absolute
  manifestDir: string; // absolute
  factory: HasherFactory;
  log: Logger;
  concurrency?: number;
  full?: boolean; // force re-hash of every file
  scrub?: number; // re-hash N random files as a bit-rot check
  chunkBytes?: number;
  /** test hook: throw after N successful hashes (each already flushed) to simulate a kill. */
  _faultAfterHashes?: number;
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

  const mf = await Manifest.open(opts.manifestDir, root, log);
  const isCold = mf.identities.size === 0 && mf.paths.size === 0;
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
    moved: 0,
    deleted: 0,
    skipped: 0,
    scrubbed: 0,
    corrupt: 0,
    bytesHashed: "0",
    elapsedMs: 0,
  };

  mf.genOpen(mode, gen);
  log.info(`scan ${mode} generation ${gen}: ${root}  (concurrency ${k}${full ? ", full re-hash" : ""})`);

  try {
    return await runScanBody(mf, opts, summary, gen, full, k, chunkBytes, excludeAbs);
  } finally {
    // Always flush the buffer and close the journal handle — even on interrupt, so the
    // per-file-flushed journal is left clean for the next resume.
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

  // ── phase 1: walk + classify ──────────────────────────────────────────────────
  const toHash: FileEntry[] = [];
  let bytesToHash = 0n;
  const seenPaths = new Set<string>();
  const queuedKeys = new Set<string>(); // identities already queued this run (dedupe hardlinks)
  let walkCount = 0;

  for await (const entry of walkTree(root, excludeAbs)) {
    if (entry.kind === "skip") {
      summary.skipped++;
      mf.putSkip(entry.relpath, entry.reason, gen);
      log.debug(`skip ${entry.relpath} (${entry.reason})`);
      continue;
    }
    summary.filesSeen++;
    seenPaths.add(entry.relpath);

    const key = identityKey(entry.dev, entry.ino);
    const existing = mf.identities.get(key);
    const contentKnown = !!existing && existing.size === entry.size && existing.mtimeNs === entry.mtimeNs;
    // Identities are materialized in phase 2, so a second hardlink/path to the same inode in
    // this run must dedupe against what's already queued, not just against prior state.
    const needHash = !queuedKeys.has(key) && (full || !contentKnown);

    const prevPath = mf.paths.get(entry.relpath);
    const pathChanged = !prevPath || prevPath.dev !== entry.dev || prevPath.ino !== entry.ino;
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

  // reconcile deletions (snapshot keys first — deletePath mutates the map)
  for (const relpath of [...mf.paths.keys()]) {
    if (!seenPaths.has(relpath)) {
      mf.deletePath(relpath, gen);
      summary.deleted++;
    }
  }
  await mf.flush();
  log.info(
    `walk done: ${humanCount(summary.filesSeen)} files seen, ${humanCount(toHash.length)} to hash ` +
      `(${humanBytes(bytesToHash)}), ${humanCount(summary.moved)} moved, ${humanCount(summary.deleted)} deleted, ` +
      `${humanCount(summary.skipped)} skipped`,
  );

  // ── phase 2: hash pool ─────────────────────────────────────────────────────────
  let hashedBytes = 0n;
  const hashStart = performance.now();
  let ticker: ReturnType<typeof setInterval> | null = null;
  if (toHash.length > 0 && !process.env.ATH_SCAN_NO_TICKER) {
    ticker = setInterval(() => {
      const elapsed = performance.now() - hashStart;
      log.progress(
        `hash: ${humanCount(summary.hashed)}/${humanCount(toHash.length)} files, ` +
          `${humanBytes(hashedBytes)}/${humanBytes(bytesToHash)}, ${humanRate(hashedBytes, elapsed)}`,
      );
    }, 1000);
  }

  try {
    await runPool(toHash, k, async (entry) => {
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
      summary.hashed++;
      hashedBytes += result.bytes;
      await mf.flush(); // durability at file granularity: resume never re-hashes this file

      if (opts._faultAfterHashes !== undefined && summary.hashed >= opts._faultAfterHashes) {
        throw new SimulatedInterrupt(`fault after ${summary.hashed} hashes`);
      }
    });
  } finally {
    if (ticker) clearInterval(ticker);
    log.endProgress();
  }
  summary.bytesHashed = hashedBytes.toString();

  // ── optional scrub ──────────────────────────────────────────────────────────────
  if (opts.scrub && opts.scrub > 0) {
    const res = await scrubSample(mf, root, opts.scrub, gen, factory, chunkBytes, log);
    summary.scrubbed = res.scrubbed;
    summary.corrupt = res.corrupt;
  }

  summary.elapsedMs = Math.round(performance.now() - started);
  mf.genClose(summary); // only reached on the success path; the caller's finally closes the manifest
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
  // reverse index: identity -> one representative live path
  const rep = new Map<string, string>();
  for (const [relpath, p] of mf.paths) {
    const key = identityKey(p.dev, p.ino);
    if (mf.identities.has(key) && !rep.has(key)) rep.set(key, relpath);
  }
  const keys = [...rep.keys()];
  // Fisher-Yates partial shuffle for a uniform sample of size n.
  for (let i = 0; i < Math.min(n, keys.length); i++) {
    const j = i + Math.floor(Math.random() * (keys.length - i));
    [keys[i], keys[j]] = [keys[j]!, keys[i]!];
  }
  const sample = keys.slice(0, Math.min(n, keys.length));

  let scrubbed = 0;
  let corrupt = 0;
  for (const key of sample) {
    const id = mf.identities.get(key)!;
    const relpath = rep.get(key)!;
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

/** Standalone compaction: fold journal into a fresh snapshot at a new generation. */
export async function compact(root: string, manifestDir: string, log: Logger): Promise<void> {
  const mf = await Manifest.open(manifestDir, root, log);
  const gen = mf.generation + 1;
  mf.genOpen("compact", gen);
  const res = await mf.compact(gen);
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
    `  moved         ${humanCount(s.moved)}`,
    `  deleted       ${humanCount(s.deleted)}`,
    `  skipped       ${humanCount(s.skipped)}`,
    `  scrubbed      ${humanCount(s.scrubbed)}   corrupt ${humanCount(s.corrupt)}`,
    `  bytes hashed  ${humanBytes(BigInt(s.bytesHashed))}`,
    `  elapsed       ${humanDuration(s.elapsedMs)}`,
    `  hash rate     ${rate}`,
  ];
  return lines.join("\n");
}
