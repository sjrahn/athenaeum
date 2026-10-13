// chain.ts — a term's refines chain (single parent, no cycles) and the root it ends at.
import { AthError } from "../../kit/errors.ts";
import { linesOf, type Ontology } from "./load.ts";

/** The term and its ancestors, most specific first. */
export function refinesChain(o: Ontology, term: string): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  let t: string | undefined = term;
  while (t !== undefined) {
    if (seen.has(t)) throw new AthError("CONFIG", `ontology: refines cycle at '${t}' (${out.join(" → ")})`);
    seen.add(t);
    out.push(t);
    const parents = linesOf(o, t, "refines");
    if (parents.length > 1) throw new AthError("CONFIG", `ontology: '${t}' refines more than one term`);
    t = parents[0] ? String(parents[0].value) : undefined;
    if (t !== undefined && !o.terms.has(t)) throw new AthError("CONFIG", `ontology: '${out[out.length - 1]}' refines unknown term '${t}'`);
  }
  return out;
}

/** Whether `term` is `ancestor` or refines it, transitively. */
export function refines(o: Ontology, term: string, ancestor: string): boolean {
  return refinesChain(o, term).includes(ancestor);
}

/** Every term that refines `ancestor` (transitively), plus itself. */
export function descendants(o: Ontology, ancestor: string): string[] {
  return [...o.terms.keys()].filter((t) => refines(o, t, ancestor));
}

export const ROOT_CLASSES = ["document", "lossy", "data"] as const;
export type RootClass = (typeof ROOT_CLASSES)[number];

/** The class a term's chain reaches (spec §7.3), or null for terms outside the three roots (e.g. `unit`, `concept`). */
export function classOf(o: Ontology, term: string): RootClass | null {
  const chain = refinesChain(o, term);
  for (const c of ROOT_CLASSES) if (chain.includes(c)) return c;
  return null;
}
