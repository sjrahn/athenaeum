// registry.ts — the command registry: key/alias lookup, longest-prefix word resolution, group listing.
import { AthError } from "./errors.ts";
import type { CommandDef } from "./types.ts";

export interface Registry {
  register(def: CommandDef): void;
  registerGroup(name: string, summary: string): void;
  /** Resolve leading CLI words (`["pass","sign","x"]`) by the longest dash-joined prefix that is a key or alias. */
  resolve(words: readonly string[]): { def: CommandDef; consumed: number } | null;
  /** Sorted by key. */
  list(): CommandDef[];
  groups(): { name: string; summary: string }[];
  /** Commands whose group is `name` (sorted by key). */
  inGroup(name: string): CommandDef[];
  groupOf(key: string): string;
}

export function createRegistry(): Registry {
  const byName = new Map<string, CommandDef>();
  const defs = new Map<string, CommandDef>();
  const groupSummaries = new Map<string, string>();

  const sorted = () => [...defs.values()].sort((a, b) => (a.contract.key < b.contract.key ? -1 : a.contract.key > b.contract.key ? 1 : 0));
  const groupOf = (key: string): string => {
    let best = key.split("-")[0]!;
    let len = 0;
    for (const g of groupSummaries.keys()) {
      if ((key === g || key.startsWith(`${g}-`)) && g.length > len) {
        best = g;
        len = g.length;
      }
    }
    return best;
  };

  return {
    register(def) {
      for (const name of [def.contract.key, ...(def.meta.aliases ?? [])]) {
        if (byName.has(name)) throw new AthError("INTERNAL", `registry: '${name}' is already registered`);
        byName.set(name, def);
      }
      defs.set(def.contract.key, def);
    },
    registerGroup(name, summary) {
      groupSummaries.set(name, summary);
    },
    resolve(words) {
      for (let n = words.length; n >= 1; n--) {
        const def = byName.get(words.slice(0, n).join("-"));
        if (def) return { def, consumed: n };
      }
      return null;
    },
    list: sorted,
    groups() {
      const seen = new Map<string, string>();
      for (const d of sorted()) {
        const g = groupOf(d.contract.key);
        if (!seen.has(g)) seen.set(g, groupSummaries.get(g) ?? (d.contract.key === g ? d.meta.summary : ""));
      }
      return [...seen].map(([name, summary]) => ({ name, summary }));
    },
    inGroup(name) {
      return sorted().filter((d) => groupOf(d.contract.key) === name);
    },
    groupOf,
  };
}
