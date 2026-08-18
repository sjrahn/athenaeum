// The junk deny-list: a curated positive list of filesystem-metadata basenames, deliberately
// NOT "skip every hidden dotfile" — many dotfiles (.config, .gitignore, ...) are wanted
// content and must still be indexed.

import { test, expect, afterAll } from "bun:test";
import { join } from "node:path";
import { matchesIgnorePattern, isIgnoredName } from "../src/walk.ts";
import { DEFAULT_IGNORE_PATTERNS } from "../src/schema.ts";
import { tmpTree, put, runScan, loadState, cleanupAll } from "./fixtures.ts";

afterAll(cleanupAll);

test("matchesIgnorePattern: exact and trailing-* prefix forms", () => {
  expect(matchesIgnorePattern(".DS_Store", ".DS_Store")).toBe(true);
  expect(matchesIgnorePattern(".DS_Store2", ".DS_Store")).toBe(false);
  expect(matchesIgnorePattern("._foo.txt", "._*")).toBe(true);
  expect(matchesIgnorePattern(".__lock.tmp", "._*")).toBe(true); // Samba-veto-alike lock names
  expect(matchesIgnorePattern("foo._bar", "._*")).toBe(false);
});

test("default list skips junk but leaves wanted dotfiles indexed", async () => {
  const root = await tmpTree();
  await put(root, "a.txt", "visible");
  await put(root, ".config", "wanted dotfile content");
  await put(root, ".gitignore", "also wanted");
  await put(root, "._resource-fork", "AppleDouble junk");
  await put(root, ".DS_Store", "finder junk");

  const { summary } = await runScan(root);
  expect(summary.filesSeen).toBe(3); // a.txt, .config, .gitignore
  expect(summary.ignored).toBe(2); // ._resource-fork, .DS_Store

  const { paths } = await loadState(join(root, ".athenaeum"), root);
  expect(paths.has("a.txt")).toBe(true);
  expect(paths.has(".config")).toBe(true);
  expect(paths.has(".gitignore")).toBe(true);
  expect(paths.has("._resource-fork")).toBe(false);
  expect(paths.has(".DS_Store")).toBe(false);
});

test("a matched directory is pruned: its subtree is never walked", async () => {
  const root = await tmpTree();
  await put(root, "keep/a.txt", "kept");
  await put(root, "@eaDir/thumb.jpg", "synology junk"); // matched dir, exact-name pattern

  const { summary } = await runScan(root);
  expect(summary.filesSeen).toBe(1); // only keep/a.txt
  expect(summary.ignored).toBe(1); // one entry for the pruned dir itself

  const { paths } = await loadState(join(root, ".athenaeum"), root);
  expect(paths.has("keep/a.txt")).toBe(true);
  expect(paths.has("@eaDir/thumb.jpg")).toBe(false);
});

test("--ignore extends the default list", async () => {
  const root = await tmpTree();
  await put(root, "a.txt", "keep");
  await put(root, "b.custom-junk", "extra junk");

  const { summary } = await runScan(root, { ignorePatterns: ["b.custom-junk"] }); // exact-match form
  expect(summary.ignored).toBe(1);
  expect(summary.filesSeen).toBe(1);

  const { paths } = await loadState(join(root, ".athenaeum"), root);
  expect(paths.has("a.txt")).toBe(true);
  expect(paths.has("b.custom-junk")).toBe(false);
});

test("--ignore accepts a trailing-* prefix pattern, layered on top of the defaults", async () => {
  const root = await tmpTree();
  await put(root, "a.txt", "keep");
  await put(root, "cache-1.tmp", "extra junk");
  await put(root, ".DS_Store", "still caught by the built-in default");

  const { summary } = await runScan(root, { ignorePatterns: ["cache-*"] });
  expect(summary.ignored).toBe(2); // cache-1.tmp (custom) + .DS_Store (default, still active)
  expect(summary.filesSeen).toBe(1);
});

test("--no-default-ignores drops the built-ins; custom --ignore patterns still apply", async () => {
  const root = await tmpTree();
  await put(root, "a.txt", "keep");
  await put(root, ".DS_Store", "no longer caught");
  await put(root, "custom-junk.tmp", "still caught");

  const { summary } = await runScan(root, { noDefaultIgnores: true, ignorePatterns: ["custom-junk.tmp"] });
  expect(summary.ignored).toBe(1); // only custom-junk.tmp
  expect(summary.filesSeen).toBe(2); // a.txt AND .DS_Store now indexed

  const { paths } = await loadState(join(root, ".athenaeum"), root);
  expect(paths.has(".DS_Store")).toBe(true);
  expect(paths.has("custom-junk.tmp")).toBe(false);
});

test("a previously-indexed junk file disappears from paths once the deny-list catches it (deletion reconcile)", async () => {
  const root = await tmpTree();
  await put(root, "a.txt", "keep");
  await put(root, "._junk", "AppleDouble sidecar");

  // First scan with no filtering at all: the junk file gets indexed like any other file.
  const first = await runScan(root, { noDefaultIgnores: true });
  expect(first.summary.filesSeen).toBe(2);
  const before = await loadState(join(root, ".athenaeum"), root);
  expect(before.paths.has("._junk")).toBe(true);

  // Second scan with the deny-list active: the junk file is no longer "seen" this walk, so
  // it reconciles away as an ordinary deletion — no special-case cleanup required.
  const second = await runScan(root);
  expect(second.summary.ignored).toBe(1);
  expect(second.summary.deleted).toBe(1);

  const after = await loadState(join(root, ".athenaeum"), root);
  expect(after.paths.has("a.txt")).toBe(true);
  expect(after.paths.has("._junk")).toBe(false);
});

test("isIgnoredName combines the default list correctly (sanity check on the constant itself)", () => {
  expect(isIgnoredName(".DS_Store", DEFAULT_IGNORE_PATTERNS)).toBe(true);
  expect(isIgnoredName("._AnyFile", DEFAULT_IGNORE_PATTERNS)).toBe(true);
  expect(isIgnoredName("Thumbs.db", DEFAULT_IGNORE_PATTERNS)).toBe(true);
  expect(isIgnoredName("desktop.ini", DEFAULT_IGNORE_PATTERNS)).toBe(true);
  expect(isIgnoredName("@eaDir", DEFAULT_IGNORE_PATTERNS)).toBe(true);
  expect(isIgnoredName(".@__thumb", DEFAULT_IGNORE_PATTERNS)).toBe(true);
  expect(isIgnoredName(".config", DEFAULT_IGNORE_PATTERNS)).toBe(false);
  expect(isIgnoredName(".gitignore", DEFAULT_IGNORE_PATTERNS)).toBe(false);
});
