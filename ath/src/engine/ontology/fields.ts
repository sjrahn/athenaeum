// fields.ts — a manifests line's fields against the term's declarations (spec §7.2 `field`): undeclared is refused,
// required must be present, kinds are checked, a `derived` field is never stored (D-D2).
import type { JsonObject } from "../../lib/jsonl.ts";
import type { FieldDecl } from "../model/term.ts";

export const RESERVED_MANIFESTS_KEYS = new Set(["at", "predicate", "term", "pass", "by"]);

export interface FieldFinding {
  field: string;
  why: string;
}

function kindOk(d: FieldDecl, v: unknown): boolean {
  switch (d.kind) {
    case "int":
      return Number.isInteger(v);
    case "enum":
      return typeof v === "string" && (d.options ?? []).includes(v);
    case "datetime":
      return typeof v === "string" && !Number.isNaN(new Date(v).getTime());
    case "string":
    case "col":
    case "designator":
    case "string | col":
      return typeof v === "string";
    case "list":
      return Array.isArray(v);
  }
}

/** The findings for one manifests line's extra keys against the declared fields. */
export function checkFields(line: JsonObject, decls: readonly FieldDecl[]): FieldFinding[] {
  const out: FieldFinding[] = [];
  const byName = new Map(decls.map((d) => [d.name, d]));
  for (const k of Object.keys(line)) {
    if (RESERVED_MANIFESTS_KEYS.has(k)) continue;
    const d = byName.get(k);
    if (!d) {
      out.push({ field: k, why: `undeclared field '${k}' on term ${String(line.term)}` });
      continue;
    }
    if (d.derived) {
      out.push({ field: k, why: `field '${k}' is derived from the address and is never stored` });
      continue;
    }
    if (!kindOk(d, line[k])) out.push({ field: k, why: `field '${k}' is not a ${d.kind}: ${JSON.stringify(line[k])}` });
  }
  for (const d of decls) {
    if (d.required && !d.derived && !(d.name in line))
      out.push({ field: d.name, why: `required field '${d.name}' missing on term ${String(line.term)}` });
  }
  return out;
}
