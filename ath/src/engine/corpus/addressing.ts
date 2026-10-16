// addressing.ts — the two derived address forms (spec §5.3), never stored: positional (an ord path from whole,
// `0/3/1`) and designated (the designators the bytes print, `sec=5&para=6`, `post=4`, `col=Currency`), each resolved to
// an intrinsic `at` through manifests, in and ord.
import { AthError } from "../../kit/errors.ts";
import { effectiveRules } from "../ontology/effective.ts";
import type { Ontology } from "../ontology/load.ts";
import type { Scope, ScopeTable } from "./tree.ts";

export function positional(table: ScopeTable, path: string): string {
  let at = "whole";
  for (const step of path.split("/").filter((x) => x !== "")) {
    const n = Number(step);
    if (!Number.isInteger(n) || n < 0) throw new AthError("USAGE", `positional path: '${step}' is not an ord`);
    const kids = table.children(at);
    const k = kids.find((c) => c.ord === n);
    if (!k) throw new AthError("NOT_FOUND", `positional path: no child ${n} under ${at} (${kids.length} children)`);
    at = k.at;
  }
  return at;
}

/** The address-key → designator-field map the ontology declares (`sec` → heading.num, `post` → post.position …). */
export function designatorKeys(o: Ontology, table: ScopeTable): Map<string, { term: string; field: string; pattern?: string }[]> {
  const out = new Map<string, { term: string; field: string; pattern?: string }[]>();
  const terms = new Set<string>();
  for (const s of table.scopes.values()) for (const t of s.terms) terms.add(t);
  for (const t of terms) {
    for (const f of effectiveRules(o, [t]).fields) {
      if (f.address) out.set(f.address, [...(out.get(f.address) ?? []), { term: t, field: f.name, pattern: f.pattern }]);
    }
  }
  return out;
}

/** What a designator field answers to in an address: the whole value, and the pattern's first capture when the
 * declaration has one (`Equation (2)` under `^Equation \((\d+)\)$` answers to `eq=2`). */
function answersTo(value: unknown, pattern: string | undefined): string[] {
  const whole = norm(value);
  if (!pattern) return [whole];
  const m = new RegExp(pattern).exec(String(value));
  return m?.[1] !== undefined ? [whole, norm(m[1])] : [whole];
}

const norm = (v: unknown): string => String(v).trim().replace(/^#/, "").replace(/\.$/, "").toLowerCase();

/** `sec=5&para=6` → the scope: each key narrows to scopes whose designator field matches, later keys inside earlier ones. */
export function designated(o: Ontology, table: ScopeTable, query: string): string {
  const keys = designatorKeys(o, table);
  let candidates: Scope[] | null = null;
  for (const part of query.split("&")) {
    const eq = part.indexOf("=");
    if (eq === -1) throw new AthError("USAGE", `designated address: '${part}' has no value`);
    const key = part.slice(0, eq);
    const want = norm(decodeURIComponent(part.slice(eq + 1)));
    const decls = keys.get(key);
    if (!decls)
      throw new AthError(
        "USAGE",
        `designated address: no term declares a designator for '${key}=' (known: ${[...keys.keys()].join(", ") || "none"})`,
      );
    // a later key narrows to what the earlier key's scopes hold: their descendants in the tree (a paragraph placed in a
    // heading) and whatever their boxes contain (a cell in a row)
    const pool: Scope[] = candidates
      ? [...new Set(candidates.flatMap((c) => [...table.walk(c.at).filter((s) => s.at !== c.at), ...table.within(c.at)]))]
      : [...table.scopes.values()];
    const hits: Scope[] = pool.filter((s: Scope) =>
      decls.some(
        (d) => s.terms.includes(d.term) && s.fields[d.field] !== undefined && answersTo(s.fields[d.field], d.pattern).includes(want),
      ),
    );
    if (!hits.length)
      throw new AthError(
        "NOT_FOUND",
        `designated address: nothing matches ${key}=${part.slice(eq + 1)}${candidates ? " inside the previous key" : ""}`,
      );
    candidates = hits;
  }
  if (candidates?.length !== 1) {
    throw new AthError("CONFLICT", `designated address '${query}' is ambiguous: ${candidates?.map((c) => c.at).join(", ")}`);
  }
  return candidates[0]!.at;
}

/** Resolve either form; an intrinsic address passes through. */
export function resolveQuery(o: Ontology, table: ScopeTable, q: string): string {
  if (q === "whole" || /^(page|bbox|bytes|row|t|path)=/.test(q) || /^col=\d+$/.test(q)) return q;
  if (/^\d+(\/\d+)*$/.test(q) || q === "/") return positional(table, q);
  return designated(o, table, q);
}
