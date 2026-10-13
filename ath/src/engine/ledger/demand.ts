// demand.ts — demand, derived never stored (spec §9.5): a held entry wants a reading pass; an unmet `owes` wants a
// search; an unsupported claim wants a capture; a stale pass wants a re-run; an unmet `expects` is a soft lint.
import { refinesChain } from "../ontology/chain.ts";
import { collectAlong } from "../ontology/effective.ts";
import type { Ontology } from "../ontology/load.ts";
import type { Concept } from "./file.ts";
import type { Judged } from "./status.ts";

export interface Demand {
  kind: "reading" | "search" | "capture" | "rerun";
  subject: string;
  detail: string;
}

export function conceptOwes(o: Ontology, terms: readonly string[]): string[] {
  const out = new Set<string>();
  for (const t of terms) {
    if (!o.terms.has(t)) continue;
    for (const v of collectAlong<unknown>(o, refinesChain(o, t), "owes")) for (const p of Array.isArray(v) ? v : [v]) out.add(String(p));
  }
  return [...out];
}

export function demandFor(o: Ontology, c: Concept, judged: Judged[]): Demand[] {
  const out: Demand[] = [];
  for (const j of judged) {
    j.bindings.forEach((b, i) => {
      if (b.state === "held")
        out.push({ kind: "reading", subject: c.slug, detail: `${j.claim.predicate} entry ${i} is held at ${b.at}: read that unit` });
    });
    if (j.status === "unsupported") out.push({ kind: "capture", subject: c.slug, detail: `${j.claim.predicate} has no bound evidence` });
  }
  const have = new Set(judged.filter((j) => j.status !== "unsupported" && j.status !== "refuted").map((j) => j.claim.predicate));
  for (const p of conceptOwes(o, c.terms))
    if (!have.has(p)) out.push({ kind: "search", subject: c.slug, detail: `${c.terms.join("+")} owes ${p}` });
  return out;
}
