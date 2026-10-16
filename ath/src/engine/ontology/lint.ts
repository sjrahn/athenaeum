// lint.ts — ontology-level checks: every refines resolves without a cycle; repeatable predicates key uniquely;
// a `reads` value is one of the four; a `concept` map's selectors are also `select` lines (D-F7); a `matches`
// declares at least a mime; a `field` parses; a `derivation` names an op of this engine (D-derivation).
import { parseOpRef } from "../model/line.ts";
import { ConceptDecl, FieldDecl, MatchesDecl, READS, REPEATABLE } from "../model/term.ts";
import { argProblem, opFor, opNames } from "../ops/index.ts";
import { refinesChain } from "./chain.ts";
import { duplicateIdentities } from "./hash.ts";
import { linesOf, type Ontology } from "./load.ts";

export interface OntologyFinding {
  term: string;
  code: string;
  msg: string;
}

export function lintOntology(o: Ontology): OntologyFinding[] {
  const out: OntologyFinding[] = [];
  for (const term of o.terms.keys()) {
    try {
      refinesChain(o, term);
    } catch (e) {
      out.push({ term, code: "O1-refines", msg: (e as Error).message });
    }
    const single = new Map<string, number>();
    for (const l of linesOf(o, term)) {
      if (!REPEATABLE.has(l.predicate)) single.set(l.predicate, (single.get(l.predicate) ?? 0) + 1);
    }
    for (const [p, n] of single) if (n > 1) out.push({ term, code: "O2-repeat", msg: `'${p}' appears ${n} times but is single-valued` });
    for (const l of linesOf(o, term, "reads"))
      if (!READS.includes(l.value as never))
        out.push({ term, code: "O3-reads", msg: `reads must be one of ${READS.join(", ")}: ${JSON.stringify(l.value)}` });
    for (const l of linesOf(o, term, "field")) {
      const r = FieldDecl.safeParse(l.value);
      if (!r.success) out.push({ term, code: "O4-field", msg: `field does not parse: ${JSON.stringify(l.value)}` });
    }
    for (const l of linesOf(o, term, "matches")) {
      const r = MatchesDecl.safeParse(l.value);
      if (!r.success || !(r.data.mime || r.data.magic))
        out.push({ term, code: "O5-matches", msg: `matches needs a mime or a magic: ${JSON.stringify(l.value)}` });
    }
    const looksSelector = (src: string) => /[#[\]]/.test(src) || (/\./.test(src) && !/^[a-z_][a-z0-9_-]*\.[a-z_][a-z0-9_-]*$/.test(src));
    for (const l of linesOf(o, term, "concept")) {
      const r = ConceptDecl.safeParse(l.value);
      if (!r.success) {
        out.push({ term, code: "O6-concept", msg: `concept does not parse: ${JSON.stringify(l.value)}` });
        continue;
      }
      if (!o.terms.has(r.data.term)) out.push({ term, code: "O6-concept", msg: `concept term '${r.data.term}' is not in the ontology` });
      const refs: [string, string][] = Object.entries(r.data.claims).flatMap(([k, v]) =>
        typeof v === "string" ? [[k, v] as [string, string]] : [],
      );
      if (r.data.key) refs.push(["key", r.data.key]);
      for (const [pred, src] of refs) {
        const target = src.split("→")[0]!.trim();
        if (target.startsWith("@") || target === "*") continue;
        if (looksSelector(target))
          out.push({
            term,
            code: "O7-concept-select",
            msg: `concept map '${pred}' names a selector '${target}'; name a term and put the selector on a select line`,
          });
      }
    }
    for (const l of linesOf(o, term, "derivation")) {
      const r = parseOpRef(l.value);
      if (!r) out.push({ term, code: "O10-derivation", msg: `derivation must be <op>@<v>[ <arg>]: ${JSON.stringify(l.value)}` });
      else {
        const op = opFor(r.op);
        if (!op)
          out.push({ term, code: "O10-derivation", msg: `derivation names ${r.op}, not an op of this engine (${opNames().join(", ")})` });
        else {
          const why = argProblem(op, r.arg);
          if (why) out.push({ term, code: "O10-derivation", msg: why });
        }
      }
    }
    for (const l of linesOf(o, term, "expects")) {
      for (const t of Array.isArray(l.value) ? l.value : [])
        if (!o.terms.has(String(t))) out.push({ term, code: "O8-expects", msg: `expects unknown term '${String(t)}'` });
    }
  }
  for (const d of duplicateIdentities(o)) out.push({ term: d.split(":")[0]!, code: "O9-identity", msg: `duplicate identity ${d}` });
  return out;
}
