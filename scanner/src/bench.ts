// Self-benchmark: measure the WASM hash throughput against the share's actual read
// throughput, so the operator can see which one bounds the pipeline. Run on the first cold
// pass and on demand via --bench (which writes no manifest). The settled expectation is
// disk-bound: hash rate should comfortably exceed read rate on spinning rust.

import { open } from "node:fs/promises";
import { walkTree, type FileEntry } from "./walk.ts";
import type { HasherFactory } from "./hasher.ts";
import { Logger, humanBytes } from "./log.ts";

export interface BenchResult {
  hashBytesPerSec: number;
  readBytesPerSec: number | null; // null when the tree held too little data to measure
  bound: "disk" | "hash" | "unknown";
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
): Promise<BenchResult> {
  log.info(`benchmark: hashing ${humanBytes(HASH_BENCH_BYTES)} in memory (${factory.name})…`);
  const hashBytesPerSec = await benchHash(factory);
  log.info(`  hash throughput  ${humanBytes(hashBytesPerSec)}/s`);

  log.info(`benchmark: reading up to ${humanBytes(READ_BENCH_BUDGET)} of real files from ${root}…`);
  const readBytesPerSec = await benchRead(root, excludeAbs, log);
  if (readBytesPerSec !== null) log.info(`  read throughput  ${humanBytes(readBytesPerSec)}/s`);

  let bound: BenchResult["bound"] = "unknown";
  if (readBytesPerSec !== null) bound = readBytesPerSec <= hashBytesPerSec ? "disk" : "hash";
  log.info(`  pipeline is ${bound === "unknown" ? "unmeasured (no read sample)" : bound + "-bound"}`);

  return { hashBytesPerSec, readBytesPerSec, bound };
}
