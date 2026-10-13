// hash.ts — the ontology pin (D-F5): BLAKE3 over the layer as loaded — term files sorted by name, lines sorted by
// identity, each compact JSON with non-ASCII unescaped and LF-terminated — written `b3:` + 16 hex. The harvest pin
// is the first 6 hex. Per-term hashes under the same recipe drive staleness by reach.
import { blake3Hex } from "../../lib/hash.ts";
import { canonicalLine } from "../../lib/jsonl.ts";
import { identityKey, sortLines } from "../model/line.ts";
import { type Ontology, toJson } from "./load.ts";

export function serializeTerm(o: Ontology, term: string): string {
  const lines = sortLines("ontology", (o.terms.get(term) ?? []).map(toJson));
  return lines.map((l) => `${canonicalLine(l)}\n`).join("");
}

export function serializeOntology(o: Ontology): string {
  return [...o.terms.keys()]
    .sort()
    .map((t) => serializeTerm(o, t))
    .join("");
}

export async function ontologyPin(o: Ontology): Promise<string> {
  return `b3:${(await blake3Hex(serializeOntology(o))).slice(0, 16)}`;
}

export const harvestPin = (pin: string): string => pin.replace(/^b3:/, "").slice(0, 6);

export async function termPins(o: Ontology): Promise<Map<string, string>> {
  const m = new Map<string, string>();
  for (const t of o.terms.keys()) m.set(t, `b3:${(await blake3Hex(serializeTerm(o, t))).slice(0, 16)}`);
  return m;
}

/** Sanity: identities are unique within a term (a repeated non-repeatable predicate is a lint, not a crash). */
export function duplicateIdentities(o: Ontology): string[] {
  const out: string[] = [];
  for (const [t, lines] of o.terms) {
    const seen = new Set<string>();
    for (const l of lines) {
      const id = identityKey("ontology", toJson(l));
      if (seen.has(id)) out.push(`${t}: ${id}`);
      seen.add(id);
    }
  }
  return out;
}
