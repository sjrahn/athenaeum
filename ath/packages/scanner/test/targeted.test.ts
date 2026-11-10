// The runs a deployment that follows its share as it changes needs: a targeted update of listed
// paths, a dry run that writes nothing, the deletion breaker, path excludes, the run lock and the
// status file.

import { Database } from "bun:sqlite";
import { afterAll, describe, expect, test } from "bun:test";
import { mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import { hostname } from "node:os";
import { join } from "node:path";
import { compileExcludes } from "../src/excludes.ts";
import { blake3Factory } from "../src/hasher.ts";
import { acquireScanLock, LOCK_FILENAME, ScanBusy } from "../src/lock.ts";
import { DeletionRefused, dryRun, publishPending } from "../src/scanner.ts";
import { MANIFEST_DIRNAME, MANIFEST_FILENAME } from "../src/schema.ts";
import { StatusFile } from "../src/status.ts";
import { parseTargets } from "../src/walk.ts";
import { b3, cleanupAll, loadState, put, quietLog, runScan, tmpTree } from "./fixtures.ts";

afterAll(cleanupAll);

const published = (root: string) => {
  const db = new Database(join(root, MANIFEST_DIRNAME, MANIFEST_FILENAME), { readonly: true });
  try {
    const gen = (db.query("SELECT MAX(generation) AS g FROM generations WHERE finished_at IS NOT NULL").get() as { g: number }).g;
    const paths = (db.query("SELECT path FROM paths ORDER BY path").all() as { path: string }[]).map((r) => r.path);
    return { gen, paths };
  } finally {
    db.close();
  }
};

async function tree(n: number): Promise<string> {
  const root = await tmpTree();
  for (let i = 0; i < n; i++) await put(root, `d${i % 3}/f${i}.txt`, `file ${i}\n`);
  return root;
}

describe("the deletion breaker", () => {
  test("refuses a generation deleting more than its share, keeping nothing of the walk; --allow-deletions accepts it", async () => {
    const root = await tree(40);
    await runScan(root);
    const before = await loadState(join(root, MANIFEST_DIRNAME), root);
    await rm(join(root, "d0"), { recursive: true }); // a third of the files, as when a disk drops out
    await put(root, "new.txt", "arrived while the disk was gone\n");
    await expect(runScan(root, { _deleteFloor: 0 })).rejects.toBeInstanceOf(DeletionRefused);
    const after = await loadState(join(root, MANIFEST_DIRNAME), root);
    expect(after.paths).toEqual(before.paths);
    expect(after.generation).toBe(before.generation);
    expect(published(root).gen).toBe(1);
    // under the floor, or past the limit by leave, the run goes through
    expect((await runScan(root, { _deleteFloor: 1000 })).summary.deleted).toBe(14);
  });

  test("an operator's leave", async () => {
    const root = await tree(40);
    await runScan(root);
    await rm(join(root, "d1"), { recursive: true });
    const r = await runScan(root, { _deleteFloor: 0, allowDeletions: true });
    expect(r.summary.deleted).toBe(13);
    expect(published(root).paths).not.toContain("d1/f1.txt");
  });
});

describe("a dry run", () => {
  test("reports what the run would hash, move and delete, and writes nothing", async () => {
    const root = await tree(9);
    await runScan(root);
    const before = await loadState(join(root, MANIFEST_DIRNAME), root);
    await put(root, "d0/f0.txt", "changed\n", 1_700_000_100);
    await put(root, "added.txt", "new\n");
    await rename(join(root, "d1/f1.txt"), join(root, "moved.txt"));
    await rm(join(root, "d2/f2.txt"));
    const r = await dryRun({ root, manifestDir: join(root, MANIFEST_DIRNAME), factory: blake3Factory, log: quietLog, _deleteFloor: 0 });
    expect(r).toMatchObject({
      dryRun: true,
      mode: "incremental",
      toHash: 2,
      moved: 1,
      deleted: 2,
      deletedPrior: 2,
      prior: 9,
      refused: true,
    });
    expect(await loadState(join(root, MANIFEST_DIRNAME), root)).toEqual(before);
    expect(published(root).gen).toBe(1);
    // the scan it stands for does what it said
    const run = await runScan(root, { allowDeletions: true });
    expect([run.hashCount, run.summary.moved, run.summary.deleted]).toEqual([2, 1, 2]);
  });

  test("a seeded carry-over is confirmed before anything is hashed", async () => {
    const root = await tree(6);
    await runScan(root, { manifestDir: join(root, "..", `${root.split("/").pop()}-old`) });
    const r = await dryRun({
      root,
      manifestDir: join(root, MANIFEST_DIRNAME),
      factory: blake3Factory,
      log: quietLog,
      seedFrom: [join(root, "..", `${root.split("/").pop()}-old`, MANIFEST_FILENAME)],
    });
    expect(r).toMatchObject({ mode: "cold", seeded: 6, toHash: 0, deleted: 0 });
    expect((await loadState(join(root, MANIFEST_DIRNAME), root)).paths.size).toBe(0);
  });
});

describe("a targeted run", () => {
  test("brings the listed paths up to date: created, changed, deleted, renamed and a directory moved", async () => {
    const root = await tree(9);
    await runScan(root);
    await put(root, "created.txt", "created\n");
    await put(root, "d0/f3.txt", "changed\n", 1_700_000_200);
    await rm(join(root, "d0/f6.txt"));
    await rename(join(root, "d1/f4.txt"), join(root, "d1/renamed.txt"));
    await rename(join(root, "d2"), join(root, "d2-moved"));
    const targets = ["created.txt", "d0/f3.txt", "d0/f6.txt", "d1/f4.txt", "d1/renamed.txt", "d2", "d2-moved"];
    const r = await runScan(root, { targets });
    expect(r.summary).toMatchObject({ mode: "targeted", generation: 2, deleted: 5, moved: 4 });
    expect(r.hashCount).toBe(2);
    // a full walk now finds nothing left to do
    const check = await runScan(root);
    expect([check.hashCount, check.summary.moved, check.summary.deleted]).toEqual([0, 0, 0]);
    const paths = published(root).paths;
    expect(paths).toContain("d2-moved/f5.txt");
    expect(paths.some((p) => p.startsWith("d2/"))).toBe(false);
    const state = await loadState(join(root, MANIFEST_DIRNAME), root);
    const created = state.paths.get("created.txt")!;
    expect(state.identities.get(`${created.dev}:${created.ino}`)!.blake3).toBe(await b3("created\n"));
  });

  test("records without publishing; a publish then carries what accumulated, once", async () => {
    const root = await tree(3);
    await runScan(root);
    await put(root, "a.txt", "a\n");
    await runScan(root, { targets: ["a.txt"], publish: false });
    await put(root, "b.txt", "b\n");
    await runScan(root, { targets: ["b.txt"], publish: false });
    expect(published(root)).toMatchObject({ gen: 1 });
    expect(await publishPending(root, join(root, MANIFEST_DIRNAME), quietLog)).toBe(3);
    expect(published(root).paths).toEqual(expect.arrayContaining(["a.txt", "b.txt"]));
    expect(await publishPending(root, join(root, MANIFEST_DIRNAME), quietLog)).toBeNull();
  });

  test("needs a manifest a full scan began, and a list of paths inside the root", async () => {
    const root = await tree(2);
    await expect(runScan(root, { targets: ["d0/f0.txt"] })).rejects.toThrow(/full scan/);
    expect(parseTargets("./a/b.txt\r\n\nc/\na/b.txt\n")).toEqual(["a/b.txt", "c"]);
    for (const bad of ["../x", "a/../b", ".", "/"]) expect(() => parseTargets(bad)).toThrow(/inside the root/);
  });
});

describe("path excludes", () => {
  test("globs over the path relative to the root; a matched directory is pruned", () => {
    const x = compileExcludes(["downloads/", "**/incomplete/**", "**/*.part", "tmp"]);
    expect([x.dir("downloads"), x.dir("a/downloads"), x.dir("a/incomplete"), x.dir("incomplete"), x.dir("tmp")]).toEqual([
      true,
      false,
      true,
      true,
      true,
    ]);
    expect([x.file("downloads"), x.file("a/b.part"), x.file("b.part"), x.file("tmp"), x.file("a/b.txt")]).toEqual([
      false,
      true,
      true,
      true,
      false,
    ]);
    expect(() => compileExcludes(["../x"])).toThrow();
  });

  test("honoured by the walk and by a targeted run; what was indexed under them is dropped", async () => {
    const root = await tree(3);
    await put(root, "downloads/big.iso", "partial\n");
    await put(root, "media/film.mkv.part", "partial\n");
    await runScan(root);
    expect(published(root).paths).toContain("downloads/big.iso");
    const excludes = ["downloads/", "**/*.part"];
    const r = await runScan(root, { excludes });
    expect(r.summary.deleted).toBe(2);
    expect(published(root).paths).not.toContain("downloads/big.iso");
    expect(published(root).paths).not.toContain("media/film.mkv.part");
    await put(root, "downloads/other.iso", "partial\n");
    await put(root, "media/next.part", "partial\n");
    const t = await runScan(root, { excludes, targets: ["downloads/other.iso", "media/next.part", "downloads"] });
    expect([t.hashCount, t.summary.ignored]).toEqual([0, 3]);
  });
});

describe("the run lock", () => {
  test("a second scan of the same manifest stops; a lock its dead holder left is taken over", async () => {
    const root = await tree(2);
    await runScan(root);
    const dir = join(root, MANIFEST_DIRNAME);
    const release = acquireScanLock(dir);
    await expect(runScan(root)).rejects.toBeInstanceOf(ScanBusy);
    await expect(publishPending(root, dir, quietLog)).rejects.toBeInstanceOf(ScanBusy);
    release();
    const dead = Bun.spawnSync(["true"]).pid;
    await writeFile(join(dir, LOCK_FILENAME), JSON.stringify({ pid: dead, host: hostname() }));
    expect((await runScan(root)).summary.generation).toBe(2);
    await expect(readFile(join(dir, LOCK_FILENAME))).rejects.toThrow();
  });
});

describe("the status file", () => {
  test("says where a run is, and how it ended", async () => {
    const root = await tree(3);
    await mkdir(join(root, "..", "status"), { recursive: true });
    const path = join(root, "..", "status", `${root.split("/").pop()}.json`);
    await runScan(root, { status: new StatusFile(path, { root }) });
    const s = JSON.parse(await readFile(path, "utf8"));
    expect(s).toMatchObject({ root, phase: "done", mode: "cold", generation: 1, filesSeen: 3, toHash: 3, published: true });
    expect(s.summary.hashed).toBe(3);
    expect(Object.keys(s).sort()).toEqual(
      [
        "root",
        "phase",
        "mode",
        "generation",
        "dryRun",
        "pid",
        "host",
        "started_at",
        "updated_at",
        "filesSeen",
        "toHash",
        "bytesToHash",
        "hashed",
        "bytesHashed",
        "published",
        "summary",
        "error",
      ].sort(),
    );
    expect([s.hashed, s.bytesHashed, s.error]).toEqual([3, s.summary.bytesHashed, null]);
    await rm(join(root, "d0"), { recursive: true });
    await expect(runScan(root, { status: new StatusFile(path, { root }), _deleteFloor: 0 })).rejects.toBeInstanceOf(DeletionRefused);
    expect(JSON.parse(await readFile(path, "utf8"))).toMatchObject({ phase: "refused" });
  });
});
