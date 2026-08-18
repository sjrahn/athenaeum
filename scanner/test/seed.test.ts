// Manifest seeding: nested `.athenaeum` exclusion (unconditional), auto-seed from a nested
// child root's manifest (default; disabled under --full), and explicit --seed-from. See the
// "subdir-scanned-first, root-scanned-later" section of README.md for the workflow this
// supports.

import { test, expect, afterAll } from "bun:test";
import { Database } from "bun:sqlite";
import { join } from "node:path";
import { identityKey, MANIFEST_DIRNAME } from "../src/schema.ts";
import { resolveSeedFromArg, assertNoSeedFromWithFull } from "../src/cli.ts";
import { tmpTree, put, runScan, loadState, b3, cleanupAll } from "./fixtures.ts";

afterAll(cleanupAll);

const MT = 1_700_000_000;

// ── nested .athenaeum exclusion ─────────────────────────────────────────────────────────

test("nested .athenaeum is never indexed as content on a normal parent scan", async () => {
  const root = await tmpTree();
  const childRoot = join(root, "child");
  await put(childRoot, "a.txt", "alpha");
  await runScan(childRoot);

  await runScan(root);
  const { paths } = await loadState(join(root, MANIFEST_DIRNAME), root);
  for (const p of paths.keys()) expect(p.includes(MANIFEST_DIRNAME)).toBe(false);
});

test("nested .athenaeum is never indexed as content even under --full (auto-seed disabled, exclusion still holds)", async () => {
  const root = await tmpTree();
  const childRoot = join(root, "child");
  await put(childRoot, "a.txt", "alpha");
  await runScan(childRoot);

  const { summary, hashCount } = await runScan(root, { full: true });
  expect(summary.seeded).toBe(0); // auto-seed disabled under --full
  expect(hashCount).toBe(1); // child/a.txt is re-hashed itself (seeding disabled)...
  const { paths } = await loadState(join(root, MANIFEST_DIRNAME), root);
  for (const p of paths.keys()) expect(p.includes(MANIFEST_DIRNAME)).toBe(false); // ...but never the manifest dir's own files
});

// ── auto-seed from a nested child root ──────────────────────────────────────────────────

test("subdir scanned first, then parent: parent hashes zero files covered by the child manifest, seeded > 0, reader join covers all paths with correct blake3s", async () => {
  const root = await tmpTree();
  const childRoot = join(root, "child");
  await put(childRoot, "a.txt", "alpha");
  await put(childRoot, "sub/b.txt", "beta");
  await runScan(childRoot); // child scanned first, independently

  await put(root, "top.txt", "top-level"); // parent must still hash its own file

  const { summary, hashCount } = await runScan(root);
  expect(summary.mode).toBe("cold");
  expect(hashCount).toBe(1); // only top.txt; child's files adopted from the seed
  expect(summary.hashed).toBe(1);
  expect(summary.seeded).toBe(2); // a.txt + sub/b.txt identities

  const { identities, paths } = await loadState(join(root, MANIFEST_DIRNAME), root);
  expect(paths.has("child/a.txt")).toBe(true);
  expect(paths.has("child/sub/b.txt")).toBe(true);
  expect(paths.has("top.txt")).toBe(true);

  const aRef = paths.get("child/a.txt")!;
  expect(identities.get(identityKey(aRef.dev, aRef.ino))!.blake3).toBe(await b3("alpha"));
  const bRef = paths.get("child/sub/b.txt")!;
  expect(identities.get(identityKey(bRef.dev, bRef.ino))!.blake3).toBe(await b3("beta"));
});

test("a file changed after the child scan: parent re-hashes exactly that file", async () => {
  const root = await tmpTree();
  const childRoot = join(root, "child");
  await put(childRoot, "a.txt", "alpha", MT);
  await put(childRoot, "b.txt", "beta", MT);
  await runScan(childRoot);

  await put(childRoot, "a.txt", "alpha-changed", MT + 100); // edited after the child's own scan

  const { summary, hashCount } = await runScan(root);
  expect(hashCount).toBe(1);
  expect(summary.hashed).toBe(1);

  const { identities, paths } = await loadState(join(root, MANIFEST_DIRNAME), root);
  const aRef = paths.get("child/a.txt")!;
  expect(identities.get(identityKey(aRef.dev, aRef.ino))!.blake3).toBe(await b3("alpha-changed"));
  const bRef = paths.get("child/b.txt")!;
  expect(identities.get(identityKey(bRef.dev, bRef.ino))!.blake3).toBe(await b3("beta")); // untouched: seeded, zero re-hash
});

test("existing-identity precedence: the parent's own identity is not overwritten by a stale seed row for the same (dev,ino)", async () => {
  const root = await tmpTree();
  const childRoot = join(root, "child");
  await put(childRoot, "a.txt", "alpha", MT);
  await runScan(childRoot);
  await runScan(root); // parent scans first, independently — records the correct blake3 itself

  const before = await loadState(join(root, MANIFEST_DIRNAME), root);
  const aRef = before.paths.get("child/a.txt")!;
  const correctBlake3 = before.identities.get(identityKey(aRef.dev, aRef.ino))!.blake3;
  expect(correctBlake3).toBe(await b3("alpha"));

  // Corrupt the child's PUBLISHED manifest to claim a bogus blake3 for the same (dev,ino).
  const manifestSqlite = join(childRoot, MANIFEST_DIRNAME, "manifest.sqlite");
  const db = new Database(manifestSqlite);
  db.run("UPDATE identities SET blake3 = 'bogus-stale-blake3'");
  db.close();

  // child/a.txt is unchanged on disk, so the parent's incremental walk still re-encounters
  // and re-attempts the (now-corrupted) nested seed every run — INSERT OR IGNORE must lose.
  const { summary, hashCount } = await runScan(root);
  expect(hashCount).toBe(0);
  expect(summary.seeded).toBe(0); // the seed row was ignored, not adopted
  const after = await loadState(join(root, MANIFEST_DIRNAME), root);
  const afterIdentity = after.identities.get(identityKey(aRef.dev, aRef.ino))!;
  expect(afterIdentity.blake3).toBe(correctBlake3);
  expect(afterIdentity.blake3).not.toBe("bogus-stale-blake3");
});

test("auto-seed skips a nested manifest with a schema version mismatch (warns, scans its files normally)", async () => {
  const root = await tmpTree();
  const childRoot = join(root, "child");
  await put(childRoot, "a.txt", "alpha");
  await runScan(childRoot);

  const manifestSqlite = join(childRoot, MANIFEST_DIRNAME, "manifest.sqlite");
  const db = new Database(manifestSqlite);
  db.run("PRAGMA user_version = 99");
  db.close();

  const { summary, hashCount } = await runScan(root); // must not throw
  expect(hashCount).toBe(1); // a.txt scanned normally, not seeded
  expect(summary.seeded).toBe(0);
});

// ── explicit --seed-from ────────────────────────────────────────────────────────────────

test("explicit --seed-from (manifest.sqlite file path) avoids re-hash for identical (dev,ino) files", async () => {
  const root = await tmpTree();
  const externalManifestDir = join(await tmpTree(), "manifest"); // lives entirely outside root
  await put(root, "a.txt", "alpha");
  await runScan(root, { manifestDir: externalManifestDir });

  const manifestSqlite = join(externalManifestDir, "manifest.sqlite");
  const { summary, hashCount } = await runScan(root, { seedFrom: [manifestSqlite] }); // fresh default .athenaeum this time
  expect(hashCount).toBe(0); // a.txt's identity was seeded before the walk classified it
  expect(summary.seeded).toBeGreaterThan(0);
});

test("--seed-from is repeatable: each source's identities are imported", async () => {
  const root = await tmpTree();
  const extBase = await tmpTree();
  const srcA = join(extBase, "a");
  const srcB = join(extBase, "b");
  await put(srcA, "x.txt", "xxx");
  await put(srcB, "y.txt", "yyy");
  await runScan(srcA);
  await runScan(srcB);

  const { summary } = await runScan(root, {
    seedFrom: [join(srcA, MANIFEST_DIRNAME, "manifest.sqlite"), join(srcB, MANIFEST_DIRNAME, "manifest.sqlite")],
  });
  expect(summary.seeded).toBe(2); // one identity adopted from each source
});

test("explicit --seed-from hard-errors on a schema version mismatch", async () => {
  const root = await tmpTree();
  const badDir = await tmpTree();
  const badPath = join(badDir, "bad-manifest.sqlite");
  const db = new Database(badPath, { create: true });
  db.run("PRAGMA user_version = 99");
  db.close();

  await expect(runScan(root, { seedFrom: [badPath] })).rejects.toThrow();
});

// ── CLI arg resolution/validation (pure functions, unit-tested directly) ─────────────────

test("resolveSeedFromArg: file path and directory forms, nonexistent path, directory missing a manifest", async () => {
  const root = await tmpTree();
  await put(root, "a.txt", "alpha");
  await runScan(root);

  const manifestSqlite = join(root, MANIFEST_DIRNAME, "manifest.sqlite");
  expect(await resolveSeedFromArg(manifestSqlite)).toBe(manifestSqlite);
  expect(await resolveSeedFromArg(root)).toBe(manifestSqlite); // directory form

  const emptyDir = await tmpTree();
  await expect(resolveSeedFromArg(emptyDir)).rejects.toThrow();
  await expect(resolveSeedFromArg(join(root, "does-not-exist"))).rejects.toThrow();
});

test("assertNoSeedFromWithFull throws only when both --seed-from and --full are set", () => {
  expect(() => assertNoSeedFromWithFull(["x"], true)).toThrow();
  expect(() => assertNoSeedFromWithFull(["x"], false)).not.toThrow();
  expect(() => assertNoSeedFromWithFull(undefined, true)).not.toThrow();
  expect(() => assertNoSeedFromWithFull([], true)).not.toThrow();
});
