// jsonl.ts — the one way a line is written: compact JSON, non-ASCII unescaped, the subject key first, the predicate
// second, the attestation (`by` | `pass`) last, everything else in the order it was given. Reading is tolerant of
// order; writing is not, so a file round-trips byte-for-byte and a diff is a diff of content.
import { readFileSync } from "node:fs";

export type JsonObject = Record<string, unknown>;

const FIRST = ["at", "subject"];
const LAST = ["by", "pass"];

/** A line's keys in canonical order. */
export function orderKeys(o: JsonObject): string[] {
  const keys = Object.keys(o);
  const head = FIRST.filter((k) => keys.includes(k));
  const tail = LAST.filter((k) => keys.includes(k));
  const mid = keys.filter((k) => !FIRST.includes(k) && !LAST.includes(k) && k !== "predicate");
  return [...head, ...(keys.includes("predicate") ? ["predicate"] : []), ...mid, ...tail];
}

export function canonicalLine(o: JsonObject): string {
  const out: JsonObject = {};
  for (const k of orderKeys(o)) out[k] = o[k];
  return JSON.stringify(out);
}

/** Compact JSON of any value (arrays as-is, objects in insertion order); the body form a reading's rev hashes. */
export const compactJson = (v: unknown): string => JSON.stringify(v);

export function parseJsonl(text: string, where = "jsonl"): JsonObject[] {
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
    if (typeof v !== "object" || v === null || Array.isArray(v)) throw new Error(`${where}:${i + 1}: a line must be a JSON object`);
    out.push(v as JsonObject);
  }
  return out;
}

export function readJsonl(path: string): JsonObject[] {
  return parseJsonl(readFileSync(path, "utf8"), path);
}

export function serializeJsonl(lines: readonly JsonObject[]): string {
  return lines.length ? `${lines.map(canonicalLine).join("\n")}\n` : "";
}
