// Shared test helpers: temp trees, deterministic-mtime file writes, a scan wrapper that
// counts hash calls, and a state loader.

process.env.ATH_SCAN_NO_TICKER = "1"; // no progress interval during tests

import { mkdtemp, writeFile, mkdir, utimes, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { blake3 } from "hash-wasm";
import { Logger } from "../src/log.ts";
import { Manifest } from "../src/manifest.ts";
import { scan, type ScanOptions } from "../src/scanner.ts";
import { countingFactory, blake3Factory } from "../src/hasher.ts";
import { MANIFEST_DIRNAME } from "../src/schema.ts";

export const quietLog = new Logger("quiet");

const dirs: string[] = [];

export async function tmpTree(): Promise<string> {
  const d = await mkdtemp(join(tmpdir(), "ath-scan-"));
  dirs.push(d);
  return d;
}

export async function cleanupAll(): Promise<void> {
  for (const d of dirs.splice(0)) await rm(d, { recursive: true, force: true });
}

/** Write a file (creating parents). mtimeSec is whole seconds so it round-trips to exact ns. */
export async function put(root: string, rel: string, content: string | Uint8Array, mtimeSec = 1_700_000_000): Promise<string> {
  const abs = join(root, rel);
  await mkdir(dirname(abs), { recursive: true });
  await writeFile(abs, content);
  await utimes(abs, mtimeSec, mtimeSec);
  return abs;
}

export const b3 = (data: string | Uint8Array): Promise<string> => blake3(data);

export interface ScanRun {
  summary: Awaited<ReturnType<typeof scan>>;
  hashCount: number;
  manifestDir: string;
}

/** Run a scan with a fresh hash-call counter; returns the summary and how many files were hashed. */
export async function runScan(root: string, extra: Partial<ScanOptions> = {}): Promise<ScanRun> {
  const factory = countingFactory(blake3Factory);
  const manifestDir = extra.manifestDir ?? join(root, MANIFEST_DIRNAME);
  const summary = await scan({
    root,
    manifestDir,
    factory,
    log: quietLog,
    concurrency: extra.concurrency ?? 4,
    full: extra.full,
    scrub: extra.scrub,
    chunkBytes: extra.chunkBytes,
    seedFrom: extra.seedFrom,
    b3sumPath: extra.b3sumPath,
    nativeThresholdBytes: extra.nativeThresholdBytes,
    _faultAfterHashes: extra._faultAfterHashes,
    _identityBatchSize: extra._identityBatchSize,
    _identityBatchIntervalMs: extra._identityBatchIntervalMs,
    // Default OFF unless a test opts in (by passing b3sumPath or _noNativeHasher explicitly):
    // real discovery would otherwise probe PATH on every single test in the suite. Harmless
    // either way (fixtures are always far below the native threshold) but this keeps every
    // existing/unrelated test fully deterministic regardless of the host's PATH.
    _noNativeHasher: extra._noNativeHasher ?? extra.b3sumPath === undefined,
    _nativeConcurrency: extra._nativeConcurrency,
    _hashProgressEvery: extra._hashProgressEvery,
    _hashProgressFloorMs: extra._hashProgressFloorMs,
    _hashProgressTickMs: extra._hashProgressTickMs,
  });
  return { summary, hashCount: factory.count, manifestDir };
}

/** Load the manifest state (identities + paths) for assertions. Test/inspection only —
 * dumpIdentities/dumpPaths materialize the full tables into memory, fine for small fixtures. */
export async function loadState(manifestDir: string, root: string) {
  const mf = await Manifest.open(manifestDir, root, quietLog);
  const identities = mf.dumpIdentities();
  const paths = mf.dumpPaths();
  const generation = mf.generation;
  await mf.close();
  return { identities, paths, generation };
}
