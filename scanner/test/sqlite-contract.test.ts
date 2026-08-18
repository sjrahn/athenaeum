// Contract v2 specifics that don't fit scanner.test.ts's engine-behavior focus: the
// inode-migration heuristic, the publish (state.sqlite -> manifest.sqlite) protocol, and
// generation bookkeeping / the crash marker.

import { test, expect, afterAll } from "bun:test";
import { copyFile, unlink, rename, utimes, stat } from "node:fs/promises";
import { join } from "node:path";
import { Database } from "bun:sqlite";
import { identityKey, MANIFEST_DIRNAME, MANIFEST_FILENAME, STATE_FILENAME, SCHEMA_VERSION } from "../src/schema.ts";
import { tmpTree, put, runScan, loadState, cleanupAll } from "./fixtures.ts";

afterAll(cleanupAll);

const MT = 1_700_000_000;

async function pathExists(p: string): Promise<boolean> {
  try {
    await stat(p);
    return true;
  } catch {
    return false;
  }
}

test("inode migration: same path, same content/mtime, new inode -> blake3 carried forward, zero re-hash", async () => {
  const root = await tmpTree();
  const abs = await put(root, "a.txt", "stable content", MT);
  await runScan(root);

  const before = await loadState(join(root, MANIFEST_DIRNAME), root);
  const beforeRef = before.paths.get("a.txt")!;

  // Simulate an inode-changing remount (unRAID/shfs-style): copy bytes to a new inode, unlink
  // the original, move the copy back onto the same path, restore the exact mtime.
  const tmp = abs + ".migrate-tmp";
  await copyFile(abs, tmp);
  await unlink(abs);
  await rename(tmp, abs);
  await utimes(abs, MT, MT);

  const { summary, hashCount } = await runScan(root);
  expect(hashCount).toBe(0);
  expect(summary.hashed).toBe(0);
  expect(summary.migrated).toBe(1);
  expect(summary.moved).toBe(0);

  const after = await loadState(join(root, MANIFEST_DIRNAME), root);
  const afterRef = after.paths.get("a.txt")!;
  // the inode really did change (otherwise this test proves nothing)...
  expect(identityKey(afterRef.dev, afterRef.ino)).not.toBe(identityKey(beforeRef.dev, beforeRef.ino));
  // ...but the blake3 was carried forward onto the new identity without re-hashing.
  const oldIdentity = before.identities.get(identityKey(beforeRef.dev, beforeRef.ino))!;
  const newIdentity = after.identities.get(identityKey(afterRef.dev, afterRef.ino))!;
  expect(newIdentity.blake3).toBe(oldIdentity.blake3);
});

test("inode migration is skipped under --full (force re-hash ignores the heuristic)", async () => {
  const root = await tmpTree();
  const abs = await put(root, "a.txt", "stable content", MT);
  await runScan(root);

  const tmp = abs + ".migrate-tmp";
  await copyFile(abs, tmp);
  await unlink(abs);
  await rename(tmp, abs);
  await utimes(abs, MT, MT);

  const { summary, hashCount } = await runScan(root, { full: true });
  expect(summary.migrated).toBe(0);
  expect(summary.hashed).toBe(1);
  expect(hashCount).toBe(1);
});

test("publish: manifest.sqlite absent after an interrupted run, present and complete after success", async () => {
  const root = await tmpTree();
  await put(root, "f1", "one");
  await put(root, "f2", "two");
  const manifestDir = join(root, MANIFEST_DIRNAME);
  const manifestSqlitePath = join(manifestDir, MANIFEST_FILENAME);

  await expect(runScan(root, { concurrency: 1, _faultAfterHashes: 1 })).rejects.toThrow();
  expect(await pathExists(manifestSqlitePath)).toBe(false);
  expect(await pathExists(manifestSqlitePath + ".tmp")).toBe(false);

  const { summary } = await runScan(root); // resume, completes successfully
  expect(summary.hashed).toBe(2);
  expect(await pathExists(manifestSqlitePath)).toBe(true);

  // readable standalone, read-only, and contains exactly the pinned schema
  const db = new Database(manifestSqlitePath, { readonly: true, safeIntegers: true });
  try {
    const uv = db.query<{ user_version: bigint }, []>("PRAGMA user_version").get()!;
    expect(Number(uv.user_version)).toBe(SCHEMA_VERSION);

    const tables = db.query<{ name: string }, []>("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").all();
    expect(tables.map((t) => t.name)).toEqual(["events", "generations", "identities", "meta", "paths"]);

    const pathCount = db.query<{ c: bigint }, []>("SELECT COUNT(*) as c FROM paths").get()!;
    expect(Number(pathCount.c)).toBe(2);

    // The interrupted generation's row is a legitimate crash marker and travels with every
    // later publish (state.sqlite is copied whole) — a reader is expected to pick the max
    // generation with finished_at NOT NULL, not assume every row is complete.
    const gens = db.query<{ generation: bigint; finished_at: string | null }, []>("SELECT generation, finished_at FROM generations ORDER BY generation").all();
    expect(gens.length).toBe(2); // the crashed generation 1, plus the completed resume generation 2
    expect(gens[0]!.finished_at).toBeNull();
    expect(gens[1]!.finished_at).not.toBeNull();
  } finally {
    db.close();
  }
});

test("generation bookkeeping: open/close rows, crash marker NULL on an interrupted run", async () => {
  const root = await tmpTree();
  await put(root, "f1", "one");
  await put(root, "f2", "two");

  await expect(runScan(root, { concurrency: 1, _faultAfterHashes: 1 })).rejects.toThrow();

  const statePath = join(root, MANIFEST_DIRNAME, STATE_FILENAME);
  {
    const db = new Database(statePath, { readonly: true, safeIntegers: true });
    try {
      const rows = db.query<{ generation: bigint; mode: string; finished_at: string | null }, []>(
        "SELECT generation, mode, finished_at FROM generations ORDER BY generation",
      ).all();
      expect(rows.length).toBe(1);
      expect(rows[0]!.mode).toBe("cold");
      expect(rows[0]!.finished_at).toBeNull(); // the crash marker: this generation never closed
    } finally {
      db.close();
    }
  }

  await runScan(root); // resume: opens a NEW generation rather than reusing the crashed one

  {
    const db = new Database(statePath, { readonly: true, safeIntegers: true });
    try {
      const rows = db.query<{ generation: bigint; mode: string; finished_at: string | null }, []>(
        "SELECT generation, mode, finished_at FROM generations ORDER BY generation",
      ).all();
      expect(rows.length).toBe(2);
      expect(rows[0]!.finished_at).toBeNull(); // the interrupted generation stays open forever
      expect(rows[1]!.mode).toBe("incremental");
      expect(rows[1]!.finished_at).not.toBeNull();
    } finally {
      db.close();
    }
  }
});
