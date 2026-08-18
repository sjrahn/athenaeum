// The tree walk. Iterative (an explicit stack, not recursion, so a deep tree can't blow the
// call stack), lstat with { bigint: true } for an exact identity tuple, symlinks never
// followed, only regular files indexed, everything else logged-and-skipped. Manifest
// directories are infrastructure, never indexed as content: any directory literally named
// `.athenaeum`, at any depth, is excluded unconditionally (even under --full) — not just the
// current root's own manifest dir. `excludeAbs` remains for a `--manifest-dir` that lives
// under root under a name other than `.athenaeum`.

import { readdir, lstat, stat } from "node:fs/promises";
import { join, relative, sep } from "node:path";
import { DEFAULT_IGNORE_PATTERNS, MANIFEST_DIRNAME, MANIFEST_FILENAME } from "./schema.ts";

export interface FileEntry {
  kind: "file";
  relpath: string; // POSIX, relative to root
  abspath: string;
  dev: bigint;
  ino: bigint;
  size: bigint;
  mtimeNs: bigint;
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

/** A basename matched the ignore-pattern deny-list (see schema.ts's DEFAULT_IGNORE_PATTERNS):
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
): AsyncGenerator<WalkEntry> {
  const stack: string[] = [rootAbs];

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

      let st;
      try {
        st = await lstat(abs, { bigint: true });
      } catch (e) {
        yield { kind: "skip", relpath: toPosix(relative(rootAbs, abs)), abspath: abs, reason: errCode(e) };
        continue;
      }

      if (st.isSymbolicLink()) continue; // never follow; not a regular file
      if (st.isDirectory()) {
        if (isIgnoredName(name, ignorePatterns)) {
          yield { kind: "ignored", relpath: toPosix(relative(rootAbs, abs)), abspath: abs, isDir: true };
          continue; // pruned — never pushed onto the stack, subtree never entered
        }
        stack.push(abs);
        continue;
      }
      if (isIgnoredName(name, ignorePatterns)) {
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
      };
    }
  }
}
