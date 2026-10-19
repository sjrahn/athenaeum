// tree.ts — walking a record's readings and its tree (spec §8.3, §8.4): the scope at an address, the reading at an
// address — in `readings` before the record is formed, in the scope that adopted it once it is.
import { ASPECTS, type Aspect, canonicalAt } from "../address/address.ts";
import { isField, type Reading, type RecordDoc, type Scope } from "./document.ts";

/** Every scope, depth first in reading order, with its parent and its position among its siblings. */
export function* scopesOf(
  scopes: readonly Scope[] | undefined,
  parent: Scope | null = null,
): Generator<{ scope: Scope; parent: Scope | null; index: number }> {
  for (const [index, scope] of (scopes ?? []).entries()) {
    yield { scope, parent, index };
    yield* scopesOf(scope.scopes, scope);
  }
}

export function scopeAt(r: RecordDoc, at: string): Scope | null {
  const want = canonicalAt(at);
  for (const { scope } of scopesOf(r.scopes)) if (canonicalAt(scope.at) === want) return scope;
  return null;
}

/** The reading at an address: its bodies by aspect, from `readings` or from the scope that adopted it. */
export function readingAt(r: RecordDoc, at: string): Reading | null {
  const want = canonicalAt(at);
  for (const [k, v] of Object.entries(r.readings ?? {})) if (canonicalAt(k) === want) return v;
  const s = scopeAt(r, want);
  if (!s) return null;
  const out: Reading = {};
  for (const a of ASPECTS) if (s[a] !== undefined) (out as Record<Aspect, unknown>)[a] = s[a];
  return Object.keys(out).length ? out : null;
}

export const fieldsOf = (s: Scope): Record<string, unknown> => Object.fromEntries(Object.entries(s).filter(([k]) => isField(k)));
