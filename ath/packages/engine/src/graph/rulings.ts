// rulings.ts — how the owner steers an instance (spec §13.5): the lines of `rulings.jsonl`, each `{id, pred, date,
// val, by: owner}`. `distrust` a testimony, an op's output at a scope, or a pass — everything bound through it is
// held; `accept` a finding — a reading-check divergence by scope and revision; `seek` a selection, creating demand and
// relevance; `defer` and `decline` demand. A ruling never asserts, supports or refutes a claim, is never evidence and
// is never projected. An extension holds its base's `distrust` and `accept` rulings, not its `seek`, `defer` or
// `decline`.
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { byCodePoint, canonicalLine, type JsonObject, parseLines } from "@ath/kit/canonical.ts";
import { writeAtomic } from "@ath/kit/fs.ts";
import { chain, type Instance } from "../instance/instance.ts";

export type RulingPred = "distrust" | "accept" | "seek" | "defer" | "decline";
export const RULINGS: readonly RulingPred[] = ["distrust", "accept", "seek", "defer", "decline"];

export interface Ruling extends JsonObject {
  id: string;
  pred: RulingPred;
  date: string;
  val: JsonObject;
  by: "owner";
}

export const rulingsPath = (i: Instance) => join(i.root, "rulings.jsonl");

export function ownRulings(i: Instance): Ruling[] {
  const p = rulingsPath(i);
  if (!existsSync(p)) return [];
  return parseLines(readFileSync(p, "utf8"), "rulings.jsonl") as Ruling[];
}

/** The rulings an instance relies on: its own, and its bases' `distrust` and `accept` (§13.5.4). */
export function rulingsOf(i: Instance): (Ruling & { instance: string })[] {
  const out: (Ruling & { instance: string })[] = [];
  for (const [k, x] of chain(i).entries())
    for (const r of ownRulings(x)) if (k === 0 || r.pred === "distrust" || r.pred === "accept") out.push({ ...r, instance: x.config.name });
  return out;
}

/** Why a ruling's value is not the shape its predicate takes, or null. */
export function rulingProblem(r: Ruling): string | null {
  if (!/^r[1-9]\d*$/.test(r.id)) return "an id is r<n>";
  if (!RULINGS.includes(r.pred)) return `${r.pred} is not a ruling`;
  if (r.by !== "owner") return "a ruling is by: owner";
  const v = r.val;
  if (!v || typeof v !== "object") return "a ruling's value is a mapping";
  const on = v.on;
  switch (r.pred) {
    case "distrust":
      return typeof on === "string" && /^ath:\/\/[0-9a-z-]+([?#].+)?$/.test(on)
        ? null
        : "distrust names a testimony, an op's output at a scope (with `op`) or a pass: {on: ath://…}";
    case "accept":
      return typeof on === "string" && (typeof v.rev === "string" || typeof v.finding === "string")
        ? null
        : "accept names a finding: {on: ath://<hash>?<at>, rev} or {on, finding}";
    case "seek":
      return v.select && typeof v.select === "object" ? null : "seek names a selection: {select: {kind | form | origin | entity}, owes?}";
    case "defer":
    case "decline":
      return typeof on === "string" || (v.select && typeof v.select === "object")
        ? null
        : `${r.pred} names a demand item or a selection: {on, demand?} or {select}`;
  }
}

export function writeRulings(i: Instance, rulings: readonly Ruling[]): void {
  const sorted = [...rulings].sort((a, b) => Number(a.id.slice(1)) - Number(b.id.slice(1)) || byCodePoint(a.id, b.id));
  writeAtomic(rulingsPath(i), sorted.map((r) => `${canonicalLine(r)}\n`).join(""));
}

export const nextRulingId = (i: Instance): string => `r${Math.max(0, ...ownRulings(i).map((r) => Number(r.id.slice(1)) || 0)) + 1}`;

/** What a distrust reaches: testimony and artifacts by hash, op output by anchor and op, passes by subject and id. */
export interface Distrusts {
  hashes: Set<string>;
  ops: { anchor: string; op?: string }[];
  passes: Set<string>;
}

export function distrusts(rulings: readonly Ruling[]): Distrusts {
  const d: Distrusts = { hashes: new Set(), ops: [], passes: new Set() };
  for (const r of rulings) {
    if (r.pred !== "distrust") continue;
    const on = String(r.val.on);
    if (on.includes("#")) d.passes.add(on.replace(/^ath:\/\//, ""));
    else if (on.includes("?")) d.ops.push({ anchor: on, ...(typeof r.val.op === "string" ? { op: r.val.op } : {}) });
    else d.hashes.add(on.replace(/^ath:\/\//, ""));
  }
  return d;
}

/** The reading-check divergences `accept` rulings mark known (§13.5.2): by scope address and the reading's revision. */
export function accepted(rulings: readonly Ruling[]): Set<string> {
  const out = new Set<string>();
  for (const r of rulings) {
    if (r.pred !== "accept" || typeof r.val.rev !== "string") continue;
    const m = /^ath:\/\/[0-9a-f]{64}\?(.+)$/.exec(String(r.val.on));
    if (m) out.add(`${hashOf(String(r.val.on))}|${m[1]}|${r.val.rev}`);
  }
  return out;
}
const hashOf = (on: string) => on.slice(6, 70);
