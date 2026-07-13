import { test, expect, afterAll } from "bun:test";
import { rename, rm, link, symlink } from "node:fs/promises";
import { join } from "node:path";
import { identityKey } from "../src/schema.ts";
import { compact } from "../src/scanner.ts";
import { tmpTree, put, runScan, loadState, b3, quietLog, cleanupAll } from "./fixtures.ts";

afterAll(cleanupAll);

test("cold pass hashes every file with correct blake3 and excludes the manifest dir", async () => {
  const root = await tmpTree();
  await put(root, "a.txt", "hello");
  await put(root, "sub/b.bin", "world!!");

  const { summary, hashCount } = await runScan(root);
  expect(summary.mode).toBe("cold");
  expect(summary.filesSeen).toBe(2);
  expect(summary.hashed).toBe(2);
  expect(hashCount).toBe(2);

  const { identities, paths } = await loadState(join(root, ".athenaeum"), root);
  expect(identities.size).toBe(2);
  expect(paths.size).toBe(2);
  for (const p of paths.keys()) expect(p.startsWith(".athenaeum")).toBe(false);

  const aRef = paths.get("a.txt")!;
  expect(identities.get(identityKey(aRef.dev, aRef.ino))!.blake3).toBe(await b3("hello"));
  const bRef = paths.get("sub/b.bin")!;
  expect(identities.get(identityKey(bRef.dev, bRef.ino))!.blake3).toBe(await b3("world!!"));
});

test("incremental re-scan hashes nothing", async () => {
  const root = await tmpTree();
  await put(root, "a.txt", "hello");
  await put(root, "b.txt", "there");
  await runScan(root);

  const { summary, hashCount } = await runScan(root);
  expect(summary.mode).toBe("incremental");
  expect(summary.hashed).toBe(0);
  expect(hashCount).toBe(0);
  expect(summary.moved).toBe(0);
  expect(summary.deleted).toBe(0);
});

test("content change (new mtime) re-hashes just that file", async () => {
  const root = await tmpTree();
  await put(root, "a.txt", "hello", 1_700_000_000);
  await put(root, "b.txt", "stable", 1_700_000_000);
  await runScan(root);

  await put(root, "a.txt", "hello, again", 1_700_000_100); // edited: new size + new mtime
  const { summary, hashCount } = await runScan(root);
  expect(summary.hashed).toBe(1);
  expect(hashCount).toBe(1);

  const { identities, paths } = await loadState(join(root, ".athenaeum"), root);
  const aRef = paths.get("a.txt")!;
  expect(identities.get(identityKey(aRef.dev, aRef.ino))!.blake3).toBe(await b3("hello, again"));
});

test("rename updates the path with zero re-hash", async () => {
  const root = await tmpTree();
  await put(root, "a.txt", "hello");
  await put(root, "b.txt", "world");
  const before = await loadState(join(root, ".athenaeum"), root);
  await runScan(root);

  await rename(join(root, "a.txt"), join(root, "c.txt"));
  const { summary, hashCount } = await runScan(root);
  expect(hashCount).toBe(0); // the property: renames never re-hash
  expect(summary.hashed).toBe(0);
  expect(summary.moved).toBe(1);
  expect(summary.deleted).toBe(1);

  const { identities, paths } = await loadState(join(root, ".athenaeum"), root);
  expect(paths.has("a.txt")).toBe(false);
  expect(paths.has("c.txt")).toBe(true);
  // identity content unchanged
  expect(identities.size).toBe(2);
  void before;
});

test("hardlinks collapse to one identity with two paths, hashed once", async () => {
  const root = await tmpTree();
  await put(root, "a.txt", "shared bytes");
  await link(join(root, "a.txt"), join(root, "a-link.txt"));

  const { summary, hashCount } = await runScan(root);
  expect(summary.filesSeen).toBe(2);
  expect(summary.hashed).toBe(1);
  expect(hashCount).toBe(1);

  const { identities, paths } = await loadState(join(root, ".athenaeum"), root);
  expect(identities.size).toBe(1);
  expect(paths.size).toBe(2);
  const r1 = paths.get("a.txt")!;
  const r2 = paths.get("a-link.txt")!;
  expect(identityKey(r1.dev, r1.ino)).toBe(identityKey(r2.dev, r2.ino));
});

test("delete drops the path immediately and the orphaned identity at compaction", async () => {
  const root = await tmpTree();
  await put(root, "a.txt", "keep");
  await put(root, "b.txt", "gone");
  await runScan(root);
  const mid = await loadState(join(root, ".athenaeum"), root);
  const bRef = mid.paths.get("b.txt")!;
  const bKey = identityKey(bRef.dev, bRef.ino);

  await rm(join(root, "b.txt"));
  const { summary } = await runScan(root);
  expect(summary.deleted).toBe(1);

  const afterScan = await loadState(join(root, ".athenaeum"), root);
  expect(afterScan.paths.has("b.txt")).toBe(false);
  expect(afterScan.identities.has(bKey)).toBe(true); // orphan still present pre-compaction

  await compact(root, join(root, ".athenaeum"), quietLog);
  const afterCompact = await loadState(join(root, ".athenaeum"), root);
  expect(afterCompact.identities.has(bKey)).toBe(false); // dropped
  expect(afterCompact.identities.size).toBe(1);
  expect(afterCompact.paths.size).toBe(1);
});

test("a killed cold pass resumes without re-hashing completed files", async () => {
  const root = await tmpTree();
  await put(root, "f1", "one");
  await put(root, "f2", "two");
  await put(root, "f3", "three");
  await put(root, "f4", "four");

  // concurrency 1 makes the fault deterministic: exactly 2 files hashed before the "kill".
  await expect(runScan(root, { concurrency: 1, _faultAfterHashes: 2 })).rejects.toThrow();
  const partial = await loadState(join(root, ".athenaeum"), root);
  expect(partial.identities.size).toBe(2);

  const { hashCount } = await runScan(root, { concurrency: 1 });
  expect(hashCount).toBe(2); // only the two that were never hashed

  const final = await loadState(join(root, ".athenaeum"), root);
  expect(final.identities.size).toBe(4);
  expect(final.paths.size).toBe(4);
});

test("snapshot round-trip preserves identities and paths", async () => {
  const root = await tmpTree();
  await put(root, "a.txt", "alpha");
  await put(root, "dir/b.txt", "beta");
  await link(join(root, "a.txt"), join(root, "a2.txt"));
  await runScan(root);

  const before = await loadState(join(root, ".athenaeum"), root);
  await compact(root, join(root, ".athenaeum"), quietLog);
  const after = await loadState(join(root, ".athenaeum"), root);

  expect(after.identities.size).toBe(before.identities.size);
  expect(after.paths.size).toBe(before.paths.size);
  for (const [k, v] of before.identities) {
    const w = after.identities.get(k)!;
    expect(w.blake3).toBe(v.blake3);
    expect(w.size).toBe(v.size);
    expect(w.mtimeNs).toBe(v.mtimeNs);
  }
  for (const [k, v] of before.paths) {
    const w = after.paths.get(k)!;
    expect(identityKey(w.dev, w.ino)).toBe(identityKey(v.dev, v.ino));
  }
});

test("symlinks are never followed or indexed", async () => {
  const root = await tmpTree();
  await put(root, "real.txt", "content");
  await symlink(join(root, "real.txt"), join(root, "link.txt"));

  const { summary } = await runScan(root);
  expect(summary.filesSeen).toBe(1);
  const { paths } = await loadState(join(root, ".athenaeum"), root);
  expect(paths.size).toBe(1);
  expect(paths.has("link.txt")).toBe(false);
});
