// compare.ts — the reading check's comparisons (spec §13.4): a reading's body against the hint at its address, per
// aspect, after the scope's conventions are applied — tokens (longest common run, then squashed) for text, each cell
// as a contiguous run for cells, the multiset of letters, digits and operators for tex. Each returns the first
// divergence as a sentence for the verifier, or null. They never block.
import { stripTex } from "../norm/tex.ts";
import { normalize, squash } from "../norm/text.ts";

const tokens = (s: string) => normalize(s).toLowerCase().split(/\s+/).filter(Boolean);

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
