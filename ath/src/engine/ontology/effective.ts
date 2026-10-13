// effective.ts — the effective rules of a scope (spec §7.1): the union over its terms' refines chains, most specific
// term first, plus its ancestors' conventions down the `in` chain. Computed, never chosen.
import { FieldDecl, type SelectDecl, type ShapeDecl } from "../model/term.ts";
import { refinesChain } from "./chain.ts";
import { linesOf, type Ontology, type TermLine } from "./load.ts";

export interface EffectiveRules {
  terms: string[];
  /** Every line that applies, most specific first. */
  lines: TermLine[];
  reads: "text" | "cells" | "tex" | "none" | null;
  fields: FieldDecl[];
  expects: string[];
  owes: string[];
  conventions: string[];
  renders: Record<string, unknown> | null;
  selects: SelectDecl[];
  shapes: ShapeDecl[];
  axes: string[] | null;
  physical: string | null;
  tree: string | null;
  derivation: string | null;
  functional: string[];
}

/** First value of `predicate` along the chain (most specific wins). */
export function resolveAlong<T = unknown>(o: Ontology, chain: readonly string[], predicate: string): T | undefined {
  for (const t of chain) {
    const l = linesOf(o, t, predicate);
    if (l.length) return l[0]!.value as T;
  }
  return undefined;
}

/** Every value of `predicate` along the chain, most specific first, deduplicated by name where values carry one. */
export function collectAlong<T = unknown>(o: Ontology, chain: readonly string[], predicate: string): T[] {
  const out: T[] = [];
  const names = new Set<string>();
  for (const t of chain) {
    for (const l of linesOf(o, t, predicate)) {
      const v = l.value as T;
      const n =
        typeof v === "object" && v !== null && "name" in (v as object) ? String((v as unknown as { name: unknown }).name) : undefined;
      if (n !== undefined) {
        if (names.has(n)) continue;
        names.add(n);
      }
      out.push(v);
    }
  }
  return out;
}

export function effectiveRules(o: Ontology, terms: readonly string[], ancestorTerms: readonly string[][] = []): EffectiveRules {
  const chains = terms.map((t) => refinesChain(o, t));
  const merged: string[] = [];
  for (const c of chains) for (const t of c) if (!merged.includes(t)) merged.push(t);
  const lines: TermLine[] = merged.flatMap((t) => linesOf(o, t));
  const conventions = new Set<string>();
  for (const t of merged) for (const l of linesOf(o, t, "convention")) conventions.add(String(l.value));
  for (const anc of ancestorTerms)
    for (const t of anc) for (const a of refinesChain(o, t)) for (const l of linesOf(o, a, "convention")) conventions.add(String(l.value));
  const fields = collectAlong<unknown>(o, merged, "field")
    .map((v) => FieldDecl.safeParse(v))
    .flatMap((r) => (r.success ? [r.data] : []));
  const flat = (p: string): string[] => [
    ...new Set(merged.flatMap((t) => linesOf(o, t, p).flatMap((l) => (Array.isArray(l.value) ? l.value.map(String) : [String(l.value)])))),
  ];
  return {
    terms: [...terms],
    lines,
    reads: (resolveAlong<string>(o, merged, "reads") as EffectiveRules["reads"]) ?? null,
    fields,
    expects: flat("expects"),
    owes: flat("owes"),
    conventions: [...conventions],
    renders: resolveAlong<Record<string, unknown>>(o, merged, "renders") ?? null,
    selects: merged.flatMap((t) => linesOf(o, t, "select").map((l) => l.value as SelectDecl)),
    shapes: merged.flatMap((t) => linesOf(o, t, "shape").map((l) => l.value as ShapeDecl)),
    axes: resolveAlong<string[]>(o, merged, "axes") ?? null,
    physical: resolveAlong<string>(o, merged, "physical") ?? null,
    tree: resolveAlong<string>(o, merged, "tree") ?? null,
    derivation: resolveAlong<string>(o, merged, "derivation") ?? null,
    functional: flat("functional"),
  };
}
