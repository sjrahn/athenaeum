// config.ts — an instance's athenaeum.yaml (spec §4.2): its id, its name, the base it extends at a pinned commit, its
// shard widths. Anything else in the file, a malformed id or commit, or a width out of range is a configuration error.
import { AthError } from "@ath/kit/errors.ts";
import { UUID } from "@ath/kit/root.ts";

export interface InstanceConfig {
  id: string;
  name: string;
  extends?: { path: string; commit: string };
  shard: { records: number; entities: number };
}

const KEYS = new Set(["id", "name", "extends", "shard"]);
const NAME = /^[a-z0-9][a-z0-9-]*$/;

export function parseConfig(text: string, where: string): InstanceConfig {
  const bad = (m: string): never => {
    throw new AthError("CONFIG", `${where}: ${m}`);
  };
  let doc: unknown;
  try {
    doc = Bun.YAML.parse(text);
  } catch (e) {
    return bad(`does not parse: ${(e as Error).message}`);
  }
  if (!doc || typeof doc !== "object" || Array.isArray(doc)) return bad("is not a mapping");
  const d = doc as Record<string, unknown>;
  for (const k of Object.keys(d)) if (!KEYS.has(k)) bad(`\`${k}\` is not a key of athenaeum.yaml`);
  if (typeof d.id !== "string" || !UUID.test(d.id)) bad("`id` is a UUID");
  if (typeof d.name !== "string" || !NAME.test(d.name)) bad("`name` is lowercase letters, digits and hyphens");
  const cfg: InstanceConfig = { id: d.id as string, name: d.name as string, shard: { records: 2, entities: 2 } };
  if (d.extends !== undefined) {
    const e = d.extends as Record<string, unknown>;
    if (!e || typeof e !== "object" || typeof e.path !== "string" || typeof e.commit !== "string" || !/^[0-9a-f]{40}$/.test(e.commit))
      bad("`extends` is {path, commit} with a 40-digit commit");
    for (const k of Object.keys(e)) if (k !== "path" && k !== "commit") bad(`extends: \`${k}\` is not a key`);
    cfg.extends = { path: e.path as string, commit: e.commit as string };
  }
  if (d.shard !== undefined) {
    const s = d.shard as Record<string, unknown>;
    if (!s || typeof s !== "object") bad("`shard` is {records, entities}");
    for (const [k, v] of Object.entries(s)) {
      if (k !== "records" && k !== "entities") bad(`shard: \`${k}\` is not a directory that shards`);
      if (typeof v !== "number" || !Number.isInteger(v) || v < 0 || v > 8) bad(`shard.${k} is a width from 0 to 8`);
      cfg.shard[k as "records" | "entities"] = v as number;
    }
  }
  return cfg;
}

/** The file in the style the tool writes it. */
export function emitConfig(c: InstanceConfig): string {
  let out = `id: ${c.id}\nname: ${c.name}\n`;
  if (c.extends) out += `extends:\n  path: ${JSON.stringify(c.extends.path)}\n  commit: ${c.extends.commit}\n`;
  out += `shard: {records: ${c.shard.records}, entities: ${c.shard.entities}}\n`;
  return out;
}
