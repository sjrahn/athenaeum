// verify.ts — the ledger against the corpus (spec §9.2–§9.5): every entry bound, every claim judged, demand listed,
// stale passes named. Derived, never stored; what `ath verify` and `ath lint` report.
import type { Chain } from "./layer/config.ts";
import { ArtifactCache, type BindResult, bindEntry, valueInQuote } from "./ledger/bind.ts";
import { type Demand, demandFor } from "./ledger/demand.ts";
import { type Concept, listConcepts, readConcept } from "./ledger/file.ts";
import { type Judged, judge } from "./ledger/status.ts";
import { fileLintsLedger } from "./lint/file.ts";
import type { Finding } from "./lint/report.ts";
import { refinesChain } from "./ontology/chain.ts";
import { collectAlong } from "./ontology/effective.ts";
import type { Ontology } from "./ontology/load.ts";

export interface ConceptReport {
  concept: Concept;
  judged: Judged[];
  demand: Demand[];
  findings: Finding[];
}

export interface VerifyReport {
  concepts: ConceptReport[];
  counts: {
    concepts: number;
    claims: number;
    entries: number;
    bound: number;
    held: number;
    flagged: number;
    byStatus: Record<string, number>;
  };
}

export function verifyConcept(_chain: Chain, o: Ontology, cache: ArtifactCache, c: Concept): ConceptReport {
  const findings = fileLintsLedger(c, o);
  const functional = c.terms.flatMap((t) =>
    o.terms.has(t)
      ? collectAlong<unknown>(o, refinesChain(o, t), "functional").flatMap((v) => (Array.isArray(v) ? v.map(String) : [String(v)]))
      : [],
  );
  const judged: Judged[] = [];
  for (const cl of c.claims) {
    const bindings: BindResult[] = cl.evidence.map((e) => {
      const b = bindEntry(cache, e);
      if (b.state === "bound" && !valueInQuote(cl.value, e))
        return { ...b, state: "flagged", why: "a stated value is not in its quote (D-D4)" };
      return b;
    });
    bindings.forEach((b, i) => {
      if (b.state === "flagged")
        findings.push({ code: "G4", severity: "block", subject: c.slug, at: b.at, msg: `${cl.predicate} entry ${i}: ${b.why}` });
    });
    judged.push(judge(cl, bindings, { functional, siblings: judged }));
  }
  // a second pass so earlier siblings see later ones for `conflicting`
  for (let i = 0; i < judged.length; i++) judged[i] = judge(judged[i]!.claim, judged[i]!.bindings, { functional, siblings: judged });
  return { concept: c, judged, demand: demandFor(o, c, judged), findings };
}

export function verifyLedger(chain: Chain, o: Ontology, slugs?: string[]): VerifyReport {
  const cache = new ArtifactCache(chain, o);
  const list = slugs ?? listConcepts(chain);
  const concepts: ConceptReport[] = [];
  const counts = { concepts: 0, claims: 0, entries: 0, bound: 0, held: 0, flagged: 0, byStatus: {} as Record<string, number> };
  for (const slug of list) {
    const c = readConcept(chain, slug);
    if (!c) continue;
    const r = verifyConcept(chain, o, cache, c);
    concepts.push(r);
    counts.concepts++;
    for (const j of r.judged) {
      counts.claims++;
      counts.byStatus[j.status] = (counts.byStatus[j.status] ?? 0) + 1;
      for (const b of j.bindings) {
        counts.entries++;
        counts[b.state]++;
      }
    }
  }
  return { concepts, counts };
}
