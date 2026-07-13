import { test, expect, afterAll } from "bun:test";
import { writeFile, utimes } from "node:fs/promises";
import { join } from "node:path";
import { tmpTree, put, runScan, cleanupAll } from "./fixtures.ts";

afterAll(cleanupAll);

const MT = 1_700_000_000; // whole seconds -> exact ns, so a restored mtime matches the stored tuple

test("scrub detects a silently-corrupted file (content changed, mtime and size preserved)", async () => {
  const root = await tmpTree();
  const abs = await put(root, "movie.dat", "AAAAAAAA", MT); // 8 bytes
  await runScan(root); // stores identity blake3(AAAAAAAA) at tuple (size=8, mtime=MT)

  // Simulate bit-rot / silent mutation: same length, mtime restored -> stat tuple unchanged.
  await writeFile(abs, "BBBBBBBB");
  await utimes(abs, MT, MT);

  const { summary } = await runScan(root, { scrub: 1 });
  expect(summary.scrubbed).toBe(1);
  expect(summary.corrupt).toBe(1);
});

test("scrub passes clean content", async () => {
  const root = await tmpTree();
  await put(root, "a.dat", "intact-a", MT);
  await put(root, "b.dat", "intact-b", MT);
  await runScan(root);

  const { summary } = await runScan(root, { scrub: 2 });
  expect(summary.scrubbed).toBe(2);
  expect(summary.corrupt).toBe(0);
});
