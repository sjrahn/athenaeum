// The tree walk. Iterative (an explicit stack, not recursion, so a deep tree can't blow the
// call stack), lstat with { bigint: true } for an exact identity tuple, symlinks never
// followed, only regular files indexed, everything else logged-and-skipped. The manifest
// directory is excluded from its own scan.

import { readdir, lstat } from "node:fs/promises";
import { join, relative, sep } from "node:path";

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

export type WalkEntry = FileEntry | SkipEntry;

const toPosix = (p: string): string => (sep === "/" ? p : p.split(sep).join("/"));

function errCode(e: unknown): string {
  const c = (e as { code?: string })?.code;
  return typeof c === "string" ? c.toLowerCase() : "eunknown";
}

/**
 * Walk `rootAbs`, yielding one FileEntry per regular file and one SkipEntry per
 * unreadable-or-special path. `excludeAbs` (the manifest dir) and its subtree are omitted.
 */
export async function* walkTree(rootAbs: string, excludeAbs: string | null): AsyncGenerator<WalkEntry> {
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

    for (const name of names) {
      const abs = join(dir, name);
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
        stack.push(abs);
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
