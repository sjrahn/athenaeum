// The tree walk. Iterative (an explicit stack, not recursion, so a deep tree can't blow the
// call stack), lstat with { bigint: true } for an exact identity tuple, symlinks never
// followed, only regular files indexed, everything else logged-and-skipped. Manifest
// directories are infrastructure, never indexed as content: any directory literally named
// `.athenaeum`, at any depth, is excluded unconditionally (even under --full) — not just the
// current root's own manifest dir. `excludeAbs` remains for a `--manifest-dir` that lives
// under root under a name other than `.athenaeum`.

import { lstat, readdir, stat } from "node:fs/promises";
import { join, relative, sep } from "node:path";
import { NO_EXCLUDES, type PathExcludes } from "./excludes.ts";
import { DEFAULT_IGNORE_PATTERNS, MANIFEST_DIRNAME, MANIFEST_FILENAME } from "./schema.ts";

export interface FileEntry {
  kind: "file";
  relpath: string; // POSIX, relative to root
  abspath: string;
  dev: bigint;
  ino: bigint;
  size: bigint;
  mtimeNs: bigint;
  ctimeNs: bigint; // catalog metadata (spec/corpus.md §12.1.1 *(25)*) — raw stat ctime
  birthtimeNs: bigint; // raw stat birth time; 0n means the fs doesn't report one (caller maps to null)
  mode: bigint; // raw stat st_mode
}

export interface SkipEntry {
  kind: "skip";
  relpath: string;
  abspath: string;
  reason: string; // "eacces", "eio", "special-file", ...
}

/**
 * A directory just listed during the walk turned out to itself be a scanned root: it has a
 * `.athenaeum` subdirectory whose published `manifest.sqlite` exists. `abspath` is that
 * manifest.sqlite; `relpath` is the containing directory's path relative to our own root
 * (POSIX, "" if it IS our root) — the prefix a seeding caller must prepend to every path it
 * imports from that manifest. Always yielded before any file/dir entry from the same
 * directory listing, so a caller that seeds from it does so before classifying anything at
 * or below that directory.
 */
export interface NestedManifestEntry {
  kind: "nested-manifest";
  abspath: string;
  relpath: string;
}

/** A basename matched the ignore-pattern deny-list (see schema.ts's DEFAULT_IGNORE_PATTERNS), or the
 * path an `--exclude` glob (excludes.ts):
 * a file was skipped, or a directory was pruned (its subtree never entered). Never marked
 * seen by the caller — so a previously-indexed junk row reconciles away as a deletion on the
 * next scan, healing rows that predate the deny-list without any special-case cleanup. */
export interface IgnoredEntry {
  kind: "ignored";
  relpath: string;
  abspath: string;
  isDir: boolean;
}

export type WalkEntry = FileEntry | SkipEntry | NestedManifestEntry | IgnoredEntry;

const toPosix = (p: string): string => (sep === "/" ? p : p.split(sep).join("/"));

/** Matches a basename against one ignore pattern: a trailing `*` is a prefix match against
 * everything before it, anything else is an exact match. The default list only needs these
 * two forms, so this stays a few lines rather than pulling in a glob dependency. */
export function matchesIgnorePattern(name: string, pattern: string): boolean {
  if (pattern.endsWith("*")) return name.startsWith(pattern.slice(0, -1));
  return name === pattern;
}

/** Whether `name` matches any pattern in the (already-combined default+custom) list. */
export function isIgnoredName(name: string, patterns: readonly string[]): boolean {
  return patterns.some((p) => matchesIgnorePattern(name, p));
}

function errCode(e: unknown): string {
  const c = (e as { code?: string })?.code;
  return typeof c === "string" ? c.toLowerCase() : "eunknown";
}

async function fileExists(p: string): Promise<boolean> {
  try {
    await stat(p);
    return true;
  } catch {
    return false;
  }
}

/**
 * Walk `rootAbs`, yielding one FileEntry per regular file, one SkipEntry per
 * unreadable-or-special path, and one NestedManifestEntry the first time a `.athenaeum`
 * subdirectory with a published manifest is discovered under a listed directory (never for
 * `rootAbs`'s own manifest dir at `excludeAbs` — that's self, not a nested child). `excludeAbs`
 * (this run's own manifest dir, when it lives under root under a non-`.athenaeum` name) and
 * its subtree are omitted from content; every `.athenaeum`-named directory is omitted from
 * content unconditionally, regardless of `excludeAbs`. `ignorePatterns` (default
 * `DEFAULT_IGNORE_PATTERNS`; pass `[]` for none) is the basename deny-list: a matching file
 * yields an `IgnoredEntry` instead of a `FileEntry`, a matching directory yields one
 * `IgnoredEntry` and is never pushed onto the walk stack (subtree pruned).
 */
export async function* walkTree(
  rootAbs: string,
  excludeAbs: string | null,
  ignorePatterns: readonly string[] = DEFAULT_IGNORE_PATTERNS,
  opts: { excludes?: PathExcludes; start?: string } = {},
): AsyncGenerator<WalkEntry> {
  const excludes = opts.excludes ?? NO_EXCLUDES;
  // `start` walks one subtree of the root (a targeted run); paths stay relative to the root
  const stack: string[] = [opts.start ?? rootAbs];

  while (stack.length > 0) {
    const dir = stack.pop()!;
    let names: string[];
    try {
      names = await readdir(dir);
    } catch (e) {
      yield { kind: "skip", relpath: toPosix(relative(rootAbs, dir)), abspath: dir, reason: errCode(e) };
      continue;
    }

    if (names.includes(MANIFEST_DIRNAME)) {
      const candidate = join(dir, MANIFEST_DIRNAME);
      if (candidate !== excludeAbs) {
        const manifestSqlite = join(candidate, MANIFEST_FILENAME);
        if (await fileExists(manifestSqlite)) {
          yield { kind: "nested-manifest", abspath: manifestSqlite, relpath: toPosix(relative(rootAbs, dir)) };
        }
      }
    }

    for (const name of names) {
      const abs = join(dir, name);
      if (name === MANIFEST_DIRNAME) continue; // infrastructure, never content — unconditional
      if (excludeAbs !== null && (abs === excludeAbs || abs.startsWith(excludeAbs + sep))) continue;

      let st: import("node:fs").BigIntStats;
      try {
        st = await lstat(abs, { bigint: true });
      } catch (e) {
        yield { kind: "skip", relpath: toPosix(relative(rootAbs, abs)), abspath: abs, reason: errCode(e) };
        continue;
      }

      if (st.isSymbolicLink()) continue; // never follow; not a regular file
      if (st.isDirectory()) {
        if (isIgnoredName(name, ignorePatterns) || excludes.dir(toPosix(relative(rootAbs, abs)))) {
          yield { kind: "ignored", relpath: toPosix(relative(rootAbs, abs)), abspath: abs, isDir: true };
          continue; // pruned — never pushed onto the stack, subtree never entered
        }
        stack.push(abs);
        continue;
      }
      if (isIgnoredName(name, ignorePatterns) || excludes.file(toPosix(relative(rootAbs, abs)))) {
        yield { kind: "ignored", relpath: toPosix(relative(rootAbs, abs)), abspath: abs, isDir: false };
        continue;
      }
      if (!st.isFile()) {
        // fifo, socket, char/block device — not content we index
        yield { kind: "skip", relpath: toPosix(relative(rootAbs, abs)), abspath: abs, reason: "special-file" };
        continue;
      }

      yield {
        kind: "file",
        relpath: toPosix(relative(rootAbs, abs)),
        abspath: abs,
        dev: st.dev,
        ino: st.ino,
        size: st.size,
        mtimeNs: st.mtimeNs,
        ctimeNs: st.ctimeNs,
        birthtimeNs: st.birthtimeNs,
        mode: st.mode,
      };
    }
  }
}

/** Whether a path a targeted run was handed lies under something the walk would never enter or
 * index: a manifest directory, an ignored basename, an excluded directory, or is itself an
 * excluded file. `isDir` says what the path is now, when it exists. */
export function outsideWalk(rel: string, ignorePatterns: readonly string[], excludes: PathExcludes, isDir: boolean): boolean {
  const parts = rel.split("/");
  for (let i = 0; i < parts.length; i++) {
    const name = parts[i]!;
    if (name === MANIFEST_DIRNAME || isIgnoredName(name, ignorePatterns)) return true;
    const prefix = parts.slice(0, i + 1).join("/");
    const last = i === parts.length - 1;
    if ((!last || isDir) && excludes.dir(prefix)) return true;
  }
  return !isDir && excludes.file(rel);
}

/** The entries a targeted run classifies: each listed path (POSIX, relative to the root) as it is
 * now — a file, a directory walked as a subtree, or nothing when it is gone (the caller deletes
 * its rows and those under it). */
export async function* targetEntries(
  rootAbs: string,
  targets: readonly string[],
  excludeAbs: string | null,
  ignorePatterns: readonly string[],
  excludes: PathExcludes,
): AsyncGenerator<WalkEntry> {
  for (const rel of targets) {
    const abs = join(rootAbs, rel);
    if (excludeAbs !== null && (abs === excludeAbs || abs.startsWith(excludeAbs + sep))) continue;
    let st: import("node:fs").BigIntStats;
    try {
      st = await lstat(abs, { bigint: true });
    } catch (e) {
      if (errCode(e) !== "enoent" && errCode(e) !== "enotdir") yield { kind: "skip", relpath: rel, abspath: abs, reason: errCode(e) };
      continue;
    }
    if (outsideWalk(rel, ignorePatterns, excludes, st.isDirectory())) {
      yield { kind: "ignored", relpath: rel, abspath: abs, isDir: st.isDirectory() };
      continue;
    }
    if (st.isSymbolicLink()) continue;
    if (st.isDirectory()) {
      yield* walkTree(rootAbs, excludeAbs, ignorePatterns, { excludes, start: abs });
      continue;
    }
    if (!st.isFile()) {
      yield { kind: "skip", relpath: rel, abspath: abs, reason: "special-file" };
      continue;
    }
    yield {
      kind: "file",
      relpath: rel,
      abspath: abs,
      dev: st.dev,
      ino: st.ino,
      size: st.size,
      mtimeNs: st.mtimeNs,
      ctimeNs: st.ctimeNs,
      birthtimeNs: st.birthtimeNs,
      mode: st.mode,
    };
  }
}

/** A targeted run's list, one path per line relative to the root: blank lines dropped, `./` and
 * leading or trailing slashes trimmed, duplicates once. A path naming the root itself or leaving
 * it is refused. */
export function parseTargets(text: string): string[] {
  const out = new Set<string>();
  for (const raw of text.split("\n")) {
    const line = raw.replace(/\r$/, "");
    if (!line.trim()) continue;
    const rel = line.replace(/^(\.\/)+/, "").replace(/^\/+|\/+$/g, "");
    const parts = rel.split("/");
    if (!rel || rel === "." || parts.includes("..") || parts.includes(".") || parts.includes(""))
      throw new Error(`--paths-from: ${JSON.stringify(line)} is not a path inside the root`);
    out.add(rel);
  }
  return [...out];
}
