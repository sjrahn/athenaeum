// binding.ts — evidence and its binding (spec §14.3, §14.4). An entry's pass binds it: on a rendered artifact to the
// revision of the reading at the anchor's scope and aspect (`b3:`); on a structured artifact or a testimony to the
// surface op that yields its quote (`derived:<op>`); to a scope's field (`field:`) or an intrinsic value
// (`intrinsics:`); with no quote, to what the region shows (`observed`). Verify derives the state: bound while the
// anchor resolves, the binding yields a body and the quote lies in it under the normaliser; held when the binding is
// null, the revision moved, or it relies on something distrusted — a re-bind owed where the quote still lies in the
// body at its anchor; flagged otherwise, with the reason.
import { short } from "@ath/kit/hash.ts";
import { normalize, quoteIn } from "../norm/text.ts";
import type { Reading } from "../record/document.ts";
import type { EvidenceEntry } from "./entity.ts";

type J = Record<string, unknown>;

/** What an anchor reaches, as the verbs resolve it. */
export interface Target {
  /** The artifact or testimony, a route to an asset canonicalised to the asset. */
  hash: string;
  /** The scope's canonical address, without its aspect. */
  at: string;
  aspect?: "text" | "cells" | "tex";
  /** A cell of a row (`&col=M`). */
  col?: number;
  kind: "rendered" | "structured" | "testimony" | "unregistered";
  /** On a rendered artifact: the reading at the address, in `readings` or adopted by the scope there. */
  reading: Reading | null;
  /** The fields of the scope at the address, stored or derived. */
  fields: J | null;
  intrinsics: J;
  /** The op a structured scope's surface comes from: the shape's `surface` line, else the format's own. */
  surfaceOp: string | null;
  /** The surface an op yields at the scope: of the node the scope reads where its shape names one, else its span. */
  surface(op: string): Promise<string | null>;
}

export type Locate = (anchor: string) => Promise<Target | { problem: string }>;

/** The body a reading gives under the anchor's aspect (a cell where `col` names one), or null. */
function readingBody(t: Target): { body: string; rev: unknown } | null {
  const r = t.reading;
  if (!r) return null;
  const aspect = t.aspect ?? (["text", "cells", "tex"] as const).find((a) => r[a] !== undefined);
  if (!aspect || r[aspect] === undefined) return null;
  const raw = r[aspect]!;
  if (aspect === "cells") {
    const cells = raw as string[];
    if (t.col !== undefined) return cells[t.col] === undefined ? null : { body: cells[t.col]!, rev: cells };
    return { body: cells.join("\t"), rev: cells };
  }
  return { body: raw as string, rev: raw };
}

const textOf = (v: unknown): string | null =>
  v === undefined || v === null
    ? null
    : typeof v === "string"
      ? v
      : typeof v === "number" || typeof v === "boolean"
        ? String(v)
        : JSON.stringify(v);

/** Bind an entry as its pass signs it; a problem refuses the signature (the citation check, §17.2). */
export async function bindEntry(e: EvidenceEntry, t: Target): Promise<{ entry: EvidenceEntry } | { problem: string }> {
  const given = e.binding;
  if (given === "observed") {
    if (e.quote !== undefined) return { problem: "an observed entry carries no quote" };
    if (e.mode !== "inferred" || !e.reason) return { problem: "an observed entry is `inferred` with a `reason`" };
    return { entry: { ...e, binding: "observed" } };
  }
  if (e.quote === undefined) return { problem: "an entry carries a quote, unless it is observed" };
  if (e.mode !== "stated" && !e.reason) return { problem: `a ${e.mode} entry carries a reason` };
  if (/…|\.\.\./.test(e.quote) && !/…|\.\.\./.test(textOf(t.reading?.text) ?? ""))
    return { problem: "an elided quote is refused: quote verbatim, with prefix and suffix to extend it" };
  if (given?.startsWith("field:")) {
    const v = textOf(t.fields?.[given.slice(6)]);
    return v !== null && quoteIn(v, e.quote, e.prefix, e.suffix)
      ? { entry: e }
      : { problem: `the quote is not in the field ${given.slice(6)} at ${t.at}` };
  }
  if (given?.startsWith("intrinsics:")) {
    const v = textOf(t.intrinsics[given.slice(11)]);
    return v !== null && quoteIn(v, e.quote, e.prefix, e.suffix)
      ? { entry: e }
      : { problem: `the quote is not in intrinsics ${given.slice(11)}` };
  }
  if (t.kind === "rendered") {
    const b = readingBody(t);
    if (!b) return { problem: `there is no reading at ${t.at}${t.aspect ? ` under ${t.aspect}` : ""}: read it first` };
    if (!quoteIn(b.body, e.quote, e.prefix, e.suffix)) return { problem: `the quote is not in the reading at ${t.at}` };
    return { entry: { ...e, binding: await short(b.rev) } };
  }
  if (t.kind === "structured" || t.kind === "testimony") {
    const op = given?.startsWith("derived:") ? given.slice(8) : t.surfaceOp;
    if (!op) return { problem: `${t.hash} gives no surface at ${t.at}` };
    const s = await t.surface(op);
    if (s === null) return { problem: `${op} yields no surface at ${t.at}` };
    if (!quoteIn(t.col !== undefined ? (s.split("\t")[t.col] ?? "") : s, e.quote, e.prefix, e.suffix))
      return { problem: `the quote is not in the surface ${op} yields at ${t.at}` };
    return { entry: { ...e, binding: `derived:${op}` } };
  }
  return { problem: `${t.hash} is of a format with no reading and no surface: cite a region with \`observed\`` };
}

export interface EntryState {
  state: "bound" | "held" | "flagged";
  reason?: string;
  /** The quote still lies in the body at its anchor: a later pass's own line re-binds it (§14.4.2). */
  rebind?: boolean;
  /** The artifact the entry is anchored in, for standing and sources. */
  artifact?: string;
}

/** The state of an entry now (§14.4.2). `distrusted` says whether it relies on something a ruling distrusts. */
export async function entryState(e: EvidenceEntry, located: Target | { problem: string }, distrusted: boolean): Promise<EntryState> {
  if ("problem" in located) return { state: "flagged", reason: located.problem };
  const t = located;
  const artifact = t.hash;
  const quoteStill = async (): Promise<boolean> => {
    if (e.quote === undefined) return false;
    if (t.kind === "rendered") {
      const b = readingBody(t);
      return !!b && quoteIn(b.body, e.quote, e.prefix, e.suffix);
    }
    return false;
  };
  if (distrusted) return { state: "held", reason: "it relies on what a ruling distrusts", artifact };
  if (e.binding === null) return { state: "held", reason: "unbound", rebind: await quoteStill(), artifact };
  if (e.binding === "observed") return { state: "bound", artifact };
  if (e.binding.startsWith("b3:")) {
    // a revision: the reading as it was when the pass bound it
    if (t.kind !== "rendered")
      return { state: "flagged", reason: "a revision binds a reading, and this is no rendered artifact", artifact };
    const b = readingBody(t);
    if (!b) return { state: "held", reason: `there is no reading at ${t.at}: a reading is owed`, artifact };
    if ((await short(b.rev)) !== e.binding)
      return { state: "held", reason: `the reading at ${t.at} has moved from the revision it bound`, rebind: await quoteStill(), artifact };
    return quoteIn(b.body, e.quote ?? "", e.prefix, e.suffix)
      ? { state: "bound", artifact }
      : { state: "flagged", reason: "the quote is not in the reading it bound", artifact };
  }
  const r = await bindEntry(e, t);
  return "problem" in r ? { state: "flagged", reason: r.problem, artifact } : { state: "bound", artifact };
}

/** Whether a stated entry's quote holds the claim's value (§14.3.3): a string within the quote after normalisation. */
export function statedSupports(val: unknown, qualAs: unknown, e: EvidenceEntry): boolean {
  if (e.mode !== "stated" || e.quote === undefined) return true;
  const v = typeof val === "string" && val.startsWith("ath://") ? qualAs : val;
  if (typeof v !== "string") return true;
  return normalize(e.quote).includes(normalize(v));
}
