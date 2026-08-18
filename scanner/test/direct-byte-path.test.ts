// End-to-end direct byte path (v0.4.0): a scan running against a "share" tree with a fake
// resolver pointing at a shadow "backing" tree must produce a manifest byte-identical (same
// identities, same paths, same hashes) to a plain scan of the same share tree — the
// share-view-is-truth guarantee — while actually reading bytes from the backing tree
// (directReads counted). Covers both the WASM and native (b3sum) hash paths, plus the
// pin-verify fallback (mtime drift) and the mid-read retry-once (permission failure) cases.

import { test, expect, afterAll } from "bun:test";
import { join, relative } from "node:path";
import { chmod, utimes } from "node:fs/promises";
import { identityKey } from "../src/schema.ts";
import type { BytePathResolver } from "../src/bytepath.ts";
import { tmpTree, put, runScan, loadState, b3, cleanupAll } from "./fixtures.ts";

afterAll(cleanupAll);

const FIXTURES = join(import.meta.dir, "fixtures");
const GOOD = join(FIXTURES, "fake-b3sum-good.ts");

/** A fake resolver mapping every path under `shareRoot` to the identically-relative path under
 * `backingRoot`, tagged with a single element name (or per-file via `elementFor`). Mirrors the
 * real unRAID resolver's contract without touching ffi or real xattrs. */
function fakeResolver(shareRoot: string, backingRoot: string, elementFor: (rel: string) => string = () => "fake0"): BytePathResolver {
  return {
    mode: "test",
    resolve(sharePath: string) {
      const rel = relative(shareRoot, sharePath);
      return { bytePath: join(backingRoot, rel), element: elementFor(rel) };
    },
  };
}

// ── clean match: manifest identical to a plain scan, both WASM and native files ─────────────

test("identical manifest to a plain scan, reading via the resolved backing path (WASM files)", async () => {
  const base = await tmpTree();
  const share = join(base, "share");
  const backing = join(base, "backing");
  await put(share, "a.txt", "hello direct");
  await put(share, "sub/b.bin", "world, directly");
  await put(backing, "a.txt", "hello direct"); // identical bytes, share is source of truth
  await put(backing, "sub/b.bin", "world, directly");

  const resolver = fakeResolver(share, backing);
  const direct = await runScan(share, { manifestDir: join(base, "direct.athenaeum"), bytePathResolver: resolver });
  const plain = await runScan(share, { manifestDir: join(base, "plain.athenaeum") });

  expect(direct.summary.hashed).toBe(2);
  expect(direct.summary.directReads).toBe(2);
  expect(direct.summary.directFallbacks).toBe(0);

  const directState = await loadState(join(base, "direct.athenaeum"), share);
  const plainState = await loadState(join(base, "plain.athenaeum"), share);

  // Same share tree scanned twice -> identical (dev,ino) identity keys either way.
  expect(directState.identities).toEqual(plainState.identities);
  expect(directState.paths).toEqual(plainState.paths);

  const aRef = directState.paths.get("a.txt")!;
  expect(directState.identities.get(identityKey(aRef.dev, aRef.ino))!.blake3).toBe(await b3("hello direct"));
});

test("identical manifest to a plain scan via the native b3sum path too", async () => {
  const base = await tmpTree();
  const share = join(base, "share");
  const backing = join(base, "backing");
  const content = "native-direct-".repeat(20); // well above a 10-byte threshold
  await put(share, "big.bin", content);
  await put(backing, "big.bin", content);

  const resolver = fakeResolver(share, backing);
  const direct = await runScan(share, {
    manifestDir: join(base, "direct.athenaeum"),
    bytePathResolver: resolver,
    b3sumPath: GOOD,
    nativeThresholdBytes: 10,
  });

  expect(direct.summary.hashedNative).toBe(1);
  expect(direct.summary.directReads).toBe(1);
  expect(direct.summary.directFallbacks).toBe(0);

  const { identities, paths } = await loadState(join(base, "direct.athenaeum"), share);
  const ref = paths.get("big.bin")!;
  expect(identities.get(identityKey(ref.dev, ref.ino))!.blake3).toBe(await b3(content));
});

// ── pin mismatch: falls back to the share path, hash still correct from share bytes ─────────

test("backing path mtime drift on a cold scan: falls back to the share path, hash is the SHARE content, directFallbacks counted", async () => {
  const base = await tmpTree();
  const share = join(base, "share");
  const backing = join(base, "backing");
  await put(share, "a.txt", "correct share bytes", 1_700_000_000);
  // Deliberately WRONG content at the backing path, so a wrongly-trusted direct read would
  // produce a different (wrong) digest — this makes the "hash is correct" assertion meaningful.
  await put(backing, "a.txt", "STALE backing bytes!", 1_700_000_000);
  await utimes(join(backing, "a.txt"), 1_700_000_500, 1_700_000_500); // drift -> pin mismatch

  const resolver = fakeResolver(share, backing);
  const { summary, manifestDir } = await runScan(share, { bytePathResolver: resolver });

  expect(summary.hashed).toBe(1);
  expect(summary.directReads).toBe(0);
  expect(summary.directFallbacks).toBe(1);

  const { identities, paths } = await loadState(manifestDir, share);
  const ref = paths.get("a.txt")!;
  expect(identities.get(identityKey(ref.dev, ref.ino))!.blake3).toBe(await b3("correct share bytes"));
});

// ── mid-read failure: pin matches, but the read itself fails -> retry once via share path ───

test("pin matches but the backing path is unreadable mid-hash: retries once via the share path (simulated mover race)", async () => {
  const base = await tmpTree();
  const share = join(base, "share");
  const backing = join(base, "backing");
  await put(share, "a.txt", "correct share bytes", 1_700_000_000);
  await put(backing, "a.txt", "correct share bytes", 1_700_000_000); // pin matches exactly

  // lstat (the pin check) doesn't require read permission, only directory traversal — so this
  // makes the pin verify successfully, then the actual read (open+read) fail, simulating a
  // mid-hash failure (e.g. the mover relocating the file) without a real race window.
  await chmod(join(backing, "a.txt"), 0o000);

  const resolver = fakeResolver(share, backing);
  const { summary, manifestDir } = await runScan(share, { bytePathResolver: resolver });

  expect(summary.hashed).toBe(1);
  expect(summary.skipped).toBe(0); // the retry succeeded — this must NOT show up as a skip
  expect(summary.directReads).toBe(0); // reclassified: the direct attempt failed
  expect(summary.directFallbacks).toBe(1);

  const { identities, paths } = await loadState(manifestDir, share);
  const ref = paths.get("a.txt")!;
  expect(identities.get(identityKey(ref.dev, ref.ino))!.blake3).toBe(await b3("correct share bytes"));

  await chmod(join(backing, "a.txt"), 0o644); // restore so cleanup can remove the tree
});

// ── unresolvable element: falls back to the share path like any other non-direct file ───────

test("a file whose element can't be resolved hashes correctly via the share path (no crash, no false directRead)", async () => {
  const base = await tmpTree();
  const share = join(base, "share");
  await put(share, "orphan.txt", "no backing mapping for me");

  const resolver: BytePathResolver = { mode: "test", resolve: () => null };
  const { summary, manifestDir } = await runScan(share, { bytePathResolver: resolver });

  expect(summary.hashed).toBe(1);
  expect(summary.directReads).toBe(0);
  expect(summary.directFallbacks).toBe(1);

  const { identities, paths } = await loadState(manifestDir, share);
  const ref = paths.get("orphan.txt")!;
  expect(identities.get(identityKey(ref.dev, ref.ino))!.blake3).toBe(await b3("no backing mapping for me"));
});

// ── disk-aware scheduling + auto native-concurrency, end to end ─────────────────────────────

test("native queue fans out across distinct elements when a resolver is active, up to the auto-scaled concurrency", async () => {
  const base = await tmpTree();
  const share = join(base, "share");
  const backing = join(base, "backing");
  const content = "x".repeat(64);
  const elements = ["disk1", "disk2", "disk3"];
  for (const el of elements) {
    for (let i = 0; i < 2; i++) {
      await put(share, `${el}/f${i}.bin`, content);
      await put(backing, `${el}/f${i}.bin`, content);
    }
  }
  const resolver = fakeResolver(share, backing, (rel) => rel.split("/")[0]!);

  const log = join(base, "concurrency.log");
  await Bun.write(log, "");
  process.env.ATH_SCAN_TEST_CONCURRENCY_LOG = log;
  process.env.ATH_SCAN_TEST_CONCURRENCY_DELAY_MS = "100";
  let summary;
  try {
    ({ summary } = await runScan(share, {
      bytePathResolver: resolver,
      b3sumPath: GOOD,
      nativeThresholdBytes: 10,
      // native-concurrency intentionally omitted: exercises the auto-scale-to-distinct-elements path
    }));
  } finally {
    delete process.env.ATH_SCAN_TEST_CONCURRENCY_LOG;
    delete process.env.ATH_SCAN_TEST_CONCURRENCY_DELAY_MS;
  }

  expect(summary.hashedNative).toBe(6);
  expect(summary.directReads).toBe(6);

  const lines = (await Bun.file(log).text())
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((l) => {
      const [kind, ts] = l.split(" ");
      return { kind: kind as "start" | "end", ts: Number(ts) };
    });
  lines.sort((a, b) => a.ts - b.ts || (a.kind === "end" ? -1 : 1));
  let cur = 0;
  let max = 0;
  for (const l of lines) {
    cur += l.kind === "start" ? 1 : -1;
    max = Math.max(max, cur);
  }
  // 3 distinct elements with queued work -> auto native-concurrency = min(max(3,2),8) = 3, and
  // the scheduler should actually achieve that overlap (2 files per element, so no element
  // starves the others out of the first round).
  expect(max).toBe(3);
});

// ── CLI wiring (cli.ts): --byte-path validation ──────────────────────────────────────────────

const CLI = join(import.meta.dir, "..", "src", "cli.ts");

function runCli(args: string[]): { exitCode: number; stderr: string } {
  const res = Bun.spawnSync(["bun", CLI, ...args], { stdout: "pipe", stderr: "pipe" });
  return { exitCode: res.exitCode, stderr: res.stderr.toString() };
}

test("--byte-path with an unsupported mode is a usage error", async () => {
  const root = await tmpTree();
  const { exitCode, stderr } = runCli([root, "--byte-path", "nfs"]);
  expect(exitCode).toBe(1);
  expect(stderr).toContain('--byte-path must be "unraid"');
});

test("--byte-path unraid on a root outside /mnt/user/ is a usage error", async () => {
  const root = await tmpTree(); // a plain tmpdir, never under /mnt/user/
  const { exitCode, stderr } = runCli([root, "--byte-path", "unraid"]);
  expect(exitCode).toBe(1);
  expect(stderr).toContain("/mnt/user/");
});
