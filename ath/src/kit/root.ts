// root.ts — where the instance is: `--root`, else $ATHENAEUM_ROOT, else the nearest ancestor directory holding
// athenaeum.yaml. The kit needs it for history and locks; the engine resolves the layer chain from it.
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

export const CONFIG_FILE = "athenaeum.yaml";

export function findRoot(cwd: string, env: Record<string, string | undefined>, flag?: string): string | null {
  if (flag) return resolve(cwd, flag);
  if (env.ATHENAEUM_ROOT) return resolve(env.ATHENAEUM_ROOT);
  let d = resolve(cwd);
  for (;;) {
    if (existsSync(join(d, CONFIG_FILE))) return d;
    const up = dirname(d);
    if (up === d) return null;
    d = up;
  }
}

/** The kit's private state directory inside a layer (gitignored by `layer init`). */
export const stateDir = (root: string) => join(root, ".ath");
