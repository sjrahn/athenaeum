// Self-benchmark: measure hash throughput (WASM, and native b3sum when available) against
// the share's actual read throughput, so the operator can see which one bounds the pipeline.
// Run on the first cold pass and on demand via --bench (which writes no manifest). Measured
// on the real deployment host (12900H): WASM does ~58.77 MiB/s in-memory vs ~159 MiB/s disk
// read — the pipeline is hash-BOUND on that host, not disk-bound as originally assumed; a
// native b3sum (rayon, multi-core) is the fix, hence benchmarking it here too.

import { open, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { walkTree, type FileEntry } from "./walk.ts";
import { discoverNativeHasher, type HasherFactory, type NativeHasher } from "./hasher.ts";
import { Logger, humanBytes } from "./log.ts";

export interface BenchResult {
  hashBytesPerSec: number; // in-process WASM
  nativeHashBytesPerSec: number | null; // native b3sum; null when none was discovered/verified
  readBytesPerSec: number | null; // null when the tree held too little data to measure
  bound: "disk" | "hash" | "unknown"; // computed against whichever hash rate is faster (native, if any)
}

const HASH_BENCH_BYTES = 256 * 1024 * 1024; // 256 MiB in-memory
const READ_BENCH_BUDGET = 512 * 1024 * 1024; // read up to 512 MiB of real files
const CHUNK = 4 * 1024 * 1024;

async function benchHash(factory: HasherFactory): Promise<number> {
  const chunk = Buffer.alloc(CHUNK); // content-independent; zeros are fine for BLAKE3
  const hasher = await factory.create();
  const t0 = performance.now();
  let done = 0;
  while (done < HASH_BENCH_BYTES) {
    hasher.update(chunk);
    done += CHUNK;
  }
  hasher.digest();
  const secs = (performance.now() - t0) / 1000;
  return done / secs;
}

/** Hash a synthetic on-disk file (content-independent, like benchHash's zero chunk) through
 * a native hasher, so the measurement isolates hash throughput from real-share read variance
 * the way the in-memory WASM bench does. */
async function benchNativeHash(hasher: NativeHasher, bytes: number): Promise<number> {
  const tmp = join(tmpdir(), `ath-scan-bench-native-${process.pid}-${Date.now()}`);
  const chunk = Buffer.alloc(CHUNK);
  const fh = await open(tmp, "w");
  try {
    let written = 0;
    while (written < bytes) {
      const n = Math.min(chunk.length, bytes - written);
      await fh.write(chunk, 0, n);
      written += n;
    }
  } finally {
    await fh.close();
  }
  try {
    const t0 = performance.now();
    await hasher.hashFile(tmp);
    const secs = (performance.now() - t0) / 1000;
    return secs > 0 ? bytes / secs : bytes;
  } finally {
    await rm(tmp, { force: true }).catch(() => {});
  }
}

async function benchRead(root: string, excludeAbs: string | null, log: Logger): Promise<number | null> {
  const files: FileEntry[] = [];
  let budget = 0n;
  for await (const e of walkTree(root, excludeAbs)) {
    if (e.kind !== "file" || e.size === 0n) continue;
    files.push(e);
    budget += e.size;
    if (budget >= BigInt(READ_BENCH_BUDGET)) break;
  }
  if (files.length === 0) {
    log.warn("read bench: no readable files under root; skipping read-throughput measurement");
    return null;
  }
  const buf = Buffer.allocUnsafe(CHUNK);
  const t0 = performance.now();
  let read = 0n;
  for (const f of files) {
    let fh;
    try {
      fh = await open(f.abspath, "r");
    } catch {
      continue;
    }
    try {
      for (;;) {
        const { bytesRead } = await fh.read(buf, 0, CHUNK, null);
        if (bytesRead === 0) break;
        read += BigInt(bytesRead);
      }
    } finally {
      await fh.close();
    }
  }
  const secs = (performance.now() - t0) / 1000;
  return secs > 0 ? Number(read) / secs : null;
}

export async function benchmark(
  root: string,
  excludeAbs: string | null,
  factory: HasherFactory,
  log: Logger,
  opts: { b3sumPath?: string } = {},
): Promise<BenchResult> {
  log.info(`benchmark: hashing ${humanBytes(HASH_BENCH_BYTES)} in memory (${factory.name})…`);
  const hashBytesPerSec = await benchHash(factory);
  log.info(`  hash throughput (WASM)    ${humanBytes(hashBytesPerSec)}/s`);

  const nativeHasher = await discoverNativeHasher(opts.b3sumPath, log);
  let nativeHashBytesPerSec: number | null = null;
  if (nativeHasher) {
    log.info(`benchmark: hashing ${humanBytes(HASH_BENCH_BYTES)} on disk via ${nativeHasher.path}…`);
    nativeHashBytesPerSec = await benchNativeHash(nativeHasher, HASH_BENCH_BYTES);
    const speedup = (nativeHashBytesPerSec / hashBytesPerSec).toFixed(1);
    log.info(`  hash throughput (native)  ${humanBytes(nativeHashBytesPerSec)}/s  (${speedup}x WASM)`);
  } else {
    log.info("  no b3sum binary found — native hash throughput not measured");
  }

  log.info(`benchmark: reading up to ${humanBytes(READ_BENCH_BUDGET)} of real files from ${root}…`);
  const readBytesPerSec = await benchRead(root, excludeAbs, log);
  if (readBytesPerSec !== null) log.info(`  read throughput           ${humanBytes(readBytesPerSec)}/s`);

  // Whichever hash rate a real scan would actually use (native wins the threshold when
  // available) is what determines whether the pipeline is disk- or hash-bound.
  const effectiveHashBytesPerSec = nativeHashBytesPerSec ?? hashBytesPerSec;
  let bound: BenchResult["bound"] = "unknown";
  if (readBytesPerSec !== null) bound = readBytesPerSec <= effectiveHashBytesPerSec ? "disk" : "hash";
  log.info(`  pipeline is ${bound === "unknown" ? "unmeasured (no read sample)" : bound + "-bound"}`);

  return { hashBytesPerSec, nativeHashBytesPerSec, readBytesPerSec, bound };
}
