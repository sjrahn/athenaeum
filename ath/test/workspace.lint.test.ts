// workspace.lint.test.ts — the package graph, pinned: each package imports only the packages listed for it, through
// `@ath/<package>`, and no relative import leaves its package. engine and custody never import each other; the daemon
// knows kit and contracts only, and is handed the registry.
import { describe, expect, test } from "bun:test";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";

const PACKAGES = join(import.meta.dir, "..", "packages");
const ALLOWED: Record<string, string[]> = {
  contracts: [],
  kit: ["contracts"],
  engine: ["kit", "contracts"],
  custody: ["kit", "contracts"],
  scanner: ["kit"],
  verbs: ["kit", "contracts", "engine", "custody", "scanner"],
  daemon: ["kit", "contracts"],
  cli: ["kit", "contracts", "verbs", "daemon"],
};

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    if (n === "node_modules" || n === "fixtures") return [];
    return statSync(p).isDirectory() ? files(p) : p.endsWith(".ts") ? [p] : [];
  });
}

describe("workspace", () => {
  test("every package is known and imports only what it may", () => {
    const problems: string[] = [];
    for (const pkg of readdirSync(PACKAGES)) {
      const allowed = ALLOWED[pkg];
      if (!allowed) {
        problems.push(`${pkg}: not in the package graph`);
        continue;
      }
      for (const f of files(join(PACKAGES, pkg))) {
        const src = readFileSync(f, "utf8");
        for (const m of src.matchAll(/(?:from|import)\s*\(?\s*"([^"]+)"/g)) {
          const spec = m[1]!;
          const at = /^@ath\/([a-z]+)/.exec(spec);
          if (at && at[1] !== pkg && !allowed.includes(at[1]!)) problems.push(`${relative(PACKAGES, f)}: imports @ath/${at[1]}`);
          if (spec.startsWith(".") && relative(join(PACKAGES, pkg), resolve(dirname(f), spec)).startsWith(".."))
            problems.push(`${relative(PACKAGES, f)}: '${spec}' leaves the package`);
        }
      }
    }
    expect(problems).toEqual([]);
  });
});
