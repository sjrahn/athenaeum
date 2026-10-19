// classify.ts — an artifact's shape (spec §11.4, §11.5): the most specific shape whose `matches` lines all hold — the
// most conditions held, then the longer `refines` chain, then the name in code-point order — unless the record stores
// a choice. A condition: `mime`; `first_row` (a sheet's first physical row begins with the cells); `selector` (it
// selects something, in the format's language); `magic` (the bytes begin with it); `container` (a container holding
// the artifact has this shape); `constituent` (one of its own constituents' paths matches); `path` (its own path in
// some container matches); `origin` (an `origins` entry has, at the pointer, a matching value, or any).
import { byCodePoint } from "@ath/kit/canonical.ts";
import { delimiterFor, parseCsv } from "../formats/csv/parse.ts";
import { patternMatches, type SelectParse, selectParse, selects } from "../select/select.ts";
import { all, refinesChain } from "./load.ts";
import type { Vocabulary } from "./terms.ts";

type J = Record<string, unknown>;

export interface Probe {
  mime: string;
  intrinsics: J;
  origins: J[];
  /** (container, path) pairs that hold the artifact (§11.5.3). */
  within: { container: string; path: string }[];
  bytes(): Promise<Uint8Array | null>;
  /** The shape of a container holding it, for `container` conditions. */
  shapeOf(container: string): Promise<string | null>;
}

const pointerValue = (doc: unknown, ptr: string): unknown =>
  ptr
    .split("/")
    .slice(1)
    .map((s) => s.replace(/~1/g, "/").replace(/~0/g, "~"))
    .reduce<unknown>((v, k) => (v && typeof v === "object" ? (v as J)[k] : undefined), doc);

/** Whether one `matches` line holds, and how many conditions it has. */
async function holds(m: J, p: Probe, v: Vocabulary, parse: () => Promise<SelectParse | null>): Promise<boolean> {
  if (m.mime !== p.mime) return false;
  if (m.magic !== undefined) {
    const b = await p.bytes();
    if (!b || new TextDecoder("latin1").decode(b.subarray(0, String(m.magic).length)) !== String(m.magic)) return false;
  }
  if (m.first_row !== undefined) {
    const b = await p.bytes();
    if (!b) return false;
    const row = parseCsv(b, delimiterFor(p.mime)).rows[0]?.cells.map((c) => c.value) ?? [];
    if (!(m.first_row as string[]).every((c, i) => row[i] === c)) return false;
  }
  if (m.selector !== undefined) {
    const sp = await parse();
    if (!sp || !selects(sp, m.selector)) return false;
  }
  if (m.constituent !== undefined) {
    const cs = (p.intrinsics.constituents as { path: string }[] | undefined) ?? [];
    if (!cs.some((c) => patternMatches(String(m.constituent), c.path))) return false;
  }
  if (m.path !== undefined && !p.within.some((w) => patternMatches(String(m.path), w.path))) return false;
  if (m.container !== undefined) {
    let ok = false;
    for (const w of p.within) {
      const s = await p.shapeOf(w.container);
      if (s && refinesChain(v, "shapes", s).includes(String(m.container))) ok = true;
    }
    if (!ok) return false;
  }
  if (m.origin !== undefined) {
    const conds = Object.entries(m.origin as J);
    const ok = p.origins.some((o) =>
      conds.every(([ptr, pat]) => {
        const x = pointerValue(o, ptr);
        return pat === true ? x !== undefined : typeof x === "string" && patternMatches(String(pat), x);
      }),
    );
    if (!ok) return false;
  }
  return true;
}

export interface Classification {
  shape: string | null;
  /** How the shape was chosen. */
  by: "stored" | "matches" | "none";
  /** Every shape that matched, most specific first. */
  matched: string[];
}

export async function classify(v: Vocabulary, p: Probe, stored?: string): Promise<Classification> {
  let cached: Promise<SelectParse | null> | null = null;
  const parse = () =>
    (cached ??= (async () => {
      const b = await p.bytes();
      return b ? selectParse(b, p.mime, (p.intrinsics.constituents as { path: string }[] | undefined) ?? []) : null;
    })());
  const scored: { name: string; conditions: number; depth: number }[] = [];
  for (const [name, lines] of v.shapes) {
    const ms = all(lines, "matches") as J[];
    if (!ms.length) continue;
    let ok = true;
    for (const m of ms) if (!(await holds(m, p, v, parse))) ok = false;
    if (ok)
      scored.push({ name, conditions: ms.reduce((n, m) => n + Object.keys(m).length, 0), depth: refinesChain(v, "shapes", name).length });
  }
  scored.sort((a, b) => b.conditions - a.conditions || b.depth - a.depth || byCodePoint(a.name, b.name));
  const matched = scored.map((s) => s.name);
  if (stored) return { shape: stored, by: "stored", matched };
  return matched[0] ? { shape: matched[0], by: "matches", matched } : { shape: null, by: "none", matched };
}
