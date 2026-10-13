// lineage.ts — the rows a correction, re-key or supersession leaves behind (spec §4.2, D-D5): append-only, in the
// top layer, one per identity whose content changed.
import { appendFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import type { JsonObject } from "../../lib/jsonl.ts";
import { canonicalLine } from "../../lib/jsonl.ts";
import type { Chain } from "./config.ts";
import { lineagePath } from "./store.ts";

export interface LineageRow {
  op: "correct" | "delete" | "rekey" | "supersede" | "regenerate";
  subject: string;
  identity: string;
  was?: JsonObject | null;
  now?: JsonObject | null;
  why?: string;
  by: string;
  date: string;
}

export function appendLineage(chain: Chain, kind: "corpus" | "ledger", row: LineageRow): void {
  const p = lineagePath(chain.top, kind);
  mkdirSync(dirname(p), { recursive: true });
  appendFileSync(p, `${canonicalLine(row as unknown as JsonObject)}\n`);
}
