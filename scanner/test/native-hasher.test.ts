// Native b3sum hashing: discovery/verification (hasher.ts) and the scan-level wiring
// (threshold routing, per-file failure handling, the concurrency cap). Uses fake b3sum
// binaries under test/fixtures/ instead of a real one — this host (and CI) may not have one,
// and the fakes compute real BLAKE3 via hash-wasm so digest-correctness assertions still hold.

import { test, expect, afterAll } from "bun:test";
import { readFileSync, writeFileSync } from "node:fs";
import { rm } from "node:fs/promises";
import { join } from "node:path";
import { identityKey } from "../src/schema.ts";
import { discoverNativeHasher } from "../src/hasher.ts";
import { resolveB3sumArg } from "../src/cli.ts";
import { tmpTree, put, runScan, loadState, b3, quietLog, cleanupAll } from "./fixtures.ts";

afterAll(cleanupAll);

const FIXTURES = join(import.meta.dir, "fixtures");
const GOOD = join(FIXTURES, "fake-b3sum-good.ts");
const CORRUPT = join(FIXTURES, "fake-b3sum-corrupt.ts");

// ── discoverNativeHasher / resolveB3sumArg (hasher.ts, cli.ts) ───────────────────────────

test("discoverNativeHasher accepts a binary that verifies correctly", async () => {
  const hasher = await discoverNativeHasher(GOOD, quietLog);
  expect(hasher).not.toBeNull();
  expect(hasher!.path).toBe(GOOD);
});

test("discoverNativeHasher refuses a binary with a wrong digest (falls back to null, not a throw)", async () => {
  const hasher = await discoverNativeHasher(CORRUPT, quietLog);
  expect(hasher).toBeNull();
});

test("discoverNativeHasher returns null (never throws) for a nonexistent explicit path", async () => {
  const hasher = await discoverNativeHasher("/does/not/exist/b3sum", quietLog);
  expect(hasher).toBeNull();
});

test("resolveB3sumArg resolves an executable path and hard-errors on a nonexistent one", async () => {
  expect(await resolveB3sumArg(GOOD)).toBe(GOOD);
  await expect(resolveB3sumArg("/does/not/exist/b3sum")).rejects.toThrow();
});

// ── threshold routing (scanner.ts) ────────────────────────────────────────────────────────

test("a file at/above the threshold routes to native; a smaller one stays on WASM", async () => {
  const root = await tmpTree();
  await put(root, "small.txt", "tiny"); // 4 bytes, well under any sane threshold
  await put(root, "big.txt", "x".repeat(64)); // 64 bytes — "big" only relative to our tiny threshold below

  const { summary, hashCount } = await runScan(root, { b3sumPath: GOOD, nativeThresholdBytes: 10 });
  expect(summary.hashed).toBe(2); // total, either strategy
  expect(summary.hashedNative).toBe(1); // big.txt only
  expect(hashCount).toBe(1); // WASM factory.create() called once — small.txt only

  const { identities, paths } = await loadState(join(root, ".athenaeum"), root);
  const bigRef = paths.get("big.txt")!;
  expect(identities.get(identityKey(bigRef.dev, bigRef.ino))!.blake3).toBe(await b3("x".repeat(64)));
  const smallRef = paths.get("small.txt")!;
  expect(identities.get(identityKey(smallRef.dev, smallRef.ino))!.blake3).toBe(await b3("tiny"));
});

test("everything stays on WASM when no b3sum is discovered", async () => {
  const root = await tmpTree();
  await put(root, "a.txt", "x".repeat(64));

  const { summary, hashCount } = await runScan(root, { nativeThresholdBytes: 10, _noNativeHasher: true });
  expect(summary.hashedNative).toBe(0);
  expect(hashCount).toBe(1);
});

test("a b3sum that fails verification falls back to WASM for everything (no throw, hashedNative stays 0)", async () => {
  const root = await tmpTree();
  await put(root, "a.txt", "x".repeat(64));

  const { summary, hashCount } = await runScan(root, { b3sumPath: CORRUPT, nativeThresholdBytes: 10 });
  expect(summary.hashedNative).toBe(0);
  expect(summary.hashed).toBe(1);
  expect(hashCount).toBe(1);
});

// ── per-file native failure (scanner.ts) ──────────────────────────────────────────────────

test("a native hash failure for one file is a per-file skip (reason b3sum-failed), not an aborted run", async () => {
  const root = await tmpTree();
  await put(root, "boom.bin", "x".repeat(64)); // the fixture is set up to fail on this basename
  await put(root, "ok.bin", "y".repeat(64));

  const origFail = process.env.ATH_SCAN_TEST_FAIL_BASENAME;
  process.env.ATH_SCAN_TEST_FAIL_BASENAME = "boom.bin";
  let summary: Awaited<ReturnType<typeof runScan>>["summary"];
  try {
    ({ summary } = await runScan(root, { b3sumPath: GOOD, nativeThresholdBytes: 10 }));
  } finally {
    if (origFail === undefined) delete process.env.ATH_SCAN_TEST_FAIL_BASENAME;
    else process.env.ATH_SCAN_TEST_FAIL_BASENAME = origFail;
  }

  expect(summary!.skipped).toBe(1);
  expect(summary!.hashedNative).toBe(1); // ok.bin succeeded
  expect(summary!.hashed).toBe(1);

  const { identities, paths } = await loadState(join(root, ".athenaeum"), root);
  expect(paths.has("boom.bin")).toBe(true); // path row written during the walk phase regardless
  expect(paths.has("ok.bin")).toBe(true);
  const okRef = paths.get("ok.bin")!;
  expect(identities.has(identityKey(okRef.dev, okRef.ino))).toBe(true);
  const boomRef = paths.get("boom.bin")!;
  expect(identities.has(identityKey(boomRef.dev, boomRef.ino))).toBe(false); // never got an identity
});

// ── concurrency cap (scanner.ts): default 2, regardless of --concurrency ─────────────────

function maxOverlap(logPath: string): number {
  const lines = readFileSync(logPath, "utf8")
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((l) => {
      const [kind, ts] = l.split(" ");
      return { kind: kind as "start" | "end", ts: Number(ts) };
    });
  // sweep-line: sort by time, +1 on start / -1 on end (ends sorted before starts at equal ts
  // so a same-millisecond handoff isn't miscounted as overlap).
  lines.sort((a, b) => a.ts - b.ts || (a.kind === "end" ? -1 : 1));
  let cur = 0;
  let max = 0;
  for (const l of lines) {
    cur += l.kind === "start" ? 1 : -1;
    max = Math.max(max, cur);
  }
  return max;
}

test("native hashing never exceeds the concurrency cap (default 2) regardless of --concurrency", async () => {
  const root = await tmpTree();
  for (let i = 0; i < 6; i++) await put(root, `f${i}.bin`, "z".repeat(64));

  const log = join(root, "concurrency.log");
  writeFileSync(log, "");
  process.env.ATH_SCAN_TEST_CONCURRENCY_LOG = log;
  process.env.ATH_SCAN_TEST_CONCURRENCY_DELAY_MS = "120";
  try {
    await runScan(root, { b3sumPath: GOOD, nativeThresholdBytes: 10, concurrency: 8 }); // high --concurrency: must not affect the native cap
  } finally {
    delete process.env.ATH_SCAN_TEST_CONCURRENCY_LOG;
    delete process.env.ATH_SCAN_TEST_CONCURRENCY_DELAY_MS;
  }

  expect(maxOverlap(log)).toBeLessThanOrEqual(2);
  await rm(log, { force: true });
});

test("_nativeConcurrency overrides the default cap", async () => {
  const root = await tmpTree();
  for (let i = 0; i < 4; i++) await put(root, `f${i}.bin`, "z".repeat(64));

  const log = join(root, "concurrency.log");
  writeFileSync(log, "");
  process.env.ATH_SCAN_TEST_CONCURRENCY_LOG = log;
  process.env.ATH_SCAN_TEST_CONCURRENCY_DELAY_MS = "120";
  try {
    await runScan(root, { b3sumPath: GOOD, nativeThresholdBytes: 10, _nativeConcurrency: 1 });
  } finally {
    delete process.env.ATH_SCAN_TEST_CONCURRENCY_LOG;
    delete process.env.ATH_SCAN_TEST_CONCURRENCY_DELAY_MS;
  }

  expect(maxOverlap(log)).toBeLessThanOrEqual(1); // serialized: never two in flight at once
  await rm(log, { force: true });
});

