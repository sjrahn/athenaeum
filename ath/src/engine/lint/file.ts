// file.ts — the per-file lints (spec §13): no undeclared field, no derivable value stored, no reads_as outside text ·
// cells · tex (the grammar refuses those at parse), one writer per file, sorted, pass refs resolve, the ontology
// hash is known. Ledger files: every line has exactly one attestation that resolves (D-F1); `scope:` and other
// strays are refused (D-F8).
import type { JsonObject } from "../../lib/jsonl.ts";
import { canonicalLine, readJsonl } from "../../lib/jsonl.ts";
import type { Artifact } from "../corpus/derive.ts";
import { subjectPath } from "../layer/store.ts";
import type { Concept } from "../ledger/file.ts";
import { attestationOf, identityKey, LEDGER_BY, sortLines } from "../model/line.ts";
import { effectiveRules } from "../ontology/effective.ts";
import { checkFields } from "../ontology/fields.ts";
import type { Ontology } from "../ontology/load.ts";
import type { Finding } from "./report.ts";

export function fileLintsCorpus(a: Artifact, currentPin: string | null): Finding[] {
  const out: Finding[] = [];
  const id = a.blake3;
  const passIds = new Set(a.passes.keys());
  for (const l of a.stored) {
    const att = attestationOf(l);
    if (l.predicate !== "pass" && (att.kind === "both" || att.kind === "none"))
      out.push({ code: "F-attest", severity: "block", subject: id, at: String(l.at), msg: `${l.predicate}: exactly one of by/pass` });
    if (att.kind === "pass" && !passIds.has(att.pass))
      out.push({
        code: "F-pass",
        severity: "block",
        subject: id,
        at: String(l.at),
        msg: `${l.predicate} names pass ${att.pass}, which is not in the file`,
      });
    if (l.predicate === "manifests") {
      const decls = effectiveRules(a.ontology, [String(l.term)]).fields;
      if (!a.ontology.terms.has(String(l.term)))
        out.push({ code: "F-term", severity: "block", subject: id, at: String(l.at), msg: `manifests unknown term '${l.term}'` });
      for (const f of checkFields(l, decls))
        out.push({
          code: f.why.includes("never stored") ? "F-derived" : "F-field",
          severity: "block",
          subject: id,
          at: String(l.at),
          msg: f.why,
        });
    }
    if (l.predicate === "inspected")
      out.push({ code: "F-writer", severity: "block", subject: id, at: String(l.at), msg: "an inspected line belongs in the owner file" });
    if (l.predicate === "pass" && currentPin && String((l.value as JsonObject).ontology) !== currentPin) {
      out.push({
        code: "F-stale",
        severity: "list",
        subject: id,
        at: String(l.at),
        msg: `pass ${(l.value as JsonObject).id} pinned ${(l.value as JsonObject).ontology}; the ontology is ${currentPin}`,
      });
    }
  }
  // sorted
  const path = subjectPath(a.chain.top, "corpus", id);
  try {
    const onDisk = readJsonl(path);
    const sorted = sortLines("corpus", onDisk);
    if (onDisk.map(canonicalLine).join("\n") !== sorted.map(canonicalLine).join("\n"))
      out.push({ code: "F-sorted", severity: "block", subject: id, msg: `${path} is not in canonical order (ath claims sort)` });
    const ids = new Set<string>();
    for (const l of onDisk) {
      const k = identityKey("corpus", l);
      if (ids.has(k)) out.push({ code: "F-identity", severity: "block", subject: id, at: String(l.at), msg: `duplicate identity ${k}` });
      ids.add(k);
    }
  } catch {
    // not in the top layer: nothing to check on disk
  }
  return out;
}

const KNOWN_LEDGER_KEYS = new Set(["subject", "predicate", "value", "object", "qualifiers", "evidence", "by", "pass"]);

export function fileLintsLedger(c: Concept, _o: Ontology): Finding[] {
  const out: Finding[] = [];
  for (const p of c.problems) out.push({ code: "F-evidence", severity: "block", subject: c.slug, msg: p });
  for (const cl of c.claims) {
    const att = attestationOf(cl.line);
    if (att.kind === "none")
      out.push({
        code: "F-attest",
        severity: "block",
        subject: c.slug,
        msg: `${cl.predicate}: a ledger claim carries by (an op) or pass (D-F1)`,
      });
    if (att.kind === "both")
      out.push({ code: "F-attest", severity: "block", subject: c.slug, msg: `${cl.predicate}: exactly one of by/pass` });
    if (att.kind === "pass" && !c.passes.has(att.pass))
      out.push({
        code: "F-pass",
        severity: "block",
        subject: c.slug,
        msg: `${cl.predicate} names pass ${att.pass}, which is not in the file`,
      });
    if (att.kind === "by" && !LEDGER_BY.test(att.by))
      out.push({
        code: "F-attest",
        severity: "block",
        subject: c.slug,
        msg: `${cl.predicate}: by '${att.by}' is not an op (name@version) or a harvest pin`,
      });
    for (const k of Object.keys(cl.line))
      if (!KNOWN_LEDGER_KEYS.has(k))
        out.push({ code: "F-field", severity: "block", subject: c.slug, msg: `${cl.predicate}: undeclared key '${k}'` });
    for (const e of Array.isArray(cl.line.evidence) ? (cl.line.evidence as JsonObject[]) : []) {
      for (const k of Object.keys(e))
        if (!["anchor", "quote", "prefix", "suffix", "kind", "mode", "reasoning", "reading"].includes(k))
          out.push({
            code: "F-field",
            severity: "block",
            subject: c.slug,
            msg: `${cl.predicate}: evidence carries undeclared key '${k}' (D-F8)`,
          });
    }
  }
  if (!c.terms.length) out.push({ code: "F-term", severity: "block", subject: c.slug, msg: "a concept carries at least one term line" });
  return out;
}
