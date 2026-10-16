// derive.ts — the derived tree (spec §6.1 "where the bytes give the structure, nothing is stored"): manifests and in
// from the parse through a root term's select (markup) or shape (tabular) lines, then the stored lines laid over it
// (a stored line wins at the same scope). Produces the scope table every consumer reads.
import { AthError } from "../../kit/errors.ts";
import type { JsonObject } from "../../lib/jsonl.ts";
import { resolveBytes } from "../layer/bytes.ts";
import type { Chain } from "../layer/config.ts";
import { readSubject, unionView } from "../layer/store.ts";
import { canonicalAt } from "../model/address.ts";
import { SelectDecl, ShapeDecl } from "../model/term.ts";
import { refinesChain } from "../ontology/chain.ts";
import { effectiveRules, resolveAlong } from "../ontology/effective.ts";
import { linesOf, type Ontology } from "../ontology/load.ts";
import { classify } from "../ontology/match.ts";
import type { CsvParse } from "../ops/csv/parse.ts";
import { type HtmlDoc, matchesSelector, select, spanOf } from "../ops/html/dom.ts";
import { elementText } from "../ops/html/text.ts";
import { formKey } from "../ops/index.ts";
import { isBodyPart, leaves, type Message } from "../ops/mail/parse.ts";
import { blocks } from "../ops/mail/text.ts";
import type { PdfForm } from "../ops/pdf/words.ts";
import { type Derivation, derivationAlong, derivationAt, derivationFor, opOf } from "./resolve.ts";
import { ScopeTable } from "./tree.ts";

export interface Artifact {
  blake3: string;
  chain: Chain;
  ontology: Ontology;
  mime: string;
  attests: JsonObject;
  capturedFrom: JsonObject | null;
  stored: JsonObject[];
  bytesPath: string | null;
  bytes: Uint8Array | null;
  /** The root term `whole` manifests (stored override, else by matches). */
  root: string | null;
  rootChain: string[];
  tree: "asserted" | "derived" | null;
  table: ScopeTable;
  /** Every parsed form an op named along the way, by family (D-derivation); the typed slots below are the same
   * objects, for the consumers that still read a form by family (bind, G3, harvest, export). */
  forms: Map<string, unknown>;
  html?: HtmlDoc;
  csv?: CsvParse;
  /** PDF: words per page and chrome by repetition. */
  pdf?: PdfForm;
  /** A message: its MIME tree with raw spans. */
  mail?: Message;
  /** Byte spans the root term declares as chrome (markup). */
  chromeSpans: { start: number; end: number; selector: string }[];
  passes: Map<string, JsonObject>;
}

export async function loadArtifact(chain: Chain, o: Ontology, blake3: string, opts: { bytes?: boolean } = {}): Promise<Artifact> {
  const lines = unionView("corpus", readSubject(chain, "corpus", blake3)).map((l) => l.line);
  const attests = lines.find((l) => l.predicate === "attests");
  if (!attests) throw new AthError("NOT_FOUND", `${blake3}: no artifact subject in the chain`);
  const mime = String((attests.value as JsonObject).mime ?? "application/octet-stream");
  const bytesPath = resolveBytes(chain, blake3);
  const bytes = opts.bytes === false ? null : bytesPath ? new Uint8Array(require("node:fs").readFileSync(bytesPath)) : null;
  const a: Artifact = {
    blake3,
    chain,
    ontology: o,
    mime,
    attests,
    capturedFrom: lines.find((l) => l.predicate === "captured_from") ?? null,
    stored: lines,
    bytesPath,
    bytes,
    root: null,
    rootChain: [],
    tree: null,
    table: new ScopeTable(),
    forms: new Map(),
    chromeSpans: [],
    passes: new Map(),
  };
  for (const l of lines) if (l.predicate === "pass") a.passes.set(String((l.value as JsonObject).id), l);

  // parse the bytes under the op the mime root names: the classification probes (a header, a selector) read the form
  const mimeRoot = classify(o, { mime });
  if (mimeRoot) {
    const d = derivationAlong(a, refinesChain(o, mimeRoot));
    if (d) await parseForm(a, d);
  }
  // a member's container, for classification by package (D-epub)
  const containerRef = (a.capturedFrom?.value as { container?: string } | null)?.container;
  let containerRoot: string | null = null;
  if (typeof containerRef === "string" && containerRef.startsWith("corpus://")) {
    const cLines = unionView("corpus", readSubject(chain, "corpus", containerRef.slice("corpus://".length))).map((l) => l.line);
    const cAttests = cLines.find((l) => l.predicate === "attests");
    const cMime = cAttests ? String((cAttests.value as JsonObject).mime ?? "") : "";
    const cRoster = (cAttests?.value as { members?: { path?: unknown }[] } | undefined)?.members;
    const cMembers = Array.isArray(cRoster) ? cRoster.flatMap((m) => (typeof m?.path === "string" ? [m.path] : [])) : undefined;
    containerRoot = cMime ? classify(o, { mime: cMime, members: cMembers }) : null;
  }

  // the root term: a stored manifests at whole wins over matches
  const storedRoot = lines.find((l) => l.predicate === "manifests" && canonicalAt(String(l.at)) === "whole");
  const header = a.csv?.rows[0]?.cells.map((c) => c.value);
  const roster = (a.attests.value as { members?: { path?: unknown }[] }).members;
  const derivedRoot = classify(o, {
    mime,
    header,
    selectorMatches: a.html ? (s) => matchesSelector(a.html!, s) : undefined,
    head: bytes?.subarray(0, 16),
    container: containerRoot,
    path:
      typeof (a.capturedFrom?.value as { path?: unknown } | null)?.path === "string"
        ? (a.capturedFrom!.value as { path: string }).path
        : null,
    members: Array.isArray(roster) ? roster.flatMap((m) => (typeof m?.path === "string" ? [m.path] : [])) : undefined,
  });
  a.table.ensure("whole");
  if (derivedRoot) {
    a.table.addTerm("whole", derivedRoot, {}, "matches");
    a.root = derivedRoot;
  }
  if (storedRoot) a.root = String(storedRoot.term);
  // the mime root (axes, tree, derivation, physical) joins the expression root's chain
  if (a.root) {
    a.rootChain = refinesChain(o, a.root);
    if (mimeRoot && !a.rootChain.includes(mimeRoot))
      for (const t of refinesChain(o, mimeRoot)) if (!a.rootChain.includes(t)) a.rootChain.push(t);
    const tree = resolveAlong<string>(o, a.rootChain, "tree") ?? null;
    a.tree = tree ? (tree.startsWith("asserted") ? "asserted" : "derived") : null;
  }

  if (a.html && a.root) deriveHtml(a);
  if (a.csv && a.root) deriveCsv(a);
  if (a.mail && a.root) deriveMail(a);
  if (a.root) deriveSpine(a);
  await ensureForms(a);
  deriveReadings(a);
  overlayStored(a);
  return a;
}

/** Parse the bytes under an op once per family (and per parse-shaping arg); the family's typed slot is the same form. */
async function parseForm(a: Artifact, d: Derivation): Promise<void> {
  const op = opOf(d);
  const key = formKey(op, d.arg);
  if (a.forms.has(key) || !a.bytes) return;
  const form = await op.parse(a.bytes, d.arg);
  a.forms.set(key, form);
  if (op.family === "html" && !a.html) a.html = form as HtmlDoc;
  else if (op.family === "csv" && !a.csv) a.csv = form as CsvParse;
  else if (op.family === "pdf" && !a.pdf) a.pdf = form as PdfForm;
  else if (op.family === "mail" && !a.mail) a.mail = form as Message;
}

/** Every op a scope's terms name (a `timestamp` under `html.attr@1 datetime`) has its form resident before any
 * surface is asked for, so resolution stays synchronous. */
async function ensureForms(a: Artifact): Promise<void> {
  const root = derivationAlong(a, a.rootChain);
  if (root) await parseForm(a, root);
  for (const s of a.table.scopes.values()) {
    const d = derivationFor(a, s.at);
    if (d) await parseForm(a, d);
  }
}

/** A derived scope whose terms read text carries the surface its derivation yields as its reading, stamped
 * `derived:<op>@<v>[ <arg>]` from the ontology, never from code. `whole` carries none (its text is the export). */
function deriveReadings(a: Artifact): void {
  if (!a.bytes) return;
  for (const s of a.table.scopes.values()) {
    if (s.at === "whole" || s.readings.length) continue;
    if (effectiveRules(a.ontology, s.terms).reads !== "text") continue;
    const d = derivationAt(a, s.at, "text");
    if (d) s.readings.push({ aspect: "text", body: d.text, rev: `derived:${d.source}`, stored: false });
  }
}

/** The derived tree of a message (D-rfc822-parts): the header block, then every text body part as a scope in whole,
 * each with its mechanical blocks (paragraph · quote · signature) placed inside it; members are routes, not scopes. */
function deriveMail(a: Artifact): void {
  const m = a.mail!;
  const o = a.ontology;
  const expects = effectiveRules(o, a.rootChain).expects;
  const has = (t: string) => expects.includes(t) && o.terms.has(t);
  let ord = 0;
  if (has("message-header") && m.root.headerEnd > 0) {
    const at = `bytes=0,${m.root.headerEnd}`;
    a.table.addTerm(at, "message-header", {}, `${a.root}.expects`);
    a.table.place(at, "whole", ord++);
  }
  for (const p of leaves(m)) {
    if (!isBodyPart(p) || !has("message-body")) continue;
    const at = `bytes=${p.bodyStart},${p.bodyEnd}`;
    const fields: Record<string, unknown> = { part: p.path || "1", encoding: p.cte };
    if (p.charset) fields.charset = p.charset;
    a.table.addTerm(at, "message-body", fields, `${a.root}.expects`);
    a.table.place(at, "whole", ord++);
    let k = 0;
    for (const b of blocks(m, p)) {
      if (!has(b.kind)) continue;
      const bat = `bytes=${b.start},${b.end}`;
      if (bat === at) continue;
      a.table.addTerm(bat, b.kind, {}, `${a.root}.blocks`);
      a.table.place(bat, at, k++);
    }
  }
}

/** A container whose attestation carries a `spine` (D-epub): one route scope per spine item, in whole in reading
 * order, manifesting the term the root expects for a spine item. */
function deriveSpine(a: Artifact): void {
  const spine = (a.attests.value as { spine?: unknown }).spine;
  if (!Array.isArray(spine)) return;
  const expects = effectiveRules(a.ontology, a.rootChain).expects;
  const term = expects.find((t) => a.ontology.terms.has(t) && t !== "member");
  if (!term) return;
  spine.forEach((p, i) => {
    const at = `path=${encodeURIComponent(String(p))}`;
    a.table.addTerm(at, term, { path: String(p) }, `${a.root}.spine`);
    a.table.place(at, "whole", i);
  });
}

function deriveHtml(a: Artifact): void {
  const d = a.html!;
  const o = a.ontology;
  // select lines along the root chain, most specific first; a selector's term places under its `in` term by containment
  const decls = a.rootChain.flatMap((t) =>
    linesOf(o, t, "select")
      .map((l) => ({ term: t, decl: SelectDecl.safeParse(l.value) }))
      .flatMap((x) => (x.decl.success ? [{ owner: x.term, decl: x.decl.data }] : [])),
  );
  const made: { at: string; start: number; end: number; term: string; inTerm?: string }[] = [];
  for (const { owner, decl } of decls) {
    let els: ReturnType<typeof select>;
    try {
      els = select(d, decl.selector);
    } catch (e) {
      throw new AthError("CONFIG", `${owner}: selector '${decl.selector}' does not parse: ${(e as Error).message}`);
    }
    for (const el of els) {
      const span = spanOf(d, el);
      if (!span) continue;
      const at = `bytes=${span.start},${span.end}`;
      const fields: Record<string, unknown> = {};
      const rules = effectiveRules(o, [decl.term]);
      if (decl.field) {
        const v = el.attribs[decl.attr ?? decl.field];
        if (v !== undefined) {
          // an attribute value passes through the field's declared pattern, when it has one: the first capture is
          // the value (`#post-42` under `^#(post-\d+)$` is `post-42`, the key another concept is minted by)
          const pattern = rules.fields.find((f) => f.name === decl.field)?.pattern;
          const m = pattern ? new RegExp(pattern).exec(v) : null;
          fields[decl.field] = m ? (m[1] ?? m[0]) : v;
        }
      }
      if (decl.level !== undefined) fields.level = decl.level;
      // the designator fields of the term from the text, where declared (e.g. post.position from the first "#N")
      for (const f of rules.fields) {
        if (f.kind === "designator" && f.pattern && fields[f.name] === undefined) {
          const text = elementText(el);
          const m = new RegExp(f.pattern, "m").exec(text);
          if (m) fields[f.name] = m[0];
        }
      }
      a.table.addTerm(at, decl.term, fields, `${owner}.select ${decl.selector}`);
      made.push({ at, start: span.start, end: span.end, term: decl.term, inTerm: decl.in });
    }
  }
  // placement: parent = the nearest made scope manifesting `in`'s term that contains this one, else whole
  const byTerm = new Map<string, typeof made>();
  for (const m of made) byTerm.set(m.term, [...(byTerm.get(m.term) ?? []), m]);
  const parentOf = new Map<string, string>();
  for (const m of made) {
    let parent = "whole";
    if (m.inTerm) {
      const candidates = (byTerm.get(m.inTerm) ?? []).filter((c) => c.start <= m.start && c.end >= m.end && c.at !== m.at);
      candidates.sort((x, y) => y.start - x.start || x.end - y.end);
      if (candidates[0]) parent = candidates[0].at;
    }
    parentOf.set(m.at, parent);
  }
  // ord: siblings in document order
  const groups = new Map<string, typeof made>();
  for (const m of made) groups.set(parentOf.get(m.at)!, [...(groups.get(parentOf.get(m.at)!) ?? []), m]);
  for (const [parent, kids] of groups) {
    const uniq = [...new Map(kids.map((k) => [k.at, k])).values()].sort((x, y) => x.start - y.start || y.end - x.end);
    uniq.forEach((k, i) => {
      a.table.place(k.at, parent, i);
    });
  }
  // designator fields whose `where` names a descendant term take that descendant's text
  for (const m of made) {
    const s = a.table.get(m.at)!;
    for (const t of s.terms) {
      for (const f of effectiveRules(o, [t]).fields) {
        if (f.kind !== "designator" || !f.where || s.fields[f.name] !== undefined) continue;
        const holder = a.table.find(f.where, m.at);
        if (!holder || holder.at === m.at) continue;
        const el = select(d, "*").find((e) => {
          const sp = spanOf(d, e);
          const hm = made.find((x) => x.at === holder.at);
          return sp && hm && sp.start === hm.start && sp.end === hm.end;
        });
        if (!el) continue;
        const text = elementText(el);
        const mm = f.pattern ? new RegExp(f.pattern, "m").exec(text) : [text];
        if (mm) s.fields[f.name] = mm[0];
      }
    }
  }
  // chrome: declared selectors on the root chain
  for (const t of a.rootChain) {
    for (const l of linesOf(o, t, "chrome")) {
      for (const sel of Array.isArray(l.value) ? l.value.map(String) : []) {
        let els: ReturnType<typeof select> = [];
        try {
          els = select(d, sel);
        } catch {
          // a selector the engine cannot evaluate declares nothing
        }
        for (const el of els) {
          const sp = spanOf(d, el);
          if (sp) a.chromeSpans.push({ start: sp.start, end: sp.end, selector: sel });
        }
      }
    }
  }
}

function deriveCsv(a: Artifact): void {
  const p = a.csv!;
  const o = a.ontology;
  const header = p.rows[0];
  if (!header) return;
  const expects = effectiveRules(o, a.rootChain).expects;
  const headerTerm = expects.includes("header") ? "header" : null;
  const recordTerm = expects.includes("record") ? "record" : null;
  const columnTerm = expects.includes("column") ? "column" : null;
  const rev = (at: string) => {
    const d = derivationFor(a, at);
    return d ? `derived:${d.source}` : null;
  };
  if (headerTerm) {
    const s = a.table.addTerm("row=0", headerTerm, {}, `${a.root}.expects`);
    a.table.place("row=0", "whole", 0);
    const r = rev("row=0");
    if (r) s.readings.push({ aspect: "cells", body: header.cells.map((c) => c.value), rev: r, stored: false });
  }
  const shapes = a.rootChain.flatMap((t) =>
    linesOf(o, t, "shape")
      .map((l) => ShapeDecl.safeParse(l.value))
      .flatMap((r) => (r.success ? [r.data] : [])),
  );
  header.cells.forEach((cell, i) => {
    const shape = shapes.find((s) => s.col === cell.value);
    const term = shape?.term ?? columnTerm;
    if (!term) return;
    const { col: _c, term: _t, ...extra } = shape ?? { col: cell.value, term };
    a.table.addTerm(`col=${i}`, term, { name: cell.value, ...extra }, shape ? `${a.root}.shape` : `${a.root}.expects`);
  });
  if (recordTerm) {
    for (const r of p.rows.slice(1)) {
      const at = `row=${r.index}`;
      const s = a.table.addTerm(at, recordTerm, {}, `${a.root}.expects`);
      a.table.place(at, "whole", headerTerm ? r.index : r.index - 1);
      const rv = rev(at);
      if (rv) s.readings.push({ aspect: "cells", body: r.cells.map((c) => c.value), rev: rv, stored: false });
    }
  }
}

function overlayStored(a: Artifact): void {
  for (const l of a.stored) {
    const at = String(l.at ?? "");
    switch (l.predicate) {
      case "manifests": {
        const { at: _a, predicate: _p, term, pass: _ps, by: _b, ...fields } = l;
        const s = a.table.addTerm(at, String(term), fields as Record<string, unknown>);
        s.derived = false;
        s.stored.push(l);
        break;
      }
      case "in": {
        const v = l.value as { at: string; ord: number };
        const s = a.table.ensure(at);
        a.table.place(at, v.at, v.ord);
        s.derived = false;
        s.stored.push(l);
        break;
      }
      case "reads_as": {
        const s = a.table.ensure(at);
        s.readings = s.readings.filter((r) => r.aspect !== l.aspect);
        s.readings.push({ aspect: l.aspect as "text", body: l.body, rev: String(l.rev), stored: true });
        s.derived = false;
        s.stored.push(l);
        break;
      }
      case "walked":
      case "pass":
      case "attests":
      case "captured_from":
        a.table.ensure(at).stored.push(l);
        break;
    }
  }
}

/** The derived lines of a scope, as they would be written if they were stored (for `claims show --derived`). */
export function derivedLines(s: {
  at: string;
  terms: string[];
  fields: Record<string, unknown>;
  parent: string | null;
  ord: number | null;
  derivedBy: Record<string, string>;
  stored: JsonObject[];
}): JsonObject[] {
  const out: JsonObject[] = [];
  const storedTerms = new Set(s.stored.filter((l) => l.predicate === "manifests").map((l) => String(l.term)));
  const storedIn = s.stored.some((l) => l.predicate === "in");
  if (s.parent !== null && !storedIn) out.push({ at: s.at, predicate: "in", value: { at: s.parent, ord: s.ord }, derived: "tree" });
  for (const t of s.terms) {
    if (storedTerms.has(t)) continue;
    const line: JsonObject = { at: s.at, predicate: "manifests", term: t };
    for (const [k, v] of Object.entries(s.fields)) line[k] = v;
    line.derived = s.derivedBy[t] ?? "ontology";
    out.push(line);
  }
  return out;
}
