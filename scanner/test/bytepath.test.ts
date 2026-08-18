// Direct byte path (bytepath.ts): the unRAID resolver's path math (via the injectable xattr
// seam, no real xattrs needed), getLocationXattr's graceful null on a filesystem without the
// attribute, and planHashPath's lstat-pin verify/fallback logic.

import { test, expect, afterAll } from "bun:test";
import { join } from "node:path";
import { utimes, stat } from "node:fs/promises";
import { createUnraidResolver, getLocationXattr, planHashPath, type HashPathTarget } from "../src/bytepath.ts";
import { tmpTree, put, cleanupAll } from "./fixtures.ts";

afterAll(cleanupAll);

// ── createUnraidResolver: path math via the injectable xattr seam ───────────────────────────

test("resolves a diskN element to /mnt/<disk>/<relative path>", () => {
  const resolver = createUnraidResolver("/mnt/user/film", () => "disk7");
  const result = resolver.resolve("/mnt/user/film/subdir/movie.mkv");
  expect(result).toEqual({ bytePath: "/mnt/disk7/film/subdir/movie.mkv", element: "disk7" });
});

test("resolves a pool-name element (e.g. a cache pool) the same way as a diskN element", () => {
  const resolver = createUnraidResolver("/mnt/user/appdata", () => "warm");
  const result = resolver.resolve("/mnt/user/appdata/foo.db");
  expect(result).toEqual({ bytePath: "/mnt/warm/appdata/foo.db", element: "warm" });
});

test("resolves a file directly at the share root (no subdirectory)", () => {
  const resolver = createUnraidResolver("/mnt/user/film", () => "disk3");
  const result = resolver.resolve("/mnt/user/film/top-level.mp4");
  expect(result).toEqual({ bytePath: "/mnt/disk3/film/top-level.mp4", element: "disk3" });
});

test("returns null when the xattr reader can't resolve an element", () => {
  const resolver = createUnraidResolver("/mnt/user/film", () => null);
  expect(resolver.resolve("/mnt/user/film/a.txt")).toBeNull();
});

test("rejects a root that isn't under /mnt/user/", () => {
  expect(() => createUnraidResolver("/srv/film", () => "disk1")).toThrow(/mnt\/user/);
  expect(() => createUnraidResolver("/mnt/user", () => "disk1")).toThrow(/mnt\/user/); // /mnt/user itself, not a share under it
  expect(() => createUnraidResolver("/mnt/usershare/film", () => "disk1")).toThrow(/mnt\/user/); // prefix collision, not a real subdir
});

test("the xattr reader is called with the exact share path passed to resolve()", () => {
  const seen: string[] = [];
  const resolver = createUnraidResolver("/mnt/user/film", (p) => {
    seen.push(p);
    return "disk1";
  });
  resolver.resolve("/mnt/user/film/a/b/c.mkv");
  expect(seen).toEqual(["/mnt/user/film/a/b/c.mkv"]);
});

// ── getLocationXattr: never throws, null on a filesystem without the attribute ──────────────

test("getLocationXattr returns null (never throws) for a plain temp file with no system.LOCATION xattr", async () => {
  const root = await tmpTree();
  const abs = await put(root, "plain.txt", "no xattr here");
  expect(() => getLocationXattr(abs)).not.toThrow();
  expect(getLocationXattr(abs)).toBeNull();
});

test("getLocationXattr returns null (never throws) for a nonexistent path", () => {
  expect(() => getLocationXattr("/does/not/exist/at/all")).not.toThrow();
  expect(getLocationXattr("/does/not/exist/at/all")).toBeNull();
});

// ── planHashPath: resolve + lstat-pin verify, fall back on mismatch/failure ──────────────────

test("planHashPath with no resolver: always the share path, never direct", async () => {
  const target: HashPathTarget = { abspath: "/anything", size: 5n, mtimeNs: 123n };
  const plan = await planHashPath(undefined, target);
  expect(plan).toEqual({ path: "/anything", direct: false });
});

test("planHashPath with a resolver that can't resolve an element: falls back to the share path", async () => {
  const root = await tmpTree();
  const abs = await put(root, "a.txt", "hello");
  const resolver = createUnraidResolver("/mnt/user/x", () => null);
  const target: HashPathTarget = { abspath: abs, size: 5n, mtimeNs: 0n };
  const plan = await planHashPath(resolver, target);
  expect(plan).toEqual({ path: abs, direct: false });
});

test("planHashPath: pin matches (size + mtime_ns identical) -> direct path used", async () => {
  const root = await tmpTree();
  const share = await put(root, "share/f.bin", "shared bytes", 1_700_000_000);
  const backing = await put(root, "backing/f.bin", "shared bytes", 1_700_000_000); // same size, same mtime
  const shareSt = await stat(share, { bigint: true });

  // Fake resolver mapping the share path straight to our shadow "backing" path.
  const resolver = { mode: "test", resolve: () => ({ bytePath: backing, element: "e1" }) };
  const target: HashPathTarget = { abspath: share, size: shareSt.size, mtimeNs: shareSt.mtimeNs };
  const plan = await planHashPath(resolver, target);
  expect(plan.direct).toBe(true);
  expect(plan.path).toBe(backing);
});

test("planHashPath: pin mismatch (backing path mtime differs) -> falls back to the share path", async () => {
  const root = await tmpTree();
  const share = await put(root, "share/f.bin", "shared bytes", 1_700_000_000);
  const backing = await put(root, "backing/f.bin", "shared bytes", 1_700_000_000);
  await utimes(backing, 1_700_000_500, 1_700_000_500); // drift the backing copy's mtime
  const shareSt = await stat(share, { bigint: true });

  const resolver = { mode: "test", resolve: () => ({ bytePath: backing, element: "e1" }) };
  const target: HashPathTarget = { abspath: share, size: shareSt.size, mtimeNs: shareSt.mtimeNs };
  const plan = await planHashPath(resolver, target);
  expect(plan).toEqual({ path: share, direct: false });
});

test("planHashPath: backing path doesn't exist (lstat fails) -> falls back to the share path", async () => {
  const root = await tmpTree();
  const share = await put(root, "share/f.bin", "shared bytes", 1_700_000_000);
  const shareSt = await stat(share, { bigint: true });

  const resolver = { mode: "test", resolve: () => ({ bytePath: join(root, "nope", "gone.bin"), element: "e1" }) };
  const target: HashPathTarget = { abspath: share, size: shareSt.size, mtimeNs: shareSt.mtimeNs };
  const plan = await planHashPath(resolver, target);
  expect(plan).toEqual({ path: share, direct: false });
});

