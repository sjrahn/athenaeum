// compare.ts — the reading check's comparisons (spec §13.4): a reading's body against the hint at its address, per
// aspect, after the scope's conventions are applied — tokens (longest common run, then squashed) for text, each cell
// as a contiguous run for cells, the multiset of letters, digits and operators for tex. Each returns the first
// divergence as a sentence for the verifier, or null. They never block.
import { stripTex } from "../norm/tex.ts";
import { normalize, squash } from "../norm/text.ts";

type Convention = Record<string, unknown>;

const tokens = (s: string) => normalize(s).toLowerCase().split(/\s+/).filter(Boolean);

/** The footnote mark pattern a scope's conventions declare, or null. */
const footnotes = (cs: readonly Convention[]): RegExp | null => {
  const p = cs.find((c) => typeof c.footnotes === "string")?.footnotes as string | undefined;
  return p ? new RegExp(p, "g") : null;
};

/** The reading with what its conventions write apart from the rendering removed: footnote marks. */
function readingSide(body: string, cs: readonly Convention[]): string {
  const fn = footnotes(cs);
  return fn ? body.replace(fn, "") : body;
}

/** The hint as the conventions read it: a footnote mark the reading wrote is a superscript glued to its word in the
 * hint (`batch1`); list markers dropped where `bullets: drop`; line-end hyphenation joined where `hyphens: rejoin`. */
function hintSide(body: string, hint: string, cs: readonly Convention[]): string {
  let h = hint;
  const fn = footnotes(cs);
  if (fn)
    for (const m of body.matchAll(new RegExp(`(\\S+?)(${fn.source})`, "g"))) {
      const digits = (m[2]!.match(/\d+/) ?? [""])[0];
      if (digits) h = h.replace(new RegExp(`${m[1]!.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}${digits}(?!\\d)`), m[1]!);
    }
  if (cs.some((c) => c.bullets === "drop")) h = h.replace(/^[ \t]*(?:[•\-*‣◦·]|\d+[.)])[ \t]+/gm, "");
  if (cs.some((c) => c.hyphens === "rejoin")) h = h.replace(/(\p{L})-\n(\p{L})/gu, "$1$2");
  return h;
}

/** The first token of `want` the longest common subsequence with `got` leaves out, as a sentence; or null. */
function lcsDiff(want: string[], got: string[]): string | null {
  const n = want.length;
  const m = got.length;
  if (n * m > 4_000_000) return want.join(" ") === got.join(" ") ? null : "the bodies differ (too long to align)";
  const L: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--) L[i]![j] = want[i] === got[j] ? L[i + 1]![j + 1]! + 1 : Math.max(L[i + 1]![j]!, L[i]![j + 1]!);
  if (L[0]![0] === n && n === m) return null;
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (want[i] === got[j]) {
      i++;
      j++;
    } else if (L[i + 1]![j]! >= L[i]![j + 1]!) return `token ${i}: the reading has '${want[i]}' where the hint has '${got[j]}'`;
    else return `token ${i}: the hint has '${got[j]}' that the reading lacks`;
  }
  return i < n ? `token ${i}: the reading has '${want[i]}' past the hint's end` : `the hint goes on past the reading: '${got[j]}'`;
}

export function compareText(body: string, hint: string, conventions: readonly Convention[]): string | null {
  const r = readingSide(body, conventions);
  const h = hintSide(body, hint, conventions);
  // token by token first; a body that differs only in whitespace and hyphens still agrees, squashed (§13.4.2)
  const d = lcsDiff(tokens(r), tokens(h));
  return d === null || squash(r) === squash(h) ? null : d;
}

export function compareCells(body: unknown, derivation: string, conventions: readonly Convention[]): string | null {
  const cells: string[] = Array.isArray(body) ? body.flatMap((c) => (Array.isArray(c) ? c.map(String) : [String(c)])) : [String(body)];
  const hay = squash(derivation);
  for (const c of cells) {
    // a cell written as TeX ($\Delta T_{i,y}$) is compared through the same symbol map as a tex reading
    const needle = squash(stripTex(readingSide(c, conventions)));
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

/** tex (§13.4.5): control words to their symbols, braces and script marks dropped, the label a scope's designator
 * names dropped from the hint; the multisets of letters, digits and operators agree. */
export function compareTex(body: string, hint: string, labels: readonly string[] = []): string | null {
  let h = hint;
  for (const l of labels) h = h.split(l).join(" ");
  const a = multiset(stripTex(body));
  const b = multiset(h.replace(/[\u2010-\u2015\u2212]/g, "-"));
  const keys = new Set([...a.keys(), ...b.keys()]);
  const diffs: string[] = [];
  for (const k of keys) {
    const x = a.get(k) ?? 0;
    const y = b.get(k) ?? 0;
    if (x !== y) diffs.push(`'${k}' ${x}≠${y}`);
  }
  return diffs.length ? `symbol counts differ: ${diffs.slice(0, 6).join(", ")}` : null;
}
