// testimony.ts — testimony (spec §9): the contract every testimony follows (§9.4) — a `subject` naming by full hash
// what it is about, a `producer` with `tool`, `version` and `at`, and a non-empty `source` — and nothing else asked;
// admission before anything is placed (§9.5), refusing a testimony whose subject is not the artifact it is delivered
// for; the receipt, the one testimony the tooling writes and the only shape it prescribes (§9.3); a record's
// `origins` entry, the testimony verbatim but for `subject` (§8.2.1); and the provenance chain, derived (§9.6).
import { canonicalJson } from "@ath/kit/canonical.ts";
import type { J } from "../formats/format.ts";
import type { RecordDoc } from "../record/document.ts";

export interface ContractCheck {
  ok: boolean;
  problems: string[];
  doc: J | null;
}

const isObj = (v: unknown): v is J => !!v && typeof v === "object" && !Array.isArray(v);
const present = (v: unknown) => v !== undefined && v !== null && v !== "";

/** Whether parsed testimony follows the contract (§9.4); `subject` is checked when `withSubject`. */
export function checkContract(doc: unknown, withSubject = true): ContractCheck {
  const problems: string[] = [];
  if (!isObj(doc)) return { ok: false, problems: ["testimony is a mapping"], doc: null };
  if (withSubject && !(typeof doc.subject === "string" && /^b3:[0-9a-f]{64}$/.test(doc.subject)))
    problems.push("`subject` is required: `b3:` and the full hash of what it testifies about");
  const p = doc.producer;
  if (!isObj(p)) problems.push("`producer` is required: {tool, version, at}");
  else for (const k of ["tool", "version", "at"]) if (!present(p[k])) problems.push(`\`producer.${k}\` is required`);
  if (!isObj(doc.source) || Object.keys(doc.source).length === 0) problems.push("`source` is required and is a non-empty mapping");
  return { ok: problems.length === 0, problems, doc };
}

/** Parse delivered testimony bytes (YAML, of which JSON is a part). */
export function parseTestimony(bytes: Uint8Array): unknown {
  try {
    return Bun.YAML.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    return null;
  }
}

/** Admission (§9.5.1): the contract, and a `subject` that is the artifact it is delivered for. */
export function admit(bytes: Uint8Array, artifact: string): ContractCheck {
  const doc = parseTestimony(bytes);
  if (doc === null) return { ok: false, problems: ["does not parse as YAML or JSON"], doc: null };
  const c = checkContract(doc);
  if (c.ok && (doc as J).subject !== `b3:${artifact}`) {
    c.ok = false;
    c.problems.push(`its \`subject\` is ${(doc as J).subject}, not the artifact it was delivered with (b3:${artifact})`);
  }
  return c;
}

/** The record's `origins` entry for an admitted testimony: its parse verbatim, `subject` aside. */
export function originOf(doc: J): J {
  const { subject: _subject, ...rest } = doc;
  return rest;
}

/** Whether a record's `origins` entry is a given testimony: its parse equals the entry, `subject` aside (§9.3.3). */
export const isOriginOf = (entry: J, testimonyDoc: J): boolean => canonicalJson(entry) === canonicalJson(originOf(testimonyDoc));

export interface Receipt {
  actor: string;
  artifact: string;
  instance: string;
  name: string;
  received: string;
  testimony: { hash: string; name: string }[];
}

/** The receipt's bytes (§9.3.1): canonical JSON, LF-terminated. Its BLAKE3 is its identity. */
export const receiptBytes = (r: Receipt): Uint8Array => new TextEncoder().encode(`${canonicalJson(r)}\n`);

export interface ProvenanceStep {
  /** The artifact this step is about. */
  artifact: string;
  receipts: RecordDoc["receipts"];
  origins: RecordDoc["origins"];
  /** How it is held inside the container of the next step: the path, and the container's own provenance. */
  within?: { container: string; path: string; provenance: ProvenanceStep }[];
}

/** An artifact's provenance (§9.6): its record's receipts and origins, and every container that holds it, at that
 * path, transitively. Nothing is copied to a constituent; a container's testimony stays the container's. */
export function provenance(
  hash: string,
  record: (h: string) => RecordDoc | null,
  containers: (h: string) => { container: string; path: string }[],
  seen: Set<string> = new Set(),
): ProvenanceStep {
  seen.add(hash);
  const r = record(hash);
  const step: ProvenanceStep = { artifact: hash, receipts: r?.receipts ?? [], origins: r?.origins ?? [] };
  const within = containers(hash)
    .filter((c) => !seen.has(c.container))
    .map((c) => ({ container: c.container, path: c.path, provenance: provenance(c.container, record, containers, new Set(seen)) }));
  if (within.length) step.within = within;
  return step;
}
