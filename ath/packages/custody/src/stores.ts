// stores.ts — the stores an instance declares (spec §18.2): `stores/<name>.yaml` with the store's `id` (a UUID written
// into the store itself), its `driver`, its `role` (`managed`: content-addressed trees only custody writes; `observed`:
// a tree that keeps its own names, which custody reads and never writes), its `tags`, `encryption`, `capacity`,
// `evict`, `links` and declared `cost`. How this host reaches each is `$XDG_CONFIG_HOME/athenaeum/access.yaml`, by id —
// a path or a remote, credentials, and the bandwidth a transfer may take; credentials never enter a repository. The host's local store is a managed store tagged `local`, and evictable.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { AthError } from "@ath/kit/errors.ts";
import { UUID } from "@ath/kit/root.ts";

export interface StoreDecl {
  name: string;
  id: string;
  driver: "local" | "rclone";
  role: "managed" | "observed";
  tags: string[];
  encryption: "none" | "client" | "driver";
  capacity?: number;
  /** The fill level, a fraction, above which the store sheds copies its policies no longer need. */
  evict?: number;
  links?: ("reflink" | "hardlink")[];
  /** What a transfer from or to it costs, relative: the local store is 0, a store with none declared 1. */
  cost: number;
  /** The instance whose declaration this is. */
  instance?: string;
}

export interface Access {
  path?: string;
  remote?: string;
  credentials?: string;
  /** Bytes per second a transfer to or from the store may take on this host. */
  bwlimit?: number;
}

const SIZE = /^(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB|PB)?$/i;
const UNITS: Record<string, number> = { B: 1, KB: 1e3, MB: 1e6, GB: 1e9, TB: 1e12, PB: 1e15 };
export const parseSize = (s: string): number | null => {
  const m = SIZE.exec(s.trim());
  return m ? Number(m[1]) * UNITS[(m[2] ?? "B").toUpperCase()]! : null;
};

export function parseStore(name: string, text: string, where: string): StoreDecl {
  const bad = (m: string): never => {
    throw new AthError("CONFIG", `${where}: ${m}`);
  };
  let d: Record<string, unknown>;
  try {
    d = (Bun.YAML.parse(text) ?? {}) as Record<string, unknown>;
  } catch (e) {
    return bad(`does not parse: ${(e as Error).message}`);
  }
  const keys = new Set(["id", "driver", "role", "tags", "encryption", "capacity", "evict", "links", "cost"]);
  for (const k of Object.keys(d)) if (!keys.has(k)) bad(`\`${k}\` is not a key of a store`);
  if (typeof d.id !== "string" || !UUID.test(d.id)) bad("`id` is a UUID");
  if (d.driver !== "local" && d.driver !== "rclone") bad("`driver` is local or rclone");
  if (d.role !== "managed" && d.role !== "observed") bad("`role` is managed or observed");
  const tags = d.tags === undefined ? [] : d.tags;
  if (!Array.isArray(tags) || !tags.every((t) => typeof t === "string")) bad("`tags` is a list of strings");
  const enc = d.encryption ?? "none";
  if (enc !== "none" && enc !== "client" && enc !== "driver") bad("`encryption` is none, client or driver");
  const out: StoreDecl = {
    name,
    id: d.id as string,
    driver: d.driver as StoreDecl["driver"],
    role: d.role as StoreDecl["role"],
    tags: tags as string[],
    encryption: enc as StoreDecl["encryption"],
    cost: 1,
  };
  if (d.capacity !== undefined) out.capacity = parseSize(String(d.capacity)) ?? bad("`capacity` is a size: 4TB");
  if (d.evict !== undefined) out.evict = evictOf(d.evict, bad);
  if (d.links !== undefined) {
    if (!Array.isArray(d.links) || !d.links.every((l) => l === "reflink" || l === "hardlink")) bad("`links` lists reflink, hardlink");
    if (out.role !== "observed") bad("`links` belongs to an observed tree");
    out.links = d.links as StoreDecl["links"];
  }
  if (d.cost !== undefined) out.cost = typeof d.cost === "number" && d.cost >= 0 ? d.cost : bad("`cost` is a number");
  return out;
}

export function emitStore(d: StoreDecl): string {
  let out = `id: ${d.id}\ndriver: ${d.driver}\nrole: ${d.role}\ntags: [${d.tags.map((t) => JSON.stringify(t)).join(", ")}]\nencryption: ${d.encryption}\n`;
  if (d.capacity !== undefined) out += `capacity: ${d.capacity}B\n`;
  if (d.evict !== undefined) out += `evict: {above: ${Math.round(d.evict * 100)}%}\n`;
  if (d.links) out += `links: [${d.links.join(", ")}]\n`;
  if (d.cost !== 1) out += `cost: ${d.cost}\n`;
  return out;
}

/** The stores declared by every instance of a chain (`roots`, the instance pointed at first). */
export function loadStores(roots: readonly { root: string; name: string }[]): StoreDecl[] {
  const out: StoreDecl[] = [];
  for (const { root, name } of roots) {
    const dir = join(root, "stores");
    if (!existsSync(dir)) continue;
    for (const f of readdirSync(dir).sort())
      if (f.endsWith(".yaml"))
        out.push({ ...parseStore(f.slice(0, -5), readFileSync(join(dir, f), "utf8"), join(name, "stores", f)), instance: name });
  }
  return out;
}

export interface LocalDecl {
  tags: string[];
  evict?: number;
  capacity?: number;
}

const evictOf = (v: unknown, bad: (m: string) => never): number => {
  const above = (v as { above?: unknown })?.above;
  const m = typeof above === "string" ? /^(\d+(?:\.\d+)?)%$/.exec(above) : null;
  return m ? Number(m[1]) / 100 : bad("`evict` is {above: <n>%}");
};

/** This host's access file: store id → how to reach it, and `local` → what the host declares of its local store: its
 * further tags, its fill level for eviction, its capacity. */
export function loadAccess(configDir: string): { stores: Map<string, Access>; local: LocalDecl } {
  const p = join(configDir, "access.yaml");
  const stores = new Map<string, Access>();
  if (!existsSync(p)) return { stores, local: { tags: [] } };
  let d: Record<string, unknown>;
  try {
    d = (Bun.YAML.parse(readFileSync(p, "utf8")) ?? {}) as Record<string, unknown>;
  } catch (e) {
    throw new AthError("CONFIG", `${p}: ${(e as Error).message}`);
  }
  const local: LocalDecl = { tags: [] };
  const bad = (m: string): never => {
    throw new AthError("CONFIG", `${p}: local: ${m}`);
  };
  for (const [k, v] of Object.entries(d)) {
    if (k === "local") {
      const o = (v ?? {}) as { tags?: unknown; evict?: unknown; capacity?: unknown };
      for (const key of Object.keys(o)) if (!["tags", "evict", "capacity"].includes(key)) bad(`\`${key}\` is not a key of the local store`);
      if (o.tags !== undefined && (!Array.isArray(o.tags) || !o.tags.every((t) => typeof t === "string")))
        bad("`tags` is a list of strings");
      local.tags = (o.tags as string[] | undefined) ?? [];
      if (o.evict !== undefined) local.evict = evictOf(o.evict, bad);
      if (o.capacity !== undefined) local.capacity = parseSize(String(o.capacity)) ?? bad("`capacity` is a size: 500GB");
      continue;
    }
    if (!UUID.test(k)) throw new AthError("CONFIG", `${p}: \`${k}\` is not a store id`);
    const o = (v ?? {}) as Record<string, unknown>;
    for (const key of Object.keys(o))
      if (!["path", "remote", "credentials", "bwlimit"].includes(key))
        throw new AthError("CONFIG", `${p}: ${k}: \`${key}\` is not a key of a store's access`);
    if (!o.path && !o.remote) throw new AthError("CONFIG", `${p}: ${k} names no path and no remote`);
    const a: Access = {};
    for (const key of ["path", "remote", "credentials"] as const) if (o[key] !== undefined) a[key] = String(o[key]);
    if (o.bwlimit !== undefined) {
      const m = /^(.+?)\/s$/.exec(String(o.bwlimit).trim());
      const n = m ? parseSize(m[1]!) : null;
      if (!n) throw new AthError("CONFIG", `${p}: ${k}: \`bwlimit\` is a rate: 10MB/s`);
      a.bwlimit = n;
    }
    stores.set(k, a);
  }
  return { stores, local };
}

/** Write this host's access file whole: the local store's declaration, then every store by id. */
export function emitAccess(local: LocalDecl, stores: ReadonlyMap<string, Access>): string {
  let out = "";
  if (local.tags.length || local.evict !== undefined || local.capacity !== undefined) {
    out += "local:\n";
    if (local.tags.length) out += `  tags: [${local.tags.map((t) => JSON.stringify(t)).join(", ")}]\n`;
    if (local.evict !== undefined) out += `  evict: {above: ${Math.round(local.evict * 100)}%}\n`;
    if (local.capacity !== undefined) out += `  capacity: ${local.capacity}B\n`;
  }
  for (const [id, a] of [...stores].sort(([x], [y]) => (x < y ? -1 : 1))) {
    out += `${id}:\n`;
    for (const k of ["path", "remote", "credentials"] as const) if (a[k] !== undefined) out += `  ${k}: ${JSON.stringify(a[k])}\n`;
    if (a.bwlimit !== undefined) out += `  bwlimit: ${a.bwlimit}B/s\n`;
  }
  return out;
}

/** Whether a store's tags satisfy a selection of them (§18.6.3): all of `all`, one of `any`, none of `not`. */
export function tagsMatch(tags: readonly string[], w: { all?: string[]; any?: string[]; not?: string[] } | undefined): boolean {
  if (!w) return true;
  if (w.all && !w.all.every((t) => tags.includes(t))) return false;
  if (w.any && !w.any.some((t) => tags.includes(t))) return false;
  if (w.not?.some((t) => tags.includes(t))) return false;
  return true;
}
