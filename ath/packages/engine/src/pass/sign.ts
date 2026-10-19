// sign.ts — what signing a record pass writes (spec §13.2.2, §8.4, §13.3). A reading pass lays its readings over the
// stored ones by address and retires what it names; over a formed record it re-reads scopes at their addresses and
// mints or retires none — a change to the tree is a re-forming pass. A forming pass puts its tree in place of the
// stored one whole, adopts every reading — each at a scope's address, or retired — and attests `structure`; it covers
// the whole record. The pass is written with what it covers (`over`) and attests. The first signature over an asset
// with no record of its own creates one with its intrinsics.
import { canonicalAt, compareAt } from "../address/address.ts";
import type { Pass, Reading, RecordDoc, Scope } from "../record/document.ts";
import { scopesOf } from "../record/tree.ts";
import type { StagedPass } from "./staging.ts";

type J = Record<string, unknown>;
const ASPECTS = ["text", "cells", "tex"] as const;

const bodyOf = (x: Reading | Scope): Reading =>
  Object.fromEntries(ASPECTS.filter((a) => x[a] !== undefined).map((a) => [a, x[a]])) as Reading;

export interface Applied {
  record: RecordDoc;
  /** Refusals in the staging itself: the record checks run on the result after. */
  problems: string[];
}

export function applyStaged(prev: RecordDoc | null, intrinsics: J, s: StagedPass, verify: string, date: string): Applied {
  const problems: string[] = [];
  const r: RecordDoc = prev ? structuredClone(prev) : { intrinsics };
  const over: string[] = [];
  const retire = (s.retire ?? []).map(canonicalAt);
  const staged = Object.fromEntries(Object.entries(s.readings ?? {}).map(([at, b]) => [canonicalAt(at), b]));
  if (s.scopes) {
    // a forming pass: the tree whole, every reading adopted
    const tree = structuredClone(s.scopes);
    const byAt = new Map<string, Scope>();
    for (const { scope } of scopesOf(tree)) byAt.set(canonicalAt(scope.at), scope);
    for (const [at, b] of Object.entries(staged)) {
      const sc = byAt.get(at);
      if (!sc) problems.push(`the reading at ${at} lies in no scope of the tree: mint a scope for it or retire it`);
      else for (const a of ASPECTS) if (b[a] !== undefined) (sc as Record<string, unknown>)[a] = b[a];
    }
    const before = [
      ...Object.keys(prev?.readings ?? {}),
      ...[...scopesOf(prev?.scopes)].filter(({ scope }) => ASPECTS.some((a) => scope[a] !== undefined)).map(({ scope }) => scope.at),
    ].map(canonicalAt);
    for (const at of before)
      if (!byAt.has(at) && !retire.includes(at))
        problems.push(`the reading at ${at} is adopted by no scope of the new tree and not retired`);
    delete r.readings;
    r.scopes = tree;
    if (!(s.attests ?? []).includes("structure")) problems.push("a tree is never signed without attesting `structure`");
  } else if (prev?.scopes) {
    // a partial pass over a formed record: re-read scopes at their addresses, mint none, retire none
    if (retire.length) problems.push("a partial pass over a formed record retires nothing; a change to the tree is a re-forming pass");
    const byAt = new Map<string, Scope>();
    for (const { scope } of scopesOf(r.scopes)) byAt.set(canonicalAt(scope.at), scope);
    for (const [at, b] of Object.entries(staged)) {
      const sc = byAt.get(at);
      if (!sc) {
        problems.push(`${at} is no scope of the formed record; a change to the tree is a re-forming pass`);
        continue;
      }
      for (const a of ASPECTS) delete (sc as Record<string, unknown>)[a];
      Object.assign(sc, b);
      over.push(at);
    }
    if ((s.attests ?? []).includes("structure")) problems.push("only a forming pass attests `structure`");
  } else {
    // a reading pass: readings by address, a re-read replacing the entry; retirements removed
    const readings: Record<string, Reading> = Object.fromEntries(Object.entries(r.readings ?? {}).map(([at, b]) => [canonicalAt(at), b]));
    for (const at of retire) {
      if (!(at in readings)) problems.push(`there is no reading at ${at} to retire`);
      delete readings[at];
    }
    for (const [at, b] of Object.entries(staged)) {
      readings[at] = bodyOf(b);
      over.push(at);
    }
    if (Object.keys(readings).length)
      r.readings = Object.fromEntries(
        Object.keys(readings)
          .sort(compareAt)
          .map((at) => [at, readings[at]!]),
      );
    else delete r.readings;
    if ((s.attests ?? []).includes("structure")) problems.push("only a forming pass attests `structure`");
  }
  if (s.shape !== undefined) {
    r.shape = s.shape;
    if (!s.scopes) over.push("shape");
  }
  if (s.chrome !== undefined) {
    if (s.chrome.length) r.chrome = s.chrome;
    else delete r.chrome;
    if (!s.scopes) over.push("chrome");
  }
  if (!s.scopes && !over.length && !retire.length) problems.push("the pass stages nothing");
  const pass: Pass = { by: s.by, verify, vocab: s.vocab, date };
  // a forming pass covers the whole record; any other names exactly what it wrote
  if (!s.scopes)
    pass.over = [...new Set(over)].sort((a, b) =>
      a === "shape" || a === "chrome" ? 1 : b === "shape" || b === "chrome" ? -1 : compareAt(a, b),
    );
  if (s.attests?.length) pass.attests = [...new Set(s.attests)].sort() as Pass["attests"];
  if (s.note) pass.note = s.note;
  r.passes = { ...(r.passes ?? {}), [s.id]: pass };
  return { record: r, problems };
}
