// nquads.ts — the graph projection (spec §15.3): every term and entity line, and every reading, scope and pass of a
// record, as N-Quads statements, and back, byte-identical; rulings are never projected. Artifacts and their scopes are
// `ath://<blake3>` and `ath://<blake3>?<at>`; entities and kinds `ath://<name>`; forms `ath:form/<name>`, shapes
// `ath:shape/<name>`, properties `ath:p/<name>`. A line's own predicate is `ath:p/<pred>` for a claim and
// `ath:pred/<pred>` otherwise, its payload a literal typed `ath:json` — the line's canonical JSON without its `pred`
// and its authorship — and its graph its authorship: `ath://<subject>#<instance-id>/<pass-id>` for a pass,
// `ath:by/<op>` for an op, `ath:vocab` for a term's lines. `is` projects as `rdf:type` too, and a term's `aligns` as
// its class or property; those statements are derived and not read back.
import { canonicalJson, canonicalLine, type JsonObject } from "@ath/kit/canonical.ts";
import { AthError } from "@ath/kit/errors.ts";
import type { Reading, RecordDoc, Scope } from "../record/document.ts";
import { isField } from "../record/document.ts";
import type { Vocab } from "../vocab/terms.ts";

const RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";
const SUBCLASS = "http://www.w3.org/2000/01/rdf-schema#subClassOf";
const SUBPROP = "http://www.w3.org/2000/01/rdf-schema#subPropertyOf";
const JSON_T = "ath:json";

export interface Quad {
  s: string;
  p: string;
  o: { iri: string } | { literal: string; datatype: string };
  g: string;
}

const esc = (s: string) => s.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n").replace(/\r/g, "\\r");
const unesc = (s: string) => s.replace(/\\(["\\nrt])/g, (_, c: string) => ({ n: "\n", r: "\r", t: "\t" })[c] ?? c);

export const quadText = (q: Quad): string =>
  `<${q.s}> <${q.p}> ${"iri" in q.o ? `<${q.o.iri}>` : `"${esc(q.o.literal)}"^^<${q.o.datatype}>`} <${q.g}> .`;

export function parseQuad(line: string): Quad {
  const m = /^<([^>]*)> <([^>]*)> (?:<([^>]*)>|"((?:[^"\\]|\\.)*)"\^\^<([^>]*)>) <([^>]*)> \.$/.exec(line.trim());
  if (!m) throw new AthError("USAGE", `not an N-Quads statement this projection writes: ${line.slice(0, 80)}`);
  return { s: m[1]!, p: m[2]!, o: m[3] !== undefined ? { iri: m[3] } : { literal: unesc(m[4]!), datatype: m[5]! }, g: m[6]! };
}

const termIri = (v: Vocab, name: string) =>
  v === "forms" ? `ath:form/${name}` : v === "shapes" ? `ath:shape/${name}` : v === "kinds" ? `ath://${name}` : `ath:p/${name}`;
const payload = (line: JsonObject): string => {
  const { pred: _p, pass: _s, by: _b, ...rest } = line;
  return canonicalLine(rest);
};

/** A term's lines. */
export function termQuads(v: Vocab, name: string, lines: readonly JsonObject[]): Quad[] {
  const s = termIri(v, name);
  const out: Quad[] = lines.map((l) => ({ s, p: `ath:pred/${l.pred}`, o: { literal: payload(l), datatype: JSON_T }, g: "ath:vocab" }));
  for (const l of lines)
    if (l.pred === "aligns" && typeof l.val === "string")
      out.push({ s, p: v === "properties" ? SUBPROP : SUBCLASS, o: { iri: l.val }, g: "ath:vocab" });
  return out;
}

/** An entity's lines, in the file of the instance `instanceId` names. */
export function entityQuads(name: string, instanceId: string, lines: readonly JsonObject[]): Quad[] {
  const s = `ath://${name}`;
  const graphOf = (l: JsonObject) =>
    l.pred === "pass"
      ? `ath://${name}#${instanceId}/${(l.val as JsonObject).id}`
      : typeof l.pass === "string"
        ? `ath://${name}#${instanceId}/${l.pass}`
        : `ath:by/${l.by}`;
  const out: Quad[] = [];
  for (const l of lines) {
    const fixed =
      l.pred === "is" ||
      l.pred === "pass" ||
      l.pred === "same-as" ||
      l.pred === "manifests" ||
      l.pred === "supersedes" ||
      l.pred === "challenges" ||
      l.pred === "presence";
    out.push({ s, p: fixed ? `ath:pred/${l.pred}` : `ath:p/${l.pred}`, o: { literal: payload(l), datatype: JSON_T }, g: graphOf(l) });
    if (l.pred === "is" && typeof l.val === "string") out.push({ s, p: RDF_TYPE, o: { iri: `ath://${l.val}` }, g: graphOf(l) });
  }
  return out;
}

/** A record's judgments: its passes, its readings, its scopes — a scope one statement per form, field and position, a
 * reading one per aspect, each in the graph of the pass that answers for it. */
export function recordQuads(hash: string, instanceId: string, r: RecordDoc, passOf: (what: string) => string | null): Quad[] {
  const out: Quad[] = [];
  const g = (what: string) => {
    const p = passOf(what);
    return p ? `ath://${hash}#${instanceId}/${p}` : `ath:by/ath`;
  };
  for (const [id, pass] of Object.entries(r.passes ?? {}))
    out.push({
      s: `ath://${hash}`,
      p: "ath:pred/pass",
      o: { literal: canonicalJson({ id, ...pass }), datatype: JSON_T },
      g: `ath://${hash}#${instanceId}/${id}`,
    });
  const reading = (at: string, b: Reading) => {
    for (const a of ["text", "cells", "tex"] as const)
      if (b[a] !== undefined)
        out.push({ s: `ath://${hash}?${at}`, p: `ath:pred/${a}`, o: { literal: canonicalJson(b[a]), datatype: JSON_T }, g: g(at) });
  };
  for (const [at, b] of Object.entries(r.readings ?? {})) reading(at, b);
  const walk = (scopes: readonly Scope[], parent: string) => {
    for (const [i, s] of scopes.entries()) {
      const iri = `ath://${hash}?${s.at}`;
      const tg = g("tree");
      for (const f of [s.form].flat()) out.push({ s: iri, p: "ath:pred/form", o: { iri: `ath:form/${f}` }, g: tg });
      if (Array.isArray(s.form)) out.push({ s: iri, p: "ath:pred/forms", o: { literal: canonicalJson(s.form), datatype: JSON_T }, g: tg });
      out.push({ s: iri, p: "ath:pred/position", o: { literal: canonicalJson({ in: parent, ord: i }), datatype: JSON_T }, g: tg });
      for (const k of Object.keys(s).filter(isField))
        out.push({ s: iri, p: `ath:pred/field/${k}`, o: { literal: canonicalJson(s[k]), datatype: JSON_T }, g: tg });
      reading(s.at, s);
      if (s.scopes) walk(s.scopes, iri);
    }
  };
  if (r.scopes) walk(r.scopes, `ath://${hash}`);
  return out;
}

// ── back ────────────────────────────────────────────────────────────────────────────────────────────────────────────

/** The lines of an entity or a term from its statements, as they were written. */
export function linesFromQuads(quads: readonly Quad[]): { subject: string; line: JsonObject }[] {
  const out: { subject: string; line: JsonObject }[] = [];
  for (const q of quads) {
    if (!("literal" in q.o) || q.o.datatype !== JSON_T) continue;
    const m = /^ath:(p|pred)\/(.+)$/.exec(q.p);
    if (!m) continue;
    // a record's own statements are `ath:pred/…` about an artifact or its scopes; a claim is `ath:p/…` about an entity
    if (m[1] === "pred" && (m[2]!.startsWith("field/") || ["form", "forms", "position", "text", "cells", "tex"].includes(m[2]!))) continue;
    if (m[2] === "pass" && /^ath:\/\/[0-9a-f]{64}$/.test(q.s)) continue; // a record's pass
    const body = JSON.parse(q.o.literal) as JsonObject;
    const line: JsonObject = { pred: m[2]!, ...body };
    const pass = /#[^/]+\/(p\d+)$/.exec(q.g);
    if (pass && m[2] !== "pass") line.pass = pass[1];
    const by = /^ath:by\/(.+)$/.exec(q.g);
    if (by) line.by = by[1];
    out.push({ subject: q.s, line: JSON.parse(canonicalLine(line)) as JsonObject });
  }
  return out;
}

/** A record's passes, readings and scopes from its statements. */
export function judgmentsFromQuads(hash: string, quads: readonly Quad[]): Pick<RecordDoc, "passes" | "readings" | "scopes"> {
  const own = quads.filter((q) => q.s === `ath://${hash}` || q.s.startsWith(`ath://${hash}?`));
  const passes: NonNullable<RecordDoc["passes"]> = {};
  for (const q of own)
    if (q.p === "ath:pred/pass" && "literal" in q.o) {
      const { id, ...p } = JSON.parse(q.o.literal) as JsonObject & { id: string };
      passes[id] = p as never;
    }
  const nodes = new Map<string, Scope & { _in?: string; _ord?: number }>();
  const bodies = new Map<string, Reading>();
  for (const q of own) {
    if (q.s === `ath://${hash}`) continue;
    const at = q.s.slice(hash.length + 7);
    const m = /^ath:pred\/(.+)$/.exec(q.p);
    if (!m) continue;
    const k = m[1]!;
    if (k === "text" || k === "cells" || k === "tex") {
      bodies.set(at, { ...(bodies.get(at) ?? {}), [k]: JSON.parse((q.o as { literal: string }).literal) });
      continue;
    }
    const n = nodes.get(at) ?? ({ form: "", at } as Scope & { _in?: string; _ord?: number });
    nodes.set(at, n);
    if (k === "form") n.form = n.form ? n.form : (q.o as { iri: string }).iri.slice(9);
    else if (k === "forms") n.form = JSON.parse((q.o as { literal: string }).literal);
    else if (k === "position") {
      const p = JSON.parse((q.o as { literal: string }).literal) as { in: string; ord: number };
      n._in = p.in;
      n._ord = p.ord;
    } else if (k.startsWith("field/")) (n as Record<string, unknown>)[k.slice(6)] = JSON.parse((q.o as { literal: string }).literal);
  }
  const out: Pick<RecordDoc, "passes" | "readings" | "scopes"> = {};
  if (Object.keys(passes).length) out.passes = passes;
  if (!nodes.size) {
    if (bodies.size) out.readings = Object.fromEntries(bodies);
    return out;
  }
  for (const [at, b] of bodies) Object.assign(nodes.get(at) ?? {}, b);
  const kids = (parent: string) =>
    [...nodes.values()]
      .filter((n) => n._in === parent)
      .sort((a, b) => a._ord! - b._ord!)
      .map((n): Scope => {
        const { _in: _i, _ord: _o, ...s } = n;
        const sub = kids(`ath://${hash}?${s.at}`);
        return sub.length ? { ...s, scopes: sub } : s;
      });
  out.scopes = kids(`ath://${hash}`);
  return out;
}
