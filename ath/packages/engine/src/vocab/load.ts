// load.ts — the vocabularies an instance reads (spec §11.1): every term file of the chain, an extension's terms
// together with its base's, each term's lines as one set (§4.4). Where each line came from is kept, so the check can
// refuse a write at an identity a base holds (§17.4).
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { parseLines } from "@ath/kit/canonical.ts";
import { AthError } from "@ath/kit/errors.ts";
import { chain, type Instance } from "../instance/instance.ts";
import { DIR, emptyVocabulary, termIdentity, VOCABS, type Vocab, type Vocabulary } from "./terms.ts";

export interface LoadedVocabulary {
  vocab: Vocabulary;
  /** Per vocabulary and term, the instance (by name) that holds each line's identity. */
  holders: Record<Vocab, Map<string, Map<string, string>>>;
}

export const termFile = (i: Instance, v: Vocab, name: string) => join(i.root, DIR[v], `${name}.jsonl`);

export function loadVocabulary(inst: Instance): LoadedVocabulary {
  const vocab = emptyVocabulary();
  const holders = { forms: new Map(), shapes: new Map(), kinds: new Map(), properties: new Map() } as LoadedVocabulary["holders"];
  for (const x of chain(inst).reverse()) {
    for (const v of VOCABS) {
      const dir = join(x.root, DIR[v]);
      if (!existsSync(dir)) continue;
      for (const f of readdirSync(dir).sort()) {
        if (!f.endsWith(".jsonl")) continue;
        const name = f.slice(0, -6);
        let lines: Record<string, unknown>[];
        try {
          lines = parseLines(readFileSync(join(dir, f), "utf8"), join(DIR[v], f));
        } catch (e) {
          throw new AthError("CONFIG", (e as Error).message);
        }
        vocab[v].set(name, [...(vocab[v].get(name) ?? []), ...lines]);
        const h = holders[v].get(name) ?? new Map<string, string>();
        for (const l of lines) if (!h.has(termIdentity(l))) h.set(termIdentity(l), x.config.name);
        holders[v].set(name, h);
      }
    }
  }
  return { vocab, holders };
}

/** A term's single value for a predicate, or undefined. */
export const one = (lines: readonly Record<string, unknown>[] | undefined, pred: string): unknown =>
  lines?.find((l) => l.pred === pred)?.val;
export const all = (lines: readonly Record<string, unknown>[] | undefined, pred: string): unknown[] =>
  (lines ?? []).filter((l) => l.pred === pred).map((l) => l.val);

/** A term's `refines` chain, nearest first, the term itself included; stops at a cycle. */
export function refinesChain(v: Vocabulary, vocab: Vocab, name: string): string[] {
  const out: string[] = [];
  for (let n: string | undefined = name; n && !out.includes(n); n = one(v[vocab].get(n), "refines") as string | undefined) out.push(n);
  return out;
}
