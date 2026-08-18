// The hash-phase non-TTY heartbeat cadence (scanner.ts): a line every N hashed files, plus a
// time floor so a stretch of huge files (hashed count stuck mid-file) still heartbeats. Uses
// a SpyLogger that records progress() calls with NO internal rate-limiting of its own, so
// these tests isolate the scanner's own cadence decision from Logger's 1s-min-spacing clamp
// (that clamp is covered directly in log.test.ts).

import { test, expect, afterAll } from "bun:test";
import { join } from "node:path";
import { Logger } from "../src/log.ts";
import { scan } from "../src/scanner.ts";
import { blake3Factory } from "../src/hasher.ts";
import { MANIFEST_DIRNAME } from "../src/schema.ts";
import { tmpTree, put, cleanupAll } from "./fixtures.ts";

afterAll(cleanupAll);

class SpyLogger extends Logger {
  progressCalls: string[] = [];
  constructor() {
    super("normal");
  }
  override progress(msg: string): void {
    this.progressCalls.push(msg);
  }
  override info(): void {}
  override debug(): void {}
  override warn(): void {}
  override error(): void {}
  override endProgress(): void {}
}

test("emits exactly one heartbeat every N hashed files, driven by count alone", async () => {
  const root = await tmpTree();
  for (let i = 0; i < 10; i++) await put(root, `f${i}.txt`, `content-${i}`);

  const log = new SpyLogger();
  await scan({
    root,
    manifestDir: join(root, MANIFEST_DIRNAME),
    factory: blake3Factory,
    log,
    concurrency: 4,
    _noNativeHasher: true,
    _hashProgressEvery: 3,
    _hashProgressFloorMs: 60_000, // effectively disabled — isolate the count trigger
  });

  // 10 files, every 3rd hashed file heartbeats: at hashed=3,6,9 -> exactly 3 calls, regardless
  // of which file happened to be the 3rd/6th/9th to finish (pool completion order isn't fixed).
  expect(log.progressCalls.length).toBe(3);
  for (const msg of log.progressCalls) expect(msg).toMatch(/^hash: \d+\/10 files/);
});

test("the stall floor forces a heartbeat even when the hashed count hasn't crossed N", async () => {
  const root = await tmpTree();
  // One file, large enough that hashing it takes measurably longer than the shrunk floor/tick
  // below on any reasonable host (a fast dev box hashes tens of MiB in tens of ms; 32 MiB
  // gives ample margin either way without making the test itself slow).
  await put(root, "big.bin", Buffer.alloc(32 * 1024 * 1024, 1));

  const log = new SpyLogger();
  // fixtures.ts sets ATH_SCAN_NO_TICKER=1 process-wide (other tests don't want a real ticker);
  // this specific test needs the real ticker running to observe the stall floor, so it's
  // unset just for this scan() call.
  const origNoTicker = process.env.ATH_SCAN_NO_TICKER;
  delete process.env.ATH_SCAN_NO_TICKER;
  try {
    await scan({
      root,
      manifestDir: join(root, MANIFEST_DIRNAME),
      factory: blake3Factory,
      log,
      concurrency: 1,
      _noNativeHasher: true,
      _hashProgressEvery: 1_000_000, // effectively disabled — isolate the floor trigger
      _hashProgressFloorMs: 5,
      _hashProgressTickMs: 2,
    });
  } finally {
    if (origNoTicker !== undefined) process.env.ATH_SCAN_NO_TICKER = origNoTicker;
  }

  // The count trigger can't fire (only one file, threshold absurdly high) — every emitted
  // line must have come from the stall floor. At least one is the property under test; the
  // ticker fires often enough (2ms) relative to the floor (5ms) that a hash taking any
  // meaningful time at all crosses it.
  expect(log.progressCalls.length).toBeGreaterThanOrEqual(1);
  for (const msg of log.progressCalls) expect(msg).toMatch(/^hash: \d+\/1 files/);
});

test("_hashProgressEvery/_hashProgressFloorMs default to the exported constants when unset", async () => {
  const root = await tmpTree();
  await put(root, "a.txt", "x");

  const log = new SpyLogger();
  // A single tiny file never reaches HASH_PROGRESS_EVERY (16) or the 30s floor, so no
  // heartbeat is expected at all — this just exercises the default path without overrides.
  await scan({
    root,
    manifestDir: join(root, MANIFEST_DIRNAME),
    factory: blake3Factory,
    log,
    concurrency: 1,
    _noNativeHasher: true,
  });
  expect(log.progressCalls.length).toBe(0);
});
