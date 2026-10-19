// entity-pass.ts — a pass over an entity (spec §13.1, §14): staged claim and `is` lines; signed by a verifier who is
// not the author, which binds every evidence entry (§14.4.1), runs the citation check over the lines it signs — every
// anchor resolves, every quote is in its bound body or surface, a stated entry holds the value (§14.3.3) — and the
// sorts — `is` names a kind, a claim's `pred` is a property or a fixed predicate and its `val` fits the range — and
// writes the `pass` line and the lines under it. An extension's claim lines add to its base's under its own passes.
import { existsSync, readFileSync } from "node:fs";
import type { Locate } from "@ath/engine/graph/binding.ts";
import { bindEntry, statedSupports } from "@ath/engine/graph/binding.ts";
import { entityView, isEntityName, type Line, ownEntity, writeEntity } from "@ath/engine/graph/entity.ts";
import { entityPath, type Instance } from "@ath/engine/instance/instance.ts";
import { nextId, openPasses } from "@ath/engine/pass/staging.ts";
import { one, refinesChain } from "@ath/engine/vocab/load.ts";
import type { Vocabulary } from "@ath/engine/vocab/terms.ts";
import { blake3Hex } from "@ath/kit/hash.ts";

type J = Record<string, unknown>;

export const FIXED = new Set(["is", "same-as", "manifests", "supersedes", "challenges", "presence"]);
const TYPE: Record<string, (v: unknown) => boolean> = {
  string: (v) => typeof v === "string",
  uri: (v) => typeof v === "string" && /^[a-z][a-z0-9+.-]*:/i.test(v),
  int: (v) => (typeof v === "number" && Number.isInteger(v)) || (typeof v === "string" && /^-?\d+$/.test(v)),
  decimal: (v) => typeof v === "number" || (typeof v === "string" && /^-?\d+(\.\d+)?$/.test(v)),
  amount: (v) => typeof v === "string" && v.trim() !== "",
  date: (v) => typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v),
  datetime: (v) => typeof v === "string" && !Number.isNaN(Date.parse(v)),
  bool: (v) => typeof v === "boolean",
};

export const entityFileHash = async (inst: Instance, name: string): Promise<string | null> => {
  const p = entityPath(inst, name);
  return existsSync(p) ? blake3Hex(new Uint8Array(readFileSync(p))) : null;
};

export function nextEntityPass(inst: Instance, state: string, name: string): string {
  const signed = (ownEntity(inst, name) ?? []).filter((l) => l.pred === "pass").map((l) => String((l.val as J).id));
  return nextId(signed, openPasses(state, name));
}

/** The sorts of one line (§17.2): what `is` names, what a claim's predicate and value are. */
export function sortsProblems(l: Line, v: Vocabulary, held: (h: string) => boolean, kindsOf: (e: string) => string[] | null): string[] {
  const out: string[] = [];
  if (l.pred === "is") {
    if (typeof l.val !== "string" || !v.kinds.has(l.val)) out.push(`is: ${JSON.stringify(l.val)} is not a kind`);
    return out;
  }
  const entityRef = (x: unknown) => typeof x === "string" && /^ath:\/\/[a-z0-9][a-z0-9-]*$/.test(x) && isEntityName(x.slice(6));
  const artifactRef = (x: unknown) => typeof x === "string" && /^ath:\/\/[0-9a-f]{64}$/.test(x);
  if (FIXED.has(l.pred)) {
    if ((l.pred === "same-as" || l.pred === "supersedes") && !entityRef(l.val)) out.push(`${l.pred} names an entity: ath://<name>`);
    if (l.pred === "manifests" && !(artifactRef(l.val) && held((l.val as string).slice(6))))
      out.push("manifests names an artifact the chain holds: ath://<blake3>");
    if (l.pred === "challenges" && !(l.val && typeof l.val === "object" && typeof (l.val as J).pred === "string" && "val" in (l.val as J)))
      out.push("challenges names a claim: {pred, val, qual?, of?}");
    if (l.pred === "presence" && l.val !== "none") out.push("presence is none");
    return out;
  }
  const p = v.properties.get(l.pred);
  if (!p) return [`${l.pred} is not a property`];
  const range = String(one(p, "range"));
  if (range === "artifact") {
    if (!(artifactRef(l.val) && held((l.val as string).slice(6)))) out.push(`${l.pred} takes an artifact the chain holds: ath://<blake3>`);
  } else if (TYPE[range]) {
    if (!TYPE[range]!(l.val)) out.push(`${l.pred} takes a ${range}; ${JSON.stringify(l.val)} is not one`);
  } else if (v.kinds.has(range)) {
    if (!entityRef(l.val)) out.push(`${l.pred} takes an entity of kind ${range}: ath://<name>`);
    else {
      const ks = kindsOf((l.val as string).slice(6));
      if (ks && !ks.some((k) => refinesChain(v, "kinds", k).includes(range))) out.push(`${l.val} is not a ${range}`);
    }
  }
  return out;
}

/** Bind and check the staged lines; returns the lines to write under the pass, or the problems refusing it. */
export async function signEntityLines(
  staged: readonly J[],
  pass: string,
  locate: Locate,
  v: Vocabulary,
  held: (h: string) => boolean,
  kindsOf: (e: string) => string[] | null,
): Promise<{ lines: Line[]; problems: string[] }> {
  const lines: Line[] = [];
  const problems: string[] = [];
  for (const [i, raw] of staged.entries()) {
    const where = `line ${i + 1} (${String(raw.pred)})`;
    if (typeof raw.pred !== "string" || !("val" in raw)) {
      problems.push(`${where}: a line is {pred, val, qual?, ev?}`);
      continue;
    }
    for (const k of Object.keys(raw))
      if (!["pred", "val", "qual", "ev"].includes(k))
        problems.push(`${where}: \`${k}\` is not a key of a claim line; the pass gives its authorship`);
    const l: Line = { pred: raw.pred, val: raw.val, ...(raw.qual ? { qual: raw.qual as J } : {}) };
    for (const p of sortsProblems(l, v, held, kindsOf)) problems.push(`${where}: ${p}`);
    if (raw.pred !== "is") {
      const ev: Line["ev"] = [];
      for (const [k, e] of ((raw.ev as J[] | undefined) ?? []).entries()) {
        const entry = { binding: null, ...e } as NonNullable<Line["ev"]>[number];
        const loc = await locate(String(entry.anchor));
        if ("problem" in loc) {
          problems.push(`${where} ev ${k + 1}: ${loc.problem}`);
          continue;
        }
        const b = await bindEntry(entry, loc);
        if ("problem" in b) problems.push(`${where} ev ${k + 1}: ${b.problem}`);
        else {
          if (!statedSupports(l.val, l.qual?.as, b.entry))
            problems.push(
              `${where} ev ${k + 1}: a stated entry's quote holds the value; this one does not, so the entry is inferred, with a reason`,
            );
          ev.push(b.entry);
        }
      }
      l.ev = ev;
    }
    l.pass = pass;
    lines.push(l);
  }
  return { lines, problems };
}

/** The kinds an entity of the chain is, or null when there is no such entity. */
export function kindsOfEntity(inst: Instance) {
  return (name: string): string[] | null => {
    const e = entityView(inst, name);
    return e ? e.filter((h) => h.line.pred === "is").map((h) => String(h.line.val)) : null;
  };
}

export { writeEntity };
