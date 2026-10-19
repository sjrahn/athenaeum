// rules.ts — a scope's effective rules (spec §11.3): the union of its forms' `refines` chains and its ancestors'
// conventions down the tree, under the artifact's shape and its chain. Where two terms declare the same expectation
// the most specific wins; a form with no `renders` renders as its parent's.
import { all, one, refinesChain } from "./load.ts";
import type { Vocabulary } from "./terms.ts";

type J = Record<string, unknown>;

export interface Rules {
  forms: string[];
  reads: string | null;
  fields: J[];
  expects: string[];
  conventions: J[];
  renders: J | null;
  checks: J[];
  surface: string | null;
}

/** The rules of a scope of `forms`, inheriting `conventions` from its ancestors, under `shape`. */
export function effectiveRules(v: Vocabulary, forms: string | string[], inherited: readonly J[] = [], shape?: string | null): Rules {
  const list = [forms].flat();
  const chains = list.map((f) => refinesChain(v, "forms", f));
  const first = <T>(pick: (f: string) => T | undefined): T | null => {
    for (const ch of chains)
      for (const f of ch) {
        const x = pick(f);
        if (x !== undefined) return x;
      }
    return null;
  };
  const fields = new Map<string, J>();
  for (const ch of chains)
    for (const f of ch) for (const d of all(v.forms.get(f), "field") as J[]) if (!fields.has(String(d.name))) fields.set(String(d.name), d);
  const conventions = [...inherited];
  const seen = new Set(inherited.map((c) => Object.keys(c)[0]));
  for (const ch of chains)
    for (const f of ch)
      for (const c of all(v.forms.get(f), "convention") as J[]) {
        const k = Object.keys(c)[0];
        if (!seen.has(k)) {
          seen.add(k);
          conventions.push(c);
        }
      }
  let surface: string | null = null;
  if (shape)
    for (const s of refinesChain(v, "shapes", shape)) {
      const line = (all(v.shapes.get(s), "surface") as J[]).find((x) => chains.some((ch) => ch.includes(String(x.form))));
      if (line) {
        surface = String(line.op);
        break;
      }
    }
  return {
    forms: list,
    reads: first((f) => one(v.forms.get(f), "reads") as string | undefined),
    fields: [...fields.values()],
    expects: [...new Set(chains.flatMap((ch) => ch.flatMap((f) => (one(v.forms.get(f), "expects") as string[] | undefined) ?? [])))],
    conventions,
    renders: first((f) => one(v.forms.get(f), "renders") as J | undefined),
    checks: chains.flatMap((ch) => ch.flatMap((f) => all(v.forms.get(f), "check") as J[])),
    surface,
  };
}
