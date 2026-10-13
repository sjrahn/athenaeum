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

/** The blake3 of a container member by path, from the attests roster. */
export function memberOf(a: Artifact, path: string): string | null {
  const members = (a.attests.value as { members?: { path: string; blake3: string }[] }).members ?? [];
  return members.find((m) => m.path === path)?.blake3 ?? null;
}

/** Does the artifact have a scope at `at`: a listed scope, `whole`, or (tabular) a cell of a listed row? */
export function scopeExists(a: Artifact, at: string): boolean {
  const s = scopeAt(at);
  if (a.table.get(s)) return true;
  const m = parseAddress(s).members[0]!;
  // physical scopes are always addressable: a row the parse holds, a page the document has
  if (m.kind === "row")
    return a.csv !== undefined
      ? m.row < a.csv.rows.length && (m.col === undefined || m.col < (a.csv.rows[m.row]?.cells.length ?? 0))
      : a.table.get(`row=${m.row}`) !== undefined;
  if (m.kind === "page")
    return a.pdf !== undefined ? m.page >= 1 && m.page <= a.pdf.pages.length : a.table.get(`page=${m.page}`) !== undefined;
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
  let a = await cache.get(anchor.blake3);
  if (!a) return { ...base, state: "flagged", why: "anchor names an artifact not in the chain" };
  // a route through a container canonicalises to the member (spec §5.1): corpus://<zip>?path=p[;…] → the member's subject
  const route = parseAddress(anchor.at).members[0];
  if (route?.kind === "path") {
    const member = memberOf(a, route.path);
    if (!member) return { ...base, state: "flagged", why: `container has no member at path ${route.path}` };
    const m = await cache.get(member);
    if (!m) return { ...base, state: "flagged", why: `member ${member.slice(0, 12)}… is not a subject in the chain` };
    a = m;
    anchor = {
      ...anchor,
      blake3: member,
      at: parseAddress(anchor.at).members.length > 1 ? scopeAt(anchor.at.replace(/^path=[^;]*;/, "")) : "whole",
    };
    base.blake3 = member;
    base.at = anchor.at;
  }
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
