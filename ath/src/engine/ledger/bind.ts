// bind.ts — the binding state of an evidence entry (spec §9.2, derived never stored): bound when the anchor resolves
// to a scope, the binding yields a surface, and the quote is in it; held when the binding is null; flagged otherwise,
// with the reason.

import { type Artifact, loadArtifact } from "../corpus/derive.ts";
import { surfaceFor } from "../corpus/resolve.ts";
import type { Chain } from "../layer/config.ts";
import { parseAddress, scopeAt } from "../model/address.ts";
import { type EvidenceEntry, parseAnchor, parseBinding } from "../model/evidence.ts";
import { normalize, quoteIn } from "../norm/text.ts";
import type { Ontology } from "../ontology/load.ts";

export type BindState = "bound" | "held" | "flagged";

export interface BindResult {
  state: BindState;
  why?: string;
  /** The artifact the anchor names. */
  blake3: string;
  at: string;
  surface?: string;
  pass?: "normalized" | "squashed";
  /** The anchor names a scope smaller than the quote's actual holder? (tightness is advisory) */
  tight: boolean;
}

export class ArtifactCache {
  private readonly map = new Map<string, Artifact | null>();
  constructor(
    private readonly chain: Chain,
    private readonly o: Ontology,
  ) {}
  async get(blake3: string): Promise<Artifact | null> {
    if (!this.map.has(blake3)) {
      try {
        this.map.set(blake3, await loadArtifact(this.chain, this.o, blake3));
      } catch {
        this.map.set(blake3, null);
      }
    }
    return this.map.get(blake3) ?? null;
  }
}

/** Does the artifact have a scope at `at`: a listed scope, `whole`, or (tabular) a cell of a listed row? */
export function scopeExists(a: Artifact, at: string): boolean {
  const s = scopeAt(at);
  if (a.table.get(s)) return true;
  const m = parseAddress(s).members[0]!;
  if (m.kind === "row" && m.col !== undefined) return a.table.get(`row=${m.row}`) !== undefined;
  return false;
}

export async function bindEntry(cache: ArtifactCache, e: EvidenceEntry): Promise<BindResult> {
  let anchor: ReturnType<typeof parseAnchor>;
  try {
    anchor = parseAnchor(e.anchor);
  } catch (err) {
    return { state: "flagged", why: (err as Error).message, blake3: "", at: "", tight: false };
  }
  const base = { blake3: anchor.blake3, at: anchor.at, tight: true };
  const b = parseBinding(e.reading);
  if (b.kind === "invalid") return { ...base, state: "flagged", why: b.why };
  if (b.kind === "held") return { ...base, state: "held" };
  const a = await cache.get(anchor.blake3);
  if (!a) return { ...base, state: "flagged", why: "anchor names an artifact not in the chain" };
  if (!scopeExists(a, anchor.at)) return { ...base, state: "flagged", why: "anchor resolves to no scope" };
  const surface = surfaceFor(a, anchor.at, b, anchor.aspect);
  if (!surface) return { ...base, state: "flagged", why: `binding ${e.reading} yields no surface at ${anchor.at}` };
  const m = quoteIn(surface.text, e.quote, e.prefix, e.suffix);
  if (!m.found) return { ...base, state: "flagged", why: m.why, surface: surface.text.slice(0, 200) };
  // a stated value must sit inside its quote (D-D4)
  return { ...base, state: "bound", surface: surface.text.slice(0, 200), pass: m.pass };
}

/** D-D4: a `stated` entry supports a string value only if the value is in the quote (after normalisation). */
export function valueInQuote(value: unknown, e: EvidenceEntry): boolean {
  if (e.mode !== "stated") return true;
  if (typeof value !== "string") return true;
  const q = normalize(e.quote);
  const v = normalize(value);
  return q.includes(v) || v.includes(q) || quoteIn(e.quote, value).found;
}
