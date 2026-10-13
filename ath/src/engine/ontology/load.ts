// load.ts — the ontology as loaded: every term file across the chain (spec §7), each line kept with its layer. An
// extension adds terms and lines; a line at a foundation term's existing identity is refused (spec §7.4).
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { AthError } from "../../kit/errors.ts";
import { type JsonObject, readJsonl } from "../../lib/jsonl.ts";
import { type Chain, type Layer, TREE_DIRS } from "../layer/config.ts";
import { identityKey, validateLine } from "../model/line.ts";

export interface TermLine {
  subject: string;
  predicate: string;
  value: unknown;
  layer: Layer;
}

export interface Ontology {
  terms: Map<string, TermLine[]>;
  /** The chain it was loaded from. */
  chain: Chain;
}

export function ontologyDir(layer: Layer): string {
  return join(layer.root, TREE_DIRS.ontology);
}

export function loadOntology(chain: Chain): Ontology {
  const terms = new Map<string, TermLine[]>();
  const seen = new Map<string, Layer>(); // identity → layer that first wrote it
  for (const layer of chain.layers) {
    const dir = ontologyDir(layer);
    if (!existsSync(dir)) continue;
    for (const f of readdirSync(dir).sort()) {
      const m = /^(.+)\.claims\.jsonl$/.exec(f);
      if (!m) continue;
      const term = m[1]!;
      const p = join(dir, f);
      for (const line of readJsonl(p)) {
        const bad = validateLine("ontology", line);
        if (bad) throw new AthError("CONFIG", `${p}: ${bad}`);
        if (line.subject !== term) throw new AthError("CONFIG", `${p}: a line's subject is '${line.subject}', not the file's term`);
        const id = identityKey("ontology", line);
        const first = seen.get(id);
        if (first && first !== layer)
          throw new AthError(
            "CONFLICT",
            `${p}: redefines ${id} declared by ${first.root} (an extension never redefines a foundation term)`,
          );
        seen.set(id, layer);
        const list = terms.get(term) ?? [];
        list.push({ subject: term, predicate: String(line.predicate), value: line.value, layer });
        terms.set(term, list);
      }
    }
  }
  return { terms, chain };
}

export function hasTerm(o: Ontology, term: string): boolean {
  return o.terms.has(term);
}

export function linesOf(o: Ontology, term: string, predicate?: string): TermLine[] {
  const l = o.terms.get(term) ?? [];
  return predicate ? l.filter((x) => x.predicate === predicate) : l;
}

/** The single value of a non-repeatable predicate on a term (not resolved along refines). */
export function singleValue<T = unknown>(o: Ontology, term: string, predicate: string): T | undefined {
  return linesOf(o, term, predicate)[0]?.value as T | undefined;
}

export const toJson = (l: TermLine): JsonObject => ({ subject: l.subject, predicate: l.predicate, value: l.value });
