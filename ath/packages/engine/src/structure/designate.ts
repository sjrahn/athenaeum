// designate.ts — the derived addresses (spec §7.6): positional (the positions from the root down to a scope) and
// designated (the designators the bytes print — `?sec=5&para=6` — where a form declares a designator field with the
// address key it feeds). Neither is stored; the resolver maps either to the scope's intrinsic `at`. A later key
// narrows to the earlier key's scopes' descendants; a designator whose pattern has a capture answers to the capture
// as well as to its whole value.
import { AthError } from "@ath/kit/errors.ts";
import { effectiveRules } from "../vocab/rules.ts";
import type { Vocabulary } from "../vocab/terms.ts";

type J = Record<string, unknown>;
export interface TreeScope {
  form: string | string[];
  at: string;
  scopes?: TreeScope[];
  [k: string]: unknown;
}

/** The scope at a positional address `1/3/2` (1-based), or null. */
export function byPosition(scopes: readonly TreeScope[], path: string): TreeScope | null {
  let level: readonly TreeScope[] | undefined = scopes;
  let s: TreeScope | null = null;
  for (const p of path.split("/")) {
    const i = Number(p) - 1;
    if (!Number.isInteger(i) || i < 0 || !level?.[i]) return null;
    s = level[i]!;
    level = s.scopes;
  }
  return s;
}

/** What a designator field's value answers to: the value, and its pattern's capture. */
function answers(v: Vocabulary, s: TreeScope, key: string): string[] {
  const out: string[] = [];
  for (const d of effectiveRules(v, s.form).fields as J[]) {
    if (d.type !== "designator" || d.address !== key) continue;
    const val = s[String(d.name)] ?? (s as { fields?: J }).fields?.[String(d.name)];
    if (typeof val !== "string") continue;
    out.push(val);
    if (typeof d.pattern === "string") {
      const m = new RegExp(d.pattern).exec(val);
      if (m?.[1] !== undefined) out.push(m[1]);
    }
  }
  return out;
}

/** The scopes a designated address names: `sec=5&para=6`. */
export function byDesignators(v: Vocabulary, scopes: readonly TreeScope[], query: string): TreeScope[] {
  let pool: TreeScope[] = [];
  const walk = (xs: readonly TreeScope[] | undefined, f: (s: TreeScope) => void) => {
    for (const s of xs ?? []) {
      f(s);
      walk(s.scopes, f);
    }
  };
  walk(scopes, (s) => pool.push(s));
  for (const part of query.split("&")) {
    const [k, val] = part.split("=") as [string, string | undefined];
    if (!k || val === undefined) throw new AthError("USAGE", `'${part}' is not key=value`);
    const hit = pool.filter((s) => answers(v, s, k).includes(val));
    pool = [];
    for (const h of hit) walk(h.scopes, (s) => pool.push(s));
    if (part === query.split("&").at(-1)) return hit;
  }
  return [];
}
