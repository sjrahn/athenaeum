// file.ts — a concept subject (spec §9.1): its lines as a typed view — terms, manifested_by, part_of, pass lines,
// claims with their evidence entries — plus the slug rules harvest mints by.
import { AthError } from "../../kit/errors.ts";
import type { JsonObject } from "../../lib/jsonl.ts";
import type { Chain } from "../layer/config.ts";
import { listSubjects, readSubject, unionView } from "../layer/store.ts";
import { EvidenceEntry } from "../model/evidence.ts";
import { identityKey } from "../model/line.ts";

export interface Claim {
  line: JsonObject;
  identity: string;
  predicate: string;
  value?: unknown;
  object?: string;
  qualifiers?: JsonObject;
  evidence: EvidenceEntry[];
  /** `pass:<id>` or `by:<op>` or `none`. */
  attestation: string;
  layer: string;
}

export interface Concept {
  slug: string;
  terms: string[];
  manifestedBy: string[];
  partOf: string[];
  passes: Map<string, JsonObject>;
  claims: Claim[];
  problems: string[];
}

export function readConcept(chain: Chain, slug: string): Concept | null {
  const lines = unionView("ledger", readSubject(chain, "ledger", slug));
  if (!lines.length) return null;
  const c: Concept = { slug, terms: [], manifestedBy: [], partOf: [], passes: new Map(), claims: [], problems: [] };
  for (const { line, layer } of lines) {
    const p = String(line.predicate);
    if (p === "term") c.terms.push(String(line.value));
    else if (p === "manifested_by") c.manifestedBy.push(String(line.value));
    else if (p === "part_of") c.partOf.push(String(line.value));
    else if (p === "pass") c.passes.set(String((line.value as JsonObject).id), line);
    else {
      const evidence: EvidenceEntry[] = [];
      const raw = Array.isArray(line.evidence) ? line.evidence : [];
      raw.forEach((e, i) => {
        const r = EvidenceEntry.safeParse(e);
        if (r.success) evidence.push(r.data);
        else c.problems.push(`${slug} ${p}: evidence[${i}]: ${r.error.issues.map((x) => `${x.path.join(".")}: ${x.message}`).join("; ")}`);
      });
      const attestation = typeof line.pass === "string" ? `pass:${line.pass}` : typeof line.by === "string" ? `by:${line.by}` : "none";
      c.claims.push({
        line,
        identity: identityKey("ledger", line),
        predicate: p,
        value: line.value,
        object: typeof line.object === "string" ? line.object : undefined,
        qualifiers: line.qualifiers as JsonObject | undefined,
        evidence,
        attestation,
        layer: layer.config.name,
      });
    }
  }
  return c;
}

export function listConcepts(chain: Chain): string[] {
  return listSubjects(chain, "ledger");
}

/** `{term}-{key}` by default; `{1}` is the first group of `extract` over the key; lowercase unless `case: keep`. */
export function mintSlug(term: string, key: string, o: { slug?: string; extract?: string; case?: string } = {}): string {
  const k = key.trim();
  let g1: string | undefined;
  if (o.extract) {
    const m = new RegExp(o.extract).exec(k);
    if (!m) throw new AthError("CONFLICT", `harvest: key '${key}' does not match extract /${o.extract}/`);
    g1 = m[1] ?? m[0];
  }
  const template = o.slug ?? "{term}-{key}";
  let s = template
    .replace("{term}", term)
    .replace("{key}", k)
    .replace("{1}", g1 ?? k);
  s = s.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  if (o.case !== "keep") s = s.toLowerCase();
  if (!s) throw new AthError("CONFLICT", `harvest: empty slug for ${term} key '${key}'`);
  return s;
}
