// generic.ts — the four generic lints (spec §13): G1 unit, G2 tree, G3 cover, G4 cite. A failing generic lint blocks
// a pass from signing.

import type { Artifact } from "../corpus/derive.ts";
import { isPageAt, parseAddress } from "../model/address.ts";
import { effectiveRules } from "../ontology/effective.ts";
import { textRuns } from "../ops/html/text.ts";
import type { Finding } from "./report.ts";

/** G1: every stored reads_as sits at a scope with a manifests whose term reads that aspect. */
export function g1Unit(a: Artifact): Finding[] {
  const out: Finding[] = [];
  for (const s of a.table.scopes.values()) {
    for (const r of s.readings.filter((x) => x.stored)) {
      if (!s.terms.length) {
        out.push({
          code: "G1",
          severity: "block",
          subject: a.blake3,
          at: s.at,
          msg: `reads_as ${r.aspect} at a scope that manifests nothing`,
        });
        continue;
      }
      const reads = effectiveRules(a.ontology, s.terms).reads;
      const ok = s.terms.some((t) => effectiveRules(a.ontology, [t]).reads === r.aspect);
      if (!ok)
        out.push({
          code: "G1",
          severity: "block",
          subject: a.blake3,
          at: s.at,
          msg: `reads_as ${r.aspect} but ${s.terms.join("+")} reads ${reads ?? "nothing"}`,
        });
    }
  }
  return out;
}

/** G2: every in resolves; ord contiguous from 0 per parent; no cycle; every non-axis scope reachable from whole. */
export function g2Tree(a: Artifact): Finding[] {
  const out: Finding[] = [];
  const t = a.table;
  for (const s of t.scopes.values()) {
    if (s.parent !== null && !t.get(s.parent))
      out.push({ code: "G2", severity: "block", subject: a.blake3, at: s.at, msg: `in names ${s.parent}, which is no scope` });
  }
  const parents = new Set([...t.scopes.values()].map((s) => s.parent).filter((p): p is string => p !== null));
  for (const p of parents) {
    const ords = t
      .children(p)
      .map((c) => c.ord ?? -1)
      .sort((x, y) => x - y);
    const expect = ords.map((_, i) => i);
    if (ords.some((o, i) => o !== expect[i]))
      out.push({
        code: "G2",
        severity: "block",
        subject: a.blake3,
        at: p,
        msg: `ord under ${p} is not contiguous from 0: ${ords.join(",")}`,
      });
  }
  // cycles
  for (const s of t.scopes.values()) {
    const seen = new Set<string>();
    let cur: string | null = s.at;
    while (cur !== null) {
      if (seen.has(cur)) {
        out.push({ code: "G2", severity: "block", subject: a.blake3, at: s.at, msg: `in chain cycles at ${cur}` });
        break;
      }
      seen.add(cur);
      cur = t.get(cur)?.parent ?? null;
    }
  }
  for (const s of t.unreachable()) {
    if (isPageAt(s.at)) continue;
    const m = parseAddress(s.at).members[0]!;
    if (m.kind === "col" && s.parent === null) continue; // a column axis
    if (s.at === "whole") continue;
    out.push({
      code: "G2",
      severity: "block",
      subject: a.blake3,
      at: s.at,
      msg: `${s.terms.join("+") || "scope"} is not reachable from whole by in (D-F2)`,
    });
  }
  return out;
}

export interface Coverage {
  /** Text characters in the derivation. */
  total: number;
  /** Inside a scope that reads. */
  inUnits: number;
  /** Inside declared or derived chrome. */
  chrome: number;
  remainder: number;
  ratio: number;
}

/** G3 (markup): the remainder — text runs outside every reading scope and outside declared chrome (D-F4). Reported,
 * never blocking on a derived tree. */
export function coverageHtml(a: Artifact): Coverage | null {
  if (!a.html) return null;
  const runs = textRuns(a.html);
  const units = [...a.table.scopes.values()]
    .filter((s) => s.readings.length && /^bytes=/.test(s.at))
    .map((s) => parseAddress(s.at).members[0]!);
  const inUnit = (start: number, end: number) => units.some((m) => m.kind === "bytes" && m.start <= start && m.end >= end);
  const inChrome = (start: number, end: number) => a.chromeSpans.some((c) => c.start <= start && c.end >= end);
  let total = 0;
  let inUnits = 0;
  let chrome = 0;
  for (const r of runs) {
    total += r.text.length;
    if (inUnit(r.start, r.end)) inUnits += r.text.length;
    else if (inChrome(r.start, r.end)) chrome += r.text.length;
  }
  const remainder = total - inUnits - chrome;
  return { total, inUnits, chrome, remainder, ratio: total ? remainder / total : 0 };
}

export function g3Cover(a: Artifact): Finding[] {
  if (a.tree === "derived") {
    for (const s of a.table.scopes.values()) {
      if (s.stored.some((l) => l.predicate === "walked")) {
        return [
          { code: "G3", severity: "block", subject: a.blake3, at: s.at, msg: "walked on a derived tree attests nothing (D-F4); remove it" },
        ];
      }
    }
  }
  return [];
}
