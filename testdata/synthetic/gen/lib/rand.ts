// rand.ts — a seeded generator and a word well for fabricated prose, so every twin reproduces byte-for-byte.
export function lcg(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
}
export const pick = <T>(r: () => number, a: readonly T[]): T => a[Math.floor(r() * a.length)]!;
export const int = (r: () => number, lo: number, hi: number) => lo + Math.floor(r() * (hi - lo + 1));

export const FIRST = ["Ada", "Bo", "Cyd", "Dee", "Eli", "Fay", "Gus", "Hal", "Ida", "Jo", "Kai", "Lou", "Max", "Nia", "Oz", "Pat", "Quin", "Rae", "Sol", "Tam"];
export const LAST = ["Abbott", "Birch", "Calder", "Dale", "Ennis", "Frost", "Grove", "Hale", "Irwin", "Judd", "Kerr", "Lowe", "Moss", "Nash", "Orme", "Penn", "Quill", "Rowe", "Stone", "Thorn"];

const WORDS = (
  "the harbour tide boat rope lantern gull quay morning fog engine chart wind sail anchor crew deck cabin " +
  "stone wall water light shadow door window kettle bread salt map letter clock bell road hill field " +
  "quiet slow bright cold warm old new small long late early green grey blue " +
  "walked waited watched turned opened closed carried found lost kept sent held heard said asked " +
  "and but then while because until after before through under over along across"
).split(" ");

/** A sentence of 6–18 words, capitalised, with a period. */
export function sentence(r: () => number): string {
  const n = int(r, 6, 18);
  const ws: string[] = [];
  for (let i = 0; i < n; i++) ws.push(pick(r, WORDS));
  const s = ws.join(" ");
  return `${s[0]!.toUpperCase()}${s.slice(1)}${r() < 0.1 ? "?" : "."}`;
}
export function paragraph(r: () => number, sentences = int(r, 2, 6)): string {
  const out: string[] = [];
  for (let i = 0; i < sentences; i++) out.push(sentence(r));
  return out.join(" ");
}
