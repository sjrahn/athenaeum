// entity.ts — an entity's file (spec §14.1, §6): `graph/entities/<shard>/<name>.jsonl`, its passes as `pass` lines (the
// one line with no authorship), its kinds as `is` lines, and one line per claim per pass that evidenced it. A line's
// identity: a claim (pred, val, qual, pass); `is` (pred, val); a `pass` line (pred, id). A file is sorted by identity,
// each line canonical. Across a chain an entity is the union of its files; a pass id names a pass in the file of the
// instance that holds it, so an extension's p2 and its base's p2 are two passes.
import { existsSync, readFileSync } from "node:fs";
import { relative } from "node:path";
import { byCodePoint, canonicalJson, canonicalLine, type JsonObject, parseLines } from "@ath/kit/canonical.ts";
import { AthError } from "@ath/kit/errors.ts";
import { writeAtomic } from "@ath/kit/fs.ts";
import { chain, entityPath, type Instance } from "../instance/instance.ts";

export interface EvidenceEntry {
  anchor: string;
  quote?: string;
  prefix?: string;
  suffix?: string;
  mode: "stated" | "inferred" | "reported";
  reason?: string;
  binding: string | null;
}

export interface Line extends JsonObject {
  pred: string;
  val: unknown;
  qual?: JsonObject;
  ev?: EvidenceEntry[];
  pass?: string;
  by?: string;
}

/** A line as the chain holds it: with the instance whose file holds it. */
export interface Held {
  line: Line;
  instance: string;
}

export const NAME = /^[a-z0-9][a-z0-9-]*$/;
export const isEntityName = (n: string) => NAME.test(n) && !/^[0-9a-f]+$/.test(n);

/** A line's identity (§6.3.1). */
export function lineIdentity(l: Line): string {
  if (l.pred === "pass") return `pass\u0000${(l.val as JsonObject).id}`;
  if (l.pred === "is") return `is\u0000${canonicalJson(l.val)}`;
  return `claim\u0000${l.pred}\u0000${canonicalJson(l.val)}\u0000${canonicalJson(l.qual ?? null)}\u0000${l.pass ?? ""}`;
}

/** The claim a line is a line of: (pred, val, qual), its pass aside. */
export const claimKey = (l: Line): string => `${l.pred}\u0000${canonicalJson(l.val)}\u0000${canonicalJson(l.qual ?? null)}`;

export function sortLines(lines: readonly Line[]): Line[] {
  const by = new Map<string, Line>();
  for (const l of lines) by.set(lineIdentity(l), l);
  return [...by.entries()].sort(([a], [b]) => byCodePoint(a, b)).map(([, l]) => l);
}

export const serializeEntity = (lines: readonly Line[]): string =>
  sortLines(lines)
    .map((l) => `${canonicalLine(l)}\n`)
    .join("");

export function ownEntity(i: Instance, name: string): Line[] | null {
  const p = entityPath(i, name);
  if (!existsSync(p)) return null;
  try {
    return parseLines(readFileSync(p, "utf8"), relative(i.root, p)) as Line[];
  } catch (e) {
    throw new AthError("CONFLICT", (e as Error).message);
  }
}

/** An entity across the chain: every instance's lines, the deepest first. */
export function entityView(i: Instance, name: string): Held[] | null {
  const out: Held[] = [];
  for (const x of chain(i).reverse()) for (const line of ownEntity(x, name) ?? []) out.push({ line, instance: x.config.name });
  return out.length ? out : null;
}

export function writeEntity(i: Instance, name: string, lines: readonly Line[]): string {
  if (i.readonly) throw new AthError("CONFLICT", `${i.config.name} is a base and is read-only here`);
  const p = entityPath(i, name);
  writeAtomic(p, serializeEntity(lines));
  return relative(i.root, p);
}

/** Whether a line's authorship is as §6.2.3 requires: exactly one of `by` and `pass`, a `pass` that resolves in its
 * file — the `pass` line itself carrying neither. */
export function authorshipProblem(l: Line, passes: ReadonlySet<string>): string | null {
  if (l.pred === "pass") return l.by !== undefined || l.pass !== undefined ? "a pass line carries no authorship" : null;
  if ((l.by === undefined) === (l.pass === undefined)) return "a line carries exactly one of `by` and `pass`";
  if (l.pass !== undefined && !passes.has(l.pass)) return `its pass ${l.pass} is no pass of this file`;
  return null;
}
