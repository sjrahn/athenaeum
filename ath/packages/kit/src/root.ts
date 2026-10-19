// root.ts — where the instance is: `--root`, else $ATHENAEUM_ROOT, else the nearest ancestor directory holding
// athenaeum.yaml; and the instance's `id`, which names its host state (§5.6). The engine loads the rest of the file.
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

export const CONFIG_FILE = "athenaeum.yaml";
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

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

/** The `id` an instance's athenaeum.yaml declares, or null when the file is absent, unparseable or has none. */
export function instanceId(root: string): string | null {
  try {
    const doc = Bun.YAML.parse(readFileSync(join(root, CONFIG_FILE), "utf8")) as { id?: unknown } | null;
    return typeof doc?.id === "string" && UUID.test(doc.id) ? doc.id : null;
  } catch {
    return null;
  }
}
