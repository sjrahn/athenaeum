// line.ts — the claim line (spec §4): what each predicate carries, the identity key a second line collides on, and
// the sort key a file is kept in. Artifact lines are keyed by `at`; ledger and ontology lines by `subject`.
import { z } from "../../../contracts/index.ts";
import { AthError } from "../../kit/errors.ts";
import type { JsonObject } from "../../lib/jsonl.ts";
import { ASPECTS, compareAt, scopeAt } from "./address.ts";
import { REPEATABLE } from "./term.ts";

export const OP_REF = /^[a-z][a-z0-9.-]*@\d+(\.\d+)*$/; // ath.ingest@1, pdf.words@1, corpus.ingest@0.1.0
export const PASS_REF = /^p[0-9a-z]+$/; // p1, p2a
export const HARVEST_BY = /^harvest:[a-z0-9-]+@[0-9a-f]{6}$/; // harvest:<term>@<6 hex of the ontology pin>
export const LEDGER_BY = /^(harvest:[a-z0-9-]+@[0-9a-f]{6}|[a-z][a-z0-9.-]*@\d+(\.\d+)*)$/;
export const REV = /^b3:[0-9a-f]{16}$/;
export const BLAKE3 = /^[0-9a-f]{64}$/;
export const SLUG = /^[A-Za-z0-9][A-Za-z0-9-]*$/;
export const TERM = SLUG;

export const ARTIFACT_PREDICATES = ["attests", "captured_from", "pass", "walked", "manifests", "in", "reads_as"] as const;
export type ArtifactPredicate = (typeof ARTIFACT_PREDICATES)[number];
export const OWNER_PREDICATES = ["inspected"] as const;

const atKey = z.string().min(1);

const opLine = z
  .object({
    at: atKey,
    predicate: z.enum(["attests", "captured_from"]),
    value: z.record(z.string(), z.unknown()),
    by: z.string().regex(OP_REF),
  })
  .strict();

const passLine = z
  .object({
    at: atKey,
    predicate: z.literal("pass"),
    value: z
      .object({
        id: z.string().regex(PASS_REF),
        by: z.string().min(1),
        verify: z.string().min(1),
        ontology: z.string().regex(REV),
        date: z.string().min(1),
        note: z.string().optional(),
        with: z.string().optional(),
      })
      .strict(),
  })
  .strict();

const walkedLine = z.object({ at: atKey, predicate: z.literal("walked"), pass: z.string().regex(PASS_REF) }).strict();

const manifestsLine = z
  .object({ at: atKey, predicate: z.literal("manifests"), term: z.string().regex(TERM), pass: z.string().regex(PASS_REF) })
  .catchall(z.unknown()); // the term's declared fields; checked against the ontology by the per-file lint

const inLine = z
  .object({
    at: atKey,
    predicate: z.literal("in"),
    value: z.object({ at: atKey, ord: z.number().int().nonnegative() }).strict(),
    pass: z.string().regex(PASS_REF),
  })
  .strict();

const readsAsLine = z
  .object({
    at: atKey,
    predicate: z.literal("reads_as"),
    aspect: z.enum(ASPECTS),
    rev: z.string().regex(REV),
    body: z.union([z.string(), z.array(z.unknown())]),
    pass: z.string().regex(PASS_REF),
  })
  .strict();

export const ArtifactLine = z.discriminatedUnion("predicate", [opLine, passLine, walkedLine, manifestsLine, inLine, readsAsLine]);
export type ArtifactLine = z.infer<typeof ArtifactLine>;

export const OwnerLine = z
  .object({
    at: atKey,
    predicate: z.literal("inspected"),
    value: z.object({ rev: z.string().regex(REV), diverges: z.literal("accepted"), why: z.string().min(1) }).strict(),
    by: z.literal("owner"),
    date: z.string().min(1),
  })
  .strict();
export type OwnerLine = z.infer<typeof OwnerLine>;

/** A ledger line: `term`, `manifested_by`, `part_of`, `pass`, or a claim with evidence. Checked loosely here; the
 * binding grammar and the evidence shape are model/evidence.ts; attestation rules are the per-file lint. */
export const LedgerLine = z
  .object({
    subject: z.string().regex(SLUG),
    predicate: z.string().min(1),
    by: z.string().regex(LEDGER_BY).optional(),
    pass: z.string().regex(PASS_REF).optional(),
  })
  .catchall(z.unknown());
export type LedgerLine = z.infer<typeof LedgerLine>;

export const OntologyLine = z.object({ subject: z.string().regex(TERM), predicate: z.string().min(1), value: z.unknown() }).strict();
export type OntologyLine = z.infer<typeof OntologyLine>;

export type Tree = "corpus" | "ledger" | "ontology" | "owner";

/** The identity key (spec §4.2): what a second line collides on. */
export function identityKey(tree: Tree, l: JsonObject): string {
  const p = String(l.predicate);
  if (tree === "corpus" || tree === "owner") {
    const at = scopeAt(String(l.at));
    switch (p) {
      case "attests":
      case "captured_from":
        return `${at}|${p}|${String(l.by)}`;
      case "manifests":
        return `${at}|manifests|${String(l.term)}`;
      case "in":
        return `${at}|in`;
      case "reads_as":
        return `${at}|reads_as|${String(l.aspect)}`;
      case "pass":
        return `${at}|pass|${String((l.value as JsonObject | undefined)?.id)}`;
      case "walked":
        return `${at}|walked|${String(l.pass)}`;
      case "inspected":
        return `${at}|inspected|${String((l.value as JsonObject | undefined)?.rev)}`;
      default:
        throw new AthError("CONFLICT", `unknown artifact predicate '${p}' at ${at}`);
    }
  }
  const s = String(l.subject);
  if (tree === "ontology") {
    if (!REPEATABLE.has(p)) return `${s}|${p}`;
    const v = l.value;
    const name =
      typeof v === "object" && v !== null && !Array.isArray(v)
        ? ((v as JsonObject).name ?? (v as JsonObject).col ?? (v as JsonObject).selector ?? (v as JsonObject).term)
        : undefined;
    const vk = name !== undefined ? String(name) : JSON.stringify(v);
    return `${s}|${p}|${vk}`;
  }
  // ledger
  if (p === "pass") return `${s}|pass|${String((l.value as JsonObject | undefined)?.id)}`;
  const obj = l.object !== undefined ? `o:${String(l.object)}` : `v:${JSON.stringify(l.value)}`;
  const q = l.qualifiers !== undefined ? `|${JSON.stringify(l.qualifiers)}` : "";
  return `${s}|${p}|${obj}${q}`;
}

const PRED_RANK: Record<string, number> = {
  attests: 0,
  captured_from: 1,
  pass: 2,
  walked: 3,
  manifests: 4,
  in: 5,
  reads_as: 6,
  inspected: 7,
};

/** File order: by address (corpus) or subject (ledger, ontology), then predicate rank, then identity. */
export function compareLines(tree: Tree, a: JsonObject, b: JsonObject): number {
  if (tree === "corpus" || tree === "owner") {
    const c = compareAt(String(a.at), String(b.at));
    if (c !== 0) return c;
    const ra = PRED_RANK[String(a.predicate)] ?? 99;
    const rb = PRED_RANK[String(b.predicate)] ?? 99;
    if (ra !== rb) return ra - rb;
  } else {
    const sa = String(a.subject);
    const sb = String(b.subject);
    if (sa !== sb) return sa < sb ? -1 : 1;
    const pa = String(a.predicate);
    const pb = String(b.predicate);
    const rank = (p: string) =>
      p === "term" ? 0 : p === "manifested_by" ? 1 : p === "part_of" ? 2 : p === "pass" ? 3 : p === "refines" ? 0 : 10;
    if (rank(pa) !== rank(pb)) return rank(pa) - rank(pb);
    if (pa !== pb) return pa < pb ? -1 : 1;
  }
  const ia = identityKey(tree, a);
  const ib = identityKey(tree, b);
  return ia < ib ? -1 : ia > ib ? 1 : 0;
}

export function sortLines(tree: Tree, lines: JsonObject[]): JsonObject[] {
  return [...lines].sort((a, b) => compareLines(tree, a, b));
}

/** Validate one line against its tree's grammar; returns the error message or null. */
export function validateLine(tree: Tree, l: JsonObject): string | null {
  const schema = tree === "corpus" ? ArtifactLine : tree === "owner" ? OwnerLine : tree === "ledger" ? LedgerLine : OntologyLine;
  const r = schema.safeParse(l);
  if (r.success) return null;
  return r.error.issues.map((i) => `${i.path.map(String).join(".") || "(root)"}: ${i.message}`).join("; ");
}

/** Which attestation a line carries. */
export function attestationOf(
  l: JsonObject,
): { kind: "by"; by: string } | { kind: "pass"; pass: string } | { kind: "none" } | { kind: "both" } {
  const by = typeof l.by === "string";
  const pass = typeof l.pass === "string";
  if (by && pass) return { kind: "both" };
  if (by) return { kind: "by", by: l.by as string };
  if (pass) return { kind: "pass", pass: l.pass as string };
  return { kind: "none" };
}
