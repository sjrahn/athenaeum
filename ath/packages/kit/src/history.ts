// history.ts — one line per invocation in the instance's host state (§19.3.2): what ran, as whom, how it ended.
// Append-only; a torn line from a killed run is skipped, never rewritten.
import { appendFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { HistoryLine } from "./types.ts";

export const historyPath = (state: string) => join(state, "history.jsonl");

export function appendHistory(state: string, line: HistoryLine): void {
  mkdirSync(state, { recursive: true });
  appendFileSync(historyPath(state), `${JSON.stringify(line)}\n`);
}

export function readHistory(state: string): HistoryLine[] {
  const p = historyPath(state);
  if (!existsSync(p)) return [];
  const out: HistoryLine[] = [];
  for (const l of readFileSync(p, "utf8").split("\n")) {
    if (!l.trim()) continue;
    try {
      out.push(JSON.parse(l) as HistoryLine);
    } catch {
      // a torn line
    }
  }
  return out;
}
