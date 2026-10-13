// term.ts — the per-term lints (spec §13): reads satisfied, required fields present, expects met (soft), the term's
// own named lints, matches agrees with the stored root. Designators against the derivation are L7's (M3).

import type { Artifact } from "../corpus/derive.ts";
import { refinesChain } from "../ontology/chain.ts";
import { effectiveRules } from "../ontology/effective.ts";
import { linesOf } from "../ontology/load.ts";
import type { Finding } from "./report.ts";

export function termLints(a: Artifact): Finding[] {
  const out: Finding[] = [];
  const o = a.ontology;
  for (const s of a.table.scopes.values()) {
    for (const t of s.terms) {
      const r = effectiveRules(o, [t]);
      // reads satisfied: a term that reads something has a reading (stored or derived) on an asserted tree
      if (r.reads && r.reads !== "none" && a.tree === "asserted" && !s.readings.some((x) => x.aspect === r.reads) && !s.derived) {
        out.push({
          code: "T-reads",
          severity: "list",
          subject: a.blake3,
          at: s.at,
          msg: `${t} reads ${r.reads} but no reading sits here (demand)`,
        });
      }
      for (const f of r.fields) {
        if (f.required && !f.derived && s.fields[f.name] === undefined && !s.derived)
          out.push({ code: "T-field", severity: "block", subject: a.blake3, at: s.at, msg: `${t} requires field ${f.name}` });
      }
      for (const child of r.expects) {
        const manifestsChild = (w: { terms: string[] }) => w.terms.some((wt) => refinesChain(o, wt).includes(child));
        const has = s.at === "whole" ? [...a.table.scopes.values()].some(manifestsChild) : a.table.within(s.at).some(manifestsChild);
        if (!has)
          out.push({ code: "T-expects", severity: "soft", subject: a.blake3, at: s.at, msg: `${t} expects a ${child}; none manifested` });
      }
      for (const l of linesOf(o, t, "lint"))
        out.push({
          code: "T-lint",
          severity: "list",
          subject: a.blake3,
          at: s.at,
          msg: `${t}: ${String(l.value)} (named lint, not implemented)`,
        });
    }
  }
  return out;
}
