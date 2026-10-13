// history.ts — one line per invocation in <root>/.ath/history.jsonl: what ran, as whom, how it ended. Append-only.
import { appendFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { stateDir } from "./root.ts";
import type { HistoryLine } from "./types.ts";

export const historyPath = (root: string) => join(stateDir(root), "history.jsonl");

export function appendHistory(root: string, line: HistoryLine): void {
  mkdirSync(stateDir(root), { recursive: true });
  appendFileSync(historyPath(root), `${JSON.stringify(line)}\n`);
}

export function readHistory(root: string): HistoryLine[] {
  const p = historyPath(root);
  if (!existsSync(p)) return [];
  const out: HistoryLine[] = [];
  for (const l of readFileSync(p, "utf8").split("\n")) {
    if (!l.trim()) continue;
    try {
      out.push(JSON.parse(l) as HistoryLine);
    } catch {
      // a torn line from a killed run is skipped, never rewritten
    }
  }
  return out;
}
