// canonical.ts — the one serialisation of a line (spec §6.4.2): compact JSON, LF-terminated, non-ASCII unescaped,
// keys `id`, then `pred`, then every other key in code-point order, then `ev`, then the authorship (`by` | `pass`).
// Nested objects' keys in code-point order; arrays keep their order; numbers in their shortest round-trip form;
// strings escape only `"`, `\` and control characters. Every hash over JSON is over this form.
export type Json = null | boolean | number | string | Json[] | { [k: string]: Json };
export type JsonObject = Record<string, unknown>;

/** Compare two strings by Unicode code point (not UTF-16 code unit). */
export function byCodePoint(a: string, b: string): number {
  const ia = a[Symbol.iterator]();
  const ib = b[Symbol.iterator]();
  for (;;) {
    const x = ia.next();
    const y = ib.next();
    if (x.done || y.done) return x.done && y.done ? 0 : x.done ? -1 : 1;
    const d = x.value.codePointAt(0)! - y.value.codePointAt(0)!;
    if (d) return d;
  }
}

const HEAD = ["id", "pred"];
const TAIL = ["ev", "by", "pass"];

/** A value with every nested object's keys in code-point order. */
export function sortedValue(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(sortedValue);
  if (v && typeof v === "object") {
    const o = v as JsonObject;
    return Object.fromEntries(
      Object.keys(o)
        .filter((k) => o[k] !== undefined)
        .sort(byCodePoint)
        .map((k) => [k, sortedValue(o[k])]),
    );
  }
  return v;
}

/** A line's keys in canonical order. */
export function lineKeys(o: JsonObject): string[] {
  const keys = Object.keys(o).filter((k) => o[k] !== undefined);
  const head = HEAD.filter((k) => keys.includes(k));
  const tail = TAIL.filter((k) => keys.includes(k));
  const mid = keys.filter((k) => !HEAD.includes(k) && !TAIL.includes(k)).sort(byCodePoint);
  return [...head, ...mid, ...tail];
}

/** The canonical serialisation of one line, without its LF. */
export function canonicalLine(o: JsonObject): string {
  return JSON.stringify(Object.fromEntries(lineKeys(o).map((k) => [k, sortedValue(o[k])])));
}

/** Any JSON value in canonical form (nested keys sorted, compact): what a hash over JSON is taken over. */
export const canonicalJson = (v: unknown): string => JSON.stringify(sortedValue(v));

/** A file of lines: each canonical and LF-terminated, in the order given (the caller sorts by identity). */
export const serializeLines = (lines: readonly JsonObject[]): string => lines.map((l) => `${canonicalLine(l)}\n`).join("");

/** Parse a file of lines; a blank line is skipped, anything else that is not a JSON object is refused. */
export function parseLines(text: string, where: string): JsonObject[] {
  const out: JsonObject[] = [];
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i]!;
    if (!l.trim()) continue;
    let v: unknown;
    try {
      v = JSON.parse(l);
    } catch (e) {
      throw new Error(`${where}:${i + 1}: not JSON: ${(e as Error).message}`);
    }
    if (typeof v !== "object" || v === null || Array.isArray(v)) throw new Error(`${where}:${i + 1}: a line is a JSON object`);
    out.push(v as JsonObject);
  }
  return out;
}
