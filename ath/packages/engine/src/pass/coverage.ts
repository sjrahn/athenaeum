// coverage.ts — what each pass answers for (spec §8.5.1): a pass names what it covers in `over` — the address of
// each reading it wrote or re-wrote, `tree`, `shape`, `chrome` — and a pass with no `over` covers everything. A
// reading's pass is the highest-numbered pass whose `over` names its address or everything; the tree's, the shape's
// and the chrome's likewise. Containment is never coverage. A pass no region resolves to is superseded.
import { canonicalAt } from "../address/address.ts";
import { passOrder, type RecordDoc } from "../record/document.ts";
import { scopesOf } from "../record/tree.ts";

export type Kind = "tree" | "shape" | "chrome";

const covers = (over: readonly string[] | undefined, what: string): boolean =>
  over === undefined || over.some((o) => (o === "tree" || o === "shape" || o === "chrome" ? o === what : canonicalAt(o) === what));

/** The pass that answers for a reading at `at`, or for the tree, the shape or the chrome; null when none does. */
export function passOf(r: RecordDoc, what: string): string | null {
  const key = what === "tree" || what === "shape" || what === "chrome" ? what : canonicalAt(what);
  const ids = Object.keys(r.passes ?? {})
    .sort(passOrder)
    .reverse();
  return ids.find((id) => covers(r.passes![id]!.over, key)) ?? null;
}

/** Every region a record holds a judgment for: its readings' addresses (in `readings` or adopted by scopes), and the
 * kinds `tree`, `shape`, `chrome` where it has them. */
export function regions(r: RecordDoc): string[] {
  const out: string[] = [];
  for (const at of Object.keys(r.readings ?? {})) out.push(canonicalAt(at));
  if (r.scopes) {
    out.push("tree");
    for (const { scope } of scopesOf(r.scopes))
      if (scope.text !== undefined || scope.cells !== undefined || scope.tex !== undefined) out.push(canonicalAt(scope.at));
  }
  if (r.shape !== undefined) out.push("shape");
  if (r.chrome?.length) out.push("chrome");
  return out;
}

/** Each pass with what resolves to it; a pass nothing resolves to is superseded. */
export function answers(r: RecordDoc): Map<string, string[]> {
  const out = new Map<string, string[]>(Object.keys(r.passes ?? {}).map((id) => [id, []]));
  for (const g of regions(r)) {
    const p = passOf(r, g);
    if (p) out.get(p)!.push(g);
  }
  return out;
}

export const superseded = (r: RecordDoc): string[] => [...answers(r)].filter(([, gs]) => gs.length === 0).map(([id]) => id);

/** Regions no pass covers: a record that leaves one is refused at write (§6.2.3). */
export const uncovered = (r: RecordDoc): string[] => regions(r).filter((g) => passOf(r, g) === null);
