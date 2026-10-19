// terms.ts — the four vocabularies (spec §11.1) as term files of lines, a term line's identity (§6.3.1), the sort
// a term file is written in, and the pin (§11.8): `b3:` and 16 hex digits of the BLAKE3 over a vocabulary as loaded —
// the term files in path order (`corpus/forms/` then `corpus/shapes/`; `graph/kinds/` then `graph/properties/`; names
// in code-point order), each preceded by its path and an LF, its lines sorted by identity, each canonical and
// LF-terminated. An extension's terms are loaded together with its base's.
import { byCodePoint, canonicalJson, canonicalLine, type JsonObject } from "@ath/kit/canonical.ts";
import { short } from "@ath/kit/hash.ts";

export type Vocab = "forms" | "shapes" | "kinds" | "properties";
export const VOCABS: readonly Vocab[] = ["forms", "shapes", "kinds", "properties"];
export type Side = "corpus" | "graph";
export const SIDE: Record<Vocab, Side> = { forms: "corpus", shapes: "corpus", kinds: "graph", properties: "graph" };
/** The directory a vocabulary's term files sit in, relative to the instance root (§5.1). */
export const DIR: Record<Vocab, string> = {
  forms: "corpus/forms",
  shapes: "corpus/shapes",
  kinds: "graph/kinds",
  properties: "graph/properties",
};

/** A term's lines as stored: `{pred, val}` each, no authorship (§6.1.2). */
export type TermLines = JsonObject[];

/** The predicates each vocabulary carries (§11.2); every term also carries `refines`, `definition`, `aligns`. */
export const PREDICATES: Record<Vocab, readonly string[]> = {
  forms: ["refines", "definition", "aligns", "reads", "field", "expects", "convention", "renders", "check"],
  shapes: ["refines", "definition", "aligns", "matches", "select", "columns", "spine", "chrome", "surface"],
  kinds: ["refines", "definition", "aligns", "owes"],
  properties: ["refines", "definition", "aligns", "range", "functional", "authority"],
};

/** Predicates with one value per term; every other predicate repeats. */
const SINGLE = new Set([
  "refines",
  "definition",
  "aligns",
  "reads",
  "expects",
  "renders",
  "spine",
  "owes",
  "range",
  "functional",
  "authority",
]);

/** The identity of a term line (§6.3.1): (pred) single-valued; (pred, name) where the value has a `name` or `col`;
 * (pred, value) for every other repeatable predicate (`select`, `matches`, `chrome`, `columns` without `col`, …). */
export function termIdentity(line: JsonObject): string {
  const pred = String(line.pred);
  if (SINGLE.has(pred)) return pred;
  const v = line.val as JsonObject | null;
  if (v && typeof v === "object" && !Array.isArray(v)) {
    if (typeof v.name === "string") return `${pred}\u0000name\u0000${v.name}`;
    if (v.col !== undefined) return `${pred}\u0000col\u0000${canonicalJson(v.col)}`;
  }
  return `${pred}\u0000val\u0000${canonicalJson(line.val)}`;
}

/** A term file's lines sorted by identity, one line per identity (the later write replaces the earlier). */
export function sortTermLines(lines: readonly JsonObject[]): JsonObject[] {
  const by = new Map<string, JsonObject>();
  for (const l of lines) by.set(termIdentity(l), l);
  return [...by.entries()].sort(([a], [b]) => byCodePoint(a, b)).map(([, l]) => l);
}

export const serializeTerm = (lines: readonly JsonObject[]): string =>
  sortTermLines(lines)
    .map((l) => `${canonicalLine(l)}\n`)
    .join("");

/** One vocabulary as loaded: term name → its lines (base and extension together). */
export type Terms = Map<string, TermLines>;
export type Vocabulary = Record<Vocab, Terms>;

export const emptyVocabulary = (): Vocabulary => ({ forms: new Map(), shapes: new Map(), kinds: new Map(), properties: new Map() });

/** The text a side's pin is the hash of. */
export function pinText(v: Vocabulary, side: Side): string {
  let out = "";
  for (const vocab of VOCABS.filter((x) => SIDE[x] === side))
    for (const name of [...v[vocab].keys()].sort(byCodePoint)) out += `${DIR[vocab]}/${name}.jsonl\n${serializeTerm(v[vocab].get(name)!)}`;
  return out;
}

/** The pin of the corpus's or the graph's vocabulary (§11.8). */
export const pin = (v: Vocabulary, side: Side): Promise<string> => short(pinText(v, side));
