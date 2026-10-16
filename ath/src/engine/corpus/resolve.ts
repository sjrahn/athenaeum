// resolve.ts — what is at an address: the bytes, the derivation surface the ontology's op yields there, or the stored
// reading. The quote surface a binding names (spec §9.2) is computed here and nowhere else. The op is never chosen
// by code: a scope's terms (then the root chain) name it on a `derivation` line, and the registry is the only place
// an op exists (D-derivation).
import { AthError } from "../../kit/errors.ts";
import type { JsonObject } from "../../lib/jsonl.ts";
import { type Aspect, parseAddress, scopeAt } from "../model/address.ts";
import type { Binding } from "../model/evidence.ts";
import { type OpRef, opRefString, parseOpRef } from "../model/line.ts";
import { cellsSurface } from "../norm/text.ts";
import { refinesChain } from "../ontology/chain.ts";
import { resolveAlong } from "../ontology/effective.ts";
import { argProblem, type DerivationOp, formKey, opFor, opNames } from "../ops/index.ts";
import type { Artifact } from "./derive.ts";

export interface Surface {
  /** The op or line that produced it. */
  source: string;
  text: string;
}

/** The bytes at an address (whole or a byte range; other axes need their op). */
export function bytesAt(a: Artifact, at: string): Uint8Array {
  if (!a.bytes) throw new AthError("NOT_FOUND", `${a.blake3}: bytes are not resident in this chain`);
  const m = parseAddress(at).members[0]!;
  if (m.kind === "whole") return a.bytes;
  if (m.kind === "bytes") return a.bytes.subarray(m.start, m.end);
  throw new AthError("USAGE", `bytes at ${at}: only whole and bytes= slice the bytes; use --derivation for ${m.kind}`);
}

export interface Derivation extends OpRef {
  op: string;
  arg?: string;
  /** The term whose line named it. */
  by: string;
  /** `<op>@<v>[ <arg>]`, the string a reading's rev carries after `derived:`. */
  source: string;
}

/** The derivation a term chain names: the first `derivation` line along it, parsed under the one grammar. */
export function derivationAlong(a: Artifact, chain: readonly string[]): Derivation | null {
  for (const t of chain) {
    const v = resolveAlong<unknown>(a.ontology, [t], "derivation");
    if (v === undefined) continue;
    const r = parseOpRef(v);
    if (!r) throw new AthError("CONFIG", `${t}: derivation must be <op>@<v>[ <arg>], not ${JSON.stringify(v)}`);
    return { ...r, by: t, source: opRefString(r) };
  }
  return null;
}

/** The derivation a scope resolves under: its own terms' chains first, then the root chain; null when no term on
 * the way declares one (a root with no derivation has no surface — D-roots). */
export function derivationFor(a: Artifact, scope: string): Derivation | null {
  const terms = a.table.get(scope)?.terms ?? [];
  const merged = [...new Set(terms.flatMap((t) => refinesChain(a.ontology, t)))];
  return derivationAlong(a, merged) ?? derivationAlong(a, a.rootChain);
}

/** The registered op a derivation names; naming one the engine lacks is a configuration error, loudly. */
export function opOf(d: Derivation): DerivationOp {
  const op = opFor(d.op);
  if (!op) throw new AthError("CONFIG", `${d.by} names ${d.op}, not an op of this engine (${opNames().join(", ")})`);
  const why = argProblem(op, d.arg);
  if (why) throw new AthError("CONFIG", `${d.by}: ${why}`);
  return op;
}

/** The parsed form an op reads, from the artifact's cache (parsed by `ensureForms` at load). */
export function formOf(a: Artifact, op: DerivationOp, arg: string | undefined): unknown | undefined {
  return a.forms.get(formKey(op, arg));
}

function surfaceOf(a: Artifact, op: DerivationOp, arg: string | undefined, at: string, aspect: Aspect): string | null {
  const form = formOf(a, op, arg);
  if (form === undefined) return null;
  const parts: string[] = [];
  for (const m of parseAddress(scopeAt(at)).members) {
    const t = op.surface(form, m, arg, aspect);
    if (t === null) return null;
    parts.push(t);
  }
  return parts.join("\n");
}

/** The derivation surface at an address under the op the ontology names there, or null when none. */
export function derivationAt(a: Artifact, at: string, aspect: Aspect = "text"): Surface | null {
  const d = derivationFor(a, scopeAt(at));
  if (!d) return null;
  const op = opOf(d);
  if (!a.bytes) throw new AthError("NOT_FOUND", `${a.blake3}: bytes are not resident in this chain; no surface under ${d.source}`);
  if (formOf(a, op, d.arg) === undefined)
    throw new AthError("INTERNAL", `${a.blake3}: the ${op.family} form for ${d.source} was not parsed at load`);
  const text = surfaceOf(a, op, d.arg, at, aspect);
  return text === null ? null : { source: d.source, text };
}

/** The surface a binding names for an anchor; null = cannot be produced (held or flagged by the caller's rule). */
export function surfaceFor(a: Artifact, at: string, b: Binding, aspect?: Aspect): Surface | null {
  const scope = scopeAt(at);
  switch (b.kind) {
    case "held":
      return null;
    case "rev": {
      const s = a.table.get(scope);
      const r = s?.readings.find((x) => x.stored && x.rev === b.rev && (!aspect || x.aspect === aspect));
      return r ? { source: r.rev, text: typeof r.body === "string" ? r.body : cellsSurface(r.body) } : null;
    }
    case "derived": {
      // a binding naming an op the engine lacks, or one whose form this artifact does not carry, is flagged, not fatal
      const op = opFor(b.op);
      if (!op || argProblem(op, b.arg)) return null;
      const text = surfaceOf(a, op, b.arg, scope, aspect ?? "text");
      return text === null ? null : { source: opRefString({ op: b.op, arg: b.arg }), text };
    }
    case "line": {
      const line =
        b.predicate === "attests"
          ? a.attests
          : b.predicate === "captured_from"
            ? a.capturedFrom
            : b.predicate === "manifests"
              ? manifestsLine(a, scope)
              : null;
      if (!line) return null;
      if (!b.field) return { source: `line:${b.predicate}`, text: JSON.stringify(line.value ?? line) };
      const holder = b.predicate === "manifests" ? line : (line.value as JsonObject);
      const v = holder?.[b.field];
      return v === undefined ? null : { source: `line:${b.predicate} ${b.field}`, text: typeof v === "string" ? v : JSON.stringify(v) };
    }
  }
}

function manifestsLine(a: Artifact, scope: string): JsonObject | null {
  const s = a.table.get(scope);
  if (!s) return null;
  // stored first; else a derived manifests carries the fields in the scope
  const stored = s.stored.find((l) => l.predicate === "manifests");
  if (stored) return stored;
  return { at: s.at, predicate: "manifests", term: s.terms[0], ...s.fields };
}
