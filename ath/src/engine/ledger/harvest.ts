// harvest.ts — mechanical minting (spec §9.4, D-F6, D-F7b): for every scope manifesting a term that carries
// `concept` lines, mint the concept keyed as declared, one claim per mapped predicate, each entry anchored at the
// scope or cell that evidences it and bound to the derivation; `by: harvest:<term>@<pin>`; repeat appearances accrue
// as entries on the one claim. A map value names a term, `term.field`, `predicate.field`, `@attr`, an edge `x → t`,
// a column name (tabular), a cell index, or `{…}` for a grouped object.
import { AthError } from "../../kit/errors.ts";
import type { JsonObject } from "../../lib/jsonl.ts";
import { canonicalLine } from "../../lib/jsonl.ts";
import type { Artifact } from "../corpus/derive.ts";
import { surfaceFor } from "../corpus/resolve.ts";
import type { Scope } from "../corpus/tree.ts";
import type { Chain } from "../layer/config.ts";
import { readSubject, unionView, writeSubject } from "../layer/store.ts";
import { scopeAt } from "../model/address.ts";
import { identityKey } from "../model/line.ts";
import { ConceptDecl } from "../model/term.ts";
import { refinesChain } from "../ontology/chain.ts";
import { harvestPin } from "../ontology/hash.ts";
import { linesOf, type Ontology } from "../ontology/load.ts";
import { CSV_OP } from "../ops/csv/parse.ts";
import { HTML_ATTR_OP, HTML_TEXT_OP } from "../ops/html/text.ts";
import { conceptOwes } from "./demand.ts";
import { mintSlug } from "./file.ts";

interface Resolved {
  /** The value the claim carries (string, number, or an object for a group). */
  value: unknown;
  /** The evidence entries that support it. */
  entries: { anchor: string; quote: string; reading: string }[];
  /** For an edge: the slug of the object concept. */
  object?: string;
}

interface Minted {
  slug: string;
  term: string;
  decl: ConceptDecl;
  scope: Scope;
  keyValue: string;
  claims: { predicate: string; r: Resolved }[];
}

const SENTINELS = (o: Ontology, chain: readonly string[]) => {
  const out = new Set<string>();
  for (const t of chain)
    for (const l of linesOf(o, t, "sentinel")) for (const v of Array.isArray(l.value) ? l.value : [l.value]) out.add(String(v));
  return out;
};

export interface HarvestReport {
  concepts: number;
  claims: number;
  entries: number;
  written: string[];
  skipped: string[];
}

function csvHeader(a: Artifact): string[] | null {
  return a.csv?.rows[0]?.cells.map((c) => c.value) ?? null;
}

function typedCell(a: Artifact, col: number, raw: string): unknown {
  const colScope = a.table.get(`col=${col}`);
  const term = colScope?.terms[0];
  if (!term) return raw;
  const chain = refinesChain(a.ontology, term);
  if (chain.includes("integer")) return /^-?\d+$/.test(raw) ? Number(raw) : raw;
  if (chain.includes("monetary-amount")) {
    const s = raw.replace(/^'|'$/g, "");
    return /^-?\d+(\.\d+)?$/.test(s) ? Number(s) : raw;
  }
  return raw;
}

/** Resolve one map reference within a scope. */
function resolveRef(a: Artifact, s: Scope, ref: string | number, minted: Minted[]): Resolved | null {
  const o = a.ontology;
  const rootChain = a.rootChain;
  const sentinels = SENTINELS(o, rootChain);
  const blake = a.blake3;
  if (typeof ref === "number") {
    const r = s.readings.find((x) => x.aspect === "cells");
    const cells = Array.isArray(r?.body) ? (r!.body as unknown[]) : null;
    const v = cells?.[ref];
    if (v === undefined || v === null || v === "") return null;
    return { value: String(v), entries: [{ anchor: `corpus://${blake}?${s.at}&cells`, quote: String(v), reading: r!.rev }] };
  }
  if (ref.startsWith("{") && ref.endsWith("}")) {
    const parts = ref
      .slice(1, -1)
      .split(",")
      .map((p) => p.trim())
      .filter(Boolean);
    const obj: JsonObject = {};
    const entries: Resolved["entries"] = [];
    for (const p of parts) {
      const r = resolveRef(a, s, p, minted);
      if (!r) continue;
      const nameSrc = p.split("→")[0]!.trim();
      const key = nameSrc
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_|_$/g, "");
      obj[key] = r.value;
      if (r.object) obj[`${key}_concept`] = r.object;
      entries.push(...r.entries.slice(0, 1));
    }
    if (!Object.keys(obj).length) return null;
    return { value: obj, entries };
  }
  const edge = ref.split("→");
  if (edge.length === 2) {
    const left = edge[0]!.trim();
    const targetTerm = edge[1]!.trim();
    const inner = resolveRef(a, s, left, minted);
    if (!inner) return null;
    // the object: a minted concept of that term whose key value equals the resolved value, else whose scope lies in s
    const byValue = minted.find((m) => m.term === targetTerm && m.keyValue === String(inner.value));
    const byScope = minted.find(
      (m) => m.term === targetTerm && (m.scope.at === s.at || a.table.within(s.at).some((w) => w.at === m.scope.at)),
    );
    const target = byValue ?? byScope;
    if (!target) return null;
    return { value: inner.value, entries: inner.entries, object: target.slug };
  }
  if (ref.startsWith("@")) {
    const attr = ref.slice(1);
    const sf = surfaceFor(a, s.at, { kind: "derived", op: HTML_ATTR_OP, arg: attr });
    if (!sf) return null;
    return {
      value: sf.text,
      entries: [{ anchor: `corpus://${blake}?${s.at}`, quote: sf.text, reading: `derived:${HTML_ATTR_OP} ${attr}` }],
    };
  }
  const dot = /^([a-z_][a-z0-9_-]*)\.([a-z_][a-z0-9_-]*)$/.exec(ref);
  if (dot && (dot[1] === "captured_from" || dot[1] === "attests")) {
    const sf = surfaceFor(a, "whole", { kind: "line", predicate: dot[1]!, field: dot[2]! });
    if (!sf) return null;
    return { value: sf.text, entries: [{ anchor: `corpus://${blake}?whole`, quote: sf.text, reading: `line:${dot[1]} ${dot[2]}` }] };
  }
  if (dot && o.terms.has(dot[1]!)) {
    const holder = a.table.find(dot[1]!, s.at);
    if (!holder) return null;
    const v = holder.fields[dot[2]!];
    if (v === undefined) return null;
    const text = typeof v === "string" ? v : JSON.stringify(v);
    return { value: text, entries: [{ anchor: `corpus://${blake}?${holder.at}`, quote: text, reading: `line:manifests ${dot[2]}` }] };
  }
  // a column name (tabular)
  const header = csvHeader(a);
  if (header && a.csv) {
    const col = header.indexOf(ref);
    if (col !== -1) {
      const m = /^row=(\d+)$/.exec(s.at);
      if (!m) return null;
      const row = a.csv.rows[Number(m[1])];
      const cell = row?.cells[col];
      if (!cell || cell.value === "" || sentinels.has(cell.value)) return null;
      return {
        value: typedCell(a, col, cell.value),
        entries: [{ anchor: `corpus://${blake}?row=${m[1]}&col=${col}`, quote: cell.value, reading: `derived:${CSV_OP}` }],
      };
    }
  }
  // a key of a key-value table (the term's `keys` line): the row under s whose first cell is the key; its second cell
  const chain = [...new Set(s.terms.flatMap((t) => refinesChain(o, t)))];
  const keys = chain.flatMap((t) => linesOf(o, t, "keys").flatMap((l) => (Array.isArray(l.value) ? l.value.map(String) : [])));
  const same = (x: unknown, y: string) => String(x).trim().toLowerCase() === y.trim().toLowerCase();
  if (keys.some((k) => same(k, ref))) {
    for (const row of rowsUnder(a, s)) {
      const r = row.readings.find((x) => x.aspect === "cells")!;
      const cells = r.body as unknown[];
      if (!same(cells[0], ref)) continue;
      const v = cells[1];
      if (v === undefined || v === null || v === "" || v === "-") return null;
      return { value: String(v), entries: [{ anchor: `corpus://${blake}?${row.at}&cells`, quote: String(v), reading: r.rev }] };
    }
    return null;
  }
  // a named cell (the term's `cells` line names the columns): the cell at that index
  const names = chain.flatMap((t) => linesOf(o, t, "cells").flatMap((l) => (Array.isArray(l.value) ? l.value.map(String) : [])));
  const idx = names.indexOf(ref);
  if (idx !== -1) {
    const holder = rowsUnder(a, s)[0];
    return holder ? resolveRef(a, holder, idx, minted) : null;
  }
  // a key in a text scope written as `Key: value` lines
  const text = s.readings.find((x) => x.aspect === "text" && typeof x.body === "string");
  if (text && /:$/.test(ref) === false) {
    const line = (text.body as string).split("\n").find((l) => same(l.split(":")[0], ref));
    if (line) {
      const v = line.slice(line.indexOf(":") + 1).trim();
      if (v) return { value: v, entries: [{ anchor: `corpus://${blake}?${s.at}&text`, quote: v, reading: text.rev }] };
    }
  }
  // a term: the scope (self or nearest descendant) manifesting it; its text surface
  if (o.terms.has(ref)) {
    const holder = s.terms.includes(ref) ? s : a.table.find(ref, s.at);
    if (!holder) return null;
    const r = holder.readings.find((x) => x.aspect === "text") ?? holder.readings[0];
    if (!r) return null;
    const text = typeof r.body === "string" ? r.body : JSON.stringify(r.body);
    if (!text) return null;
    return { value: text, entries: [{ anchor: `corpus://${blake}?${holder.at}&${r.aspect}`, quote: text, reading: r.rev }] };
  }
  return null;
}

/** The scopes with a cells reading at or under `s`: itself, then its tree descendants, then what its box contains. */
function rowsUnder(a: Artifact, s: Scope): Scope[] {
  const seen = new Set<string>();
  const out: Scope[] = [];
  for (const c of [s, ...a.table.walk(s.at), ...a.table.within(s.at)]) {
    if (seen.has(c.at) || !c.readings.some((r) => r.aspect === "cells" && Array.isArray(r.body))) continue;
    seen.add(c.at);
    out.push(c);
  }
  return out;
}

/** The scopes a key is read from under an owner scope. */
function keyHolders(a: Artifact, owner: Scope, key: string, header: string[] | null): Scope[] {
  const o = a.ontology;
  if (key.startsWith("@") || /^(captured_from|attests)\./.test(key)) return [owner];
  const dot = /^([a-z_][a-z0-9_-]*)(?:\.[a-z_][a-z0-9_-]*)?$/.exec(key);
  if (dot && o.terms.has(dot[1]!)) return a.table.findAll(dot[1]!, owner.at);
  if (header?.includes(key))
    return [...a.table.scopes.values()].filter((s) => /^row=[1-9]\d*$/.test(s.at) && s.readings.some((r) => r.aspect === "cells"));
  return [owner];
}

/** Harvest one artifact: returns the concept files to write (slug → lines), merged into what exists. */
export function harvestArtifact(
  a: Artifact,
  pin: string,
  o: { dryRun?: boolean; onlyTerm?: string } = {},
): { minted: Minted[]; files: Map<string, JsonObject[]>; report: HarvestReport } {
  const ont = a.ontology;
  const decls: { owner: string; decl: ConceptDecl }[] = [];
  const termsInTable = new Set<string>();
  for (const s of a.table.scopes.values()) for (const t of s.terms) termsInTable.add(t);
  for (const t of termsInTable) {
    for (const anc of refinesChain(ont, t)) {
      for (const l of linesOf(ont, anc, "concept")) {
        const r = ConceptDecl.safeParse(l.value);
        if (r.success) decls.push({ owner: t, decl: r.data });
      }
    }
  }
  const uniq = new Map<string, { owner: string; decl: ConceptDecl }>();
  for (const d of decls) uniq.set(`${d.owner}|${d.decl.term}|${d.decl.key ?? ""}`, d);

  // pass 1: mint by key — one concept per holder of the key (every scope of the key's term under the owner scope,
  // every record row for a column key, the owner scope itself for an attribute or op-line key)
  const minted: Minted[] = [];
  const header = csvHeader(a);
  for (const { owner, decl } of uniq.values()) {
    if (o.onlyTerm && decl.term !== o.onlyTerm) continue;
    for (const ownerScope of a.table.findAll(owner)) {
      if (!decl.key) {
        const slug = mintSlug(decl.term, a.blake3.slice(0, 12), { slug: "{term}-{key}" });
        minted.push({ slug, term: decl.term, decl, scope: ownerScope, keyValue: a.blake3, claims: [] });
        continue;
      }
      const holders = keyHolders(a, ownerScope, decl.key, header);
      for (const h of holders) {
        const k = resolveRef(a, h, decl.key, minted);
        if (!k) continue;
        const keyValue = String(k.value);
        const extra = decl as unknown as { slug?: string; extract?: string; case?: string };
        let slug: string;
        try {
          slug = mintSlug(decl.term, keyValue, { slug: extra.slug, extract: extra.extract, case: extra.case });
        } catch {
          continue;
        }
        minted.push({ slug, term: decl.term, decl, scope: h, keyValue, claims: [] });
      }
    }
  }
  // pass 2: claims
  for (const m of minted) {
    for (const [pred, ref] of Object.entries(m.decl.claims)) {
      if (ref === "*") continue; // document-wide rows: a later ruling (revision-history)
      // an edge whose left side is a term names every scope of that term under this one: one edge per minted
      // concept found there, cited by that concept's key (a container has no text of its own to quote)
      const edge = typeof ref === "string" ? ref.split("→") : [];
      if (edge.length === 2 && ont.terms.has(edge[0]!.trim())) {
        const leftTerm = edge[0]!.trim();
        const targetTerm = edge[1]!.trim();
        const holders = a.table.findAll(leftTerm, m.scope.at).filter((h) => h.at !== m.scope.at || m.scope.terms.includes(leftTerm));
        let any = false;
        for (const h of holders) {
          const target =
            minted.find((t) => t.term === targetTerm && t.scope.at === h.at) ??
            minted.find((t) => t.term === targetTerm && a.table.within(h.at).some((w) => w.at === t.scope.at));
          if (!target?.decl.key) continue;
          const key = resolveRef(a, target.scope, target.decl.key, minted);
          if (!key) continue;
          m.claims.push({ predicate: pred, r: { value: key.value, entries: key.entries, object: target.slug } });
          any = true;
        }
        if (any) continue;
      }
      let r = resolveRef(a, m.scope, ref, minted);
      if (!r && m.scope.parent) {
        const parent = a.table.get(m.scope.parent);
        if (parent) r = resolveRef(a, parent, ref, minted);
      }
      if (r) m.claims.push({ predicate: pred, r });
    }
  }
  // assemble lines per slug
  const by = `harvest:${a.root}@${harvestPin(pin)}`;
  const files = new Map<string, JsonObject[]>();
  const report: HarvestReport = { concepts: 0, claims: 0, entries: 0, written: [], skipped: [] };
  const slugs = [...new Set(minted.map((m) => m.slug))];
  for (const slug of slugs) {
    const group = minted.filter((m) => m.slug === slug);
    const term = group[0]!.term;
    const owes = conceptOwes(ont, [term]);
    const lines: JsonObject[] = [{ subject: slug, predicate: "term", value: term }];
    const manifested = new Set<string>();
    for (const m of group) {
      const at = m.decl.group ? m.scope.at : m.scope.at;
      manifested.add(`corpus://${a.blake3}?${scopeAt(at)}`);
    }
    for (const v of manifested) lines.push({ subject: slug, predicate: "manifested_by", value: v });
    const claimMap = new Map<string, JsonObject>();
    for (const m of group) {
      for (const { predicate, r } of m.claims) {
        const kind = owes.includes(predicate) ? "authoritative" : "direct";
        const entries = r.entries.map((e) => ({ anchor: e.anchor, quote: e.quote, kind, mode: "stated", reading: e.reading }));
        const line: JsonObject =
          r.object !== undefined ? { subject: slug, predicate, object: r.object } : { subject: slug, predicate, value: r.value };
        if (r.object !== undefined && typeof r.value === "string" && r.value !== r.object) line.qualifiers = { as: r.value };
        const id = identityKey("ledger", line);
        const prev = claimMap.get(id);
        if (prev) {
          const have = new Set((prev.evidence as JsonObject[]).map((e) => `${e.anchor}|${e.quote}`));
          for (const e of entries) if (!have.has(`${e.anchor}|${e.quote}`)) (prev.evidence as JsonObject[]).push(e);
        } else claimMap.set(id, { ...line, evidence: entries, by });
      }
    }
    lines.push(...claimMap.values());
    files.set(slug, lines);
    report.concepts++;
    report.claims += claimMap.size;
    for (const c of claimMap.values()) report.entries += (c.evidence as unknown[]).length;
  }
  return { minted, files, report };
}

/** Write harvested concept files into the top layer, merging evidence into existing harvest claims and leaving
 * authored lines untouched. */
export function writeHarvest(chain: Chain, files: Map<string, JsonObject[]>, report: HarvestReport): void {
  for (const [slug, lines] of files) {
    const existing = unionView("ledger", readSubject(chain, "ledger", slug)).filter((l) => l.layer === chain.top);
    const byId = new Map<string, JsonObject>();
    for (const l of existing) byId.set(identityKey("ledger", l.line), l.line);
    let changed = false;
    for (const l of lines) {
      const id = identityKey("ledger", l);
      const prev = byId.get(id);
      if (!prev) {
        byId.set(id, l);
        changed = true;
        continue;
      }
      if (typeof prev.by === "string" && String(prev.by).startsWith("harvest:") && Array.isArray(l.evidence)) {
        const have = new Set((prev.evidence as JsonObject[]).map((e) => `${e.anchor}|${e.quote}`));
        const merged = [...(prev.evidence as JsonObject[])];
        for (const e of l.evidence as JsonObject[]) if (!have.has(`${e.anchor}|${e.quote}`)) merged.push(e);
        const next = { ...prev, evidence: merged, by: l.by };
        if (canonicalLine(next) !== canonicalLine(prev)) {
          byId.set(id, next);
          changed = true;
        }
      }
      // an authored line at the same identity stays
    }
    if (changed || !existing.length) {
      writeSubject(chain, "ledger", slug, [...byId.values()]);
      report.written.push(slug);
    } else report.skipped.push(slug);
  }
}

export function requireRoot(a: Artifact): string {
  if (!a.root) throw new AthError("CONFIG", `${a.blake3}: no term matches this artifact; nothing to harvest`);
  return a.root;
}

export { HTML_TEXT_OP };
