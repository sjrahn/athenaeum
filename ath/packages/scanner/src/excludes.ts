// Path excludes (`--exclude <glob>`): globs over the path relative to the scanned root, beside the
// basename deny-list (walk.ts). A pattern names files or directories; a matched directory is
// pruned, its subtree never entered. A trailing `/` (or `/**`) makes a pattern name directories
// only: `downloads/` prunes the root's `downloads`, `**/incomplete/` an `incomplete` at any depth.
// `*` stays within one path segment, `**` crosses them: `*.part` is a root-level file,
// `**/*.part` one at any depth. An excluded path is never seen, so a row a previous walk indexed
// under it reconciles away as a deletion — the same as a newly ignored basename.

export interface PathExcludes {
  /** Whether the directory at `rel` (POSIX, relative to the root) is pruned. */
  dir(rel: string): boolean;
  /** Whether the file at `rel` is excluded (its ancestors are the walk's to prune). */
  file(rel: string): boolean;
  readonly patterns: readonly string[];
}

export function compileExcludes(patterns: readonly string[]): PathExcludes {
  const compiled = patterns.map((raw) => {
    let p = raw.trim().replace(/^\/+/, "");
    let dirOnly = false;
    if (p.endsWith("/**")) {
      p = p.slice(0, -3);
      dirOnly = true;
    } else if (p.endsWith("/")) {
      p = p.replace(/\/+$/, "");
      dirOnly = true;
    }
    if (!p || p.split("/").includes("..")) throw new Error(`--exclude ${JSON.stringify(raw)}: a glob relative to the root`);
    return { glob: new Bun.Glob(p), dirOnly };
  });
  return {
    patterns,
    dir: (rel) => compiled.some((c) => c.glob.match(rel)),
    file: (rel) => compiled.some((c) => !c.dirOnly && c.glob.match(rel)),
  };
}

export const NO_EXCLUDES: PathExcludes = compileExcludes([]);
