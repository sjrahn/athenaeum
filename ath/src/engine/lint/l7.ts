// l7.ts — the reading against the bytes (spec §10.3, D-L7): for every stored reading, compare its body with the
// derivation at its address after the term's conventions and designator strip — per aspect: a token sequence diff
// for text, per cell as a contiguous run for cells, a character-class multiset for tex. Divergence is listed for a
// human; an `inspected` line by rev accepts it. Where the root declares no derivation, every reading is listed.
import type { JsonObject } from "../../lib/jsonl.ts";
import type { Artifact } from "../corpus/derive.ts";
import { derivationAt } from "../corpus/resolve.ts";
import type { Scope } from "../corpus/tree.ts";
import { stripTex } from "../norm/tex.ts";
import { normalize, squash } from "../norm/text.ts";
import { effectiveRules } from "../ontology/effective.ts";

export type L7State = "ok" | "diverges" | "accepted" | "no-derivation";

export interface L7Row {
  at: string;
  aspect: "text" | "cells" | "tex";
  rev: string;
  terms: string[];
  state: L7State;
  /** The first divergence, or the acceptance reason. */
  detail?: string;
  derivation?: string;
}

const tokens = (s: string) => normalize(s).toLowerCase().split(/\s+/).filter(Boolean);

/** Strip what the term's fields declare as designators (num, label, mark …) from the derivation's head/tail. */
function stripDesignators(a: Artifact, s: Scope, text: string): string {
  let t = text;
  for (const term of s.terms) {
    for (const f of effectiveRules(a.ontology, [term]).fields) {
      if (f.kind !== "designator") continue;
      const v = s.fields[f.name];
      if (typeof v !== "string" || !v) continue;
      const n = normalize(v);
      const nt = normalize(t);
      if (nt.startsWith(n)) t = nt.slice(n.length).trim();
      else if (nt.endsWith(n)) t = nt.slice(0, nt.length - n.length).trim();
      else t = nt;
    }
  }
  return t;
}

/** Conventions the reading applied and the derivation did not: footnote marks, bullets. */
function applyConventions(body: string, conventions: readonly string[]): string {
  let b = body;
  if (conventions.some((c) => c.includes("[^n]"))) b = b.replace(/\[\^\d+\]/g, "");
  b = b.replace(/^[•\-*]\s+/gm, "");
  return b;
}

function firstDiff(want: string[], got: string[]): string {
  const n = Math.min(want.length, got.length);
  for (let i = 0; i < n; i++) if (want[i] !== got[i]) return `token ${i}: reading '${want[i]}' vs derivation '${got[i]}'`;
  if (want.length !== got.length) return `length: reading ${want.length} tokens, derivation ${got.length}`;
  return "";
}

/** A footnote mark the reading wrote as `word[^n]` is a superscript glued to the word in the derivation (`word1`). */
function unglueMarks(body: string, derivation: string): string {
  let d = derivation;
  for (const m of body.matchAll(/(\S+)\[\^(\d+)\]/g))
    d = d.replace(new RegExp(`${m[1]!.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}${m[2]}(?!d)`), m[1]!);
  return d;
}

export function compareText(body: string, derivation: string, conventions: readonly string[]): string | null {
  const w = tokens(applyConventions(body, conventions));
  const g = tokens(unglueMarks(body, derivation));
  if (w.join(" ") === g.join(" ")) return null;
  if (squash(applyConventions(body, conventions)) === squash(unglueMarks(body, derivation))) return null;
  return firstDiff(w, g);
}

export function compareCells(body: unknown, derivation: string, conventions: readonly string[]): string | null {
  const cells: string[] = Array.isArray(body) ? body.flatMap((c) => (Array.isArray(c) ? c.map(String) : [String(c)])) : [String(body)];
  const hay = squash(derivation);
  for (const c of cells) {
    // a cell written as TeX ($\Delta T_{i,y}$) is compared through the same symbol map as a tex reading
    const needle = squash(stripTex(applyConventions(c, conventions)));
    if (!needle || needle === "-" || needle === "–") continue;
    if (!hay.includes(needle)) return `cell '${c.slice(0, 40)}' not a contiguous run of the row's words`;
  }
  return null;
}

const CLASS = /[\p{L}\p{N}+\-=×÷*/∑∏√∫≤≥≠<>()]/u;

function multiset(s: string): Map<string, number> {
  const m = new Map<string, number>();
  for (const ch of s.normalize("NFKC")) if (CLASS.test(ch)) m.set(ch, (m.get(ch) ?? 0) + 1);
  return m;
}

export function compareTex(body: string, derivation: string): string | null {
  const a = multiset(stripTex(body));
  const b = multiset(derivation.replace(/Equation\s*\(\d+\)/g, "").replace(/[\u2010-\u2015\u2212]/g, "-"));
  const keys = new Set([...a.keys(), ...b.keys()]);
  const diffs: string[] = [];
  for (const k of keys) {
    const x = a.get(k) ?? 0;
    const y = b.get(k) ?? 0;
    if (x !== y) diffs.push(`'${k}' ${x}≠${y}`);
  }
  return diffs.length ? `symbol counts differ: ${diffs.slice(0, 6).join(", ")}` : null;
}

export function l7(a: Artifact, inspected: readonly JsonObject[] = []): L7Row[] {
  const rows: L7Row[] = [];
  const accepted = new Map<string, string>();
  for (const l of inspected)
    if (l.predicate === "inspected") accepted.set(String((l.value as JsonObject).rev), String((l.value as JsonObject).why));
  for (const s of a.table.scopes.values()) {
    for (const r of s.readings.filter((x) => x.stored)) {
      const row: L7Row = { at: s.at, aspect: r.aspect, rev: r.rev, terms: s.terms, state: "ok" };
      const d = derivationAt(a, s.at, r.aspect);
      if (!d) {
        row.state = "no-derivation";
        rows.push(row);
        continue;
      }
      row.derivation = d.text.slice(0, 200);
      const conventions = effectiveRules(a.ontology, s.terms, [a.rootChain]).conventions;
      const deriv = stripDesignators(a, s, d.text);
      let diff: string | null;
      if (r.aspect === "text") diff = compareText(String(r.body), deriv, conventions);
      else if (r.aspect === "cells") diff = compareCells(r.body, d.text, conventions);
      else diff = compareTex(String(r.body), deriv);
      if (diff) {
        const why = accepted.get(r.rev);
        row.state = why !== undefined ? "accepted" : "diverges";
        row.detail = why !== undefined ? why : diff;
      }
      rows.push(row);
    }
  }
  return rows;
}
