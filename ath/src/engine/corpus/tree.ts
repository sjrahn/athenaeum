// tree.ts — the scope table of one artifact: every scope (stored or derived) with its terms, fields, placement and
// reading; the ord walk from `whole`; closures. Lint, export, harvest and verify all read it.
import type { JsonObject } from "../../lib/jsonl.ts";
import { canonicalAt, contains, isPageAt, parseAddress } from "../model/address.ts";

export interface Reading {
  aspect: "text" | "cells" | "tex";
  body: unknown;
  /** A stored revision, or `derived:<op>@<v>` when the parse is the surface. */
  rev: string;
  stored: boolean;
}

export interface Scope {
  at: string;
  terms: string[];
  fields: Record<string, unknown>;
  parent: string | null;
  ord: number | null;
  /** True when no stored line sits at this scope. */
  derived: boolean;
  /** Where the derivation came from (`xenforo-thread.select h1.p-title-value`), per term. */
  derivedBy: Record<string, string>;
  stored: JsonObject[];
  readings: Reading[];
}

export class ScopeTable {
  readonly scopes = new Map<string, Scope>();

  get(at: string): Scope | undefined {
    return this.scopes.get(canonicalAt(at));
  }

  ensure(at: string): Scope {
    const key = canonicalAt(at);
    let s = this.scopes.get(key);
    if (!s) {
      s = { at: key, terms: [], fields: {}, parent: null, ord: null, derived: true, derivedBy: {}, stored: [], readings: [] };
      this.scopes.set(key, s);
    }
    return s;
  }

  addTerm(at: string, term: string, fields: Record<string, unknown> = {}, derivedBy?: string): Scope {
    const s = this.ensure(at);
    if (!s.terms.includes(term)) s.terms.push(term);
    Object.assign(s.fields, fields);
    if (derivedBy) s.derivedBy[term] = derivedBy;
    return s;
  }

  place(at: string, parent: string, ord: number): void {
    const s = this.ensure(at);
    s.parent = canonicalAt(parent);
    s.ord = ord;
  }

  children(at: string): Scope[] {
    const key = canonicalAt(at);
    return [...this.scopes.values()].filter((s) => s.parent === key).sort((a, b) => (a.ord ?? 0) - (b.ord ?? 0));
  }

  /** Depth-first in ord from `whole`. */
  walk(from = "whole"): Scope[] {
    const out: Scope[] = [];
    const seen = new Set<string>();
    const visit = (at: string) => {
      if (seen.has(at)) return;
      seen.add(at);
      const s = this.scopes.get(at);
      if (s) out.push(s);
      for (const c of this.children(at)) visit(c.at);
    };
    visit(canonicalAt(from));
    return out;
  }

  /** Scopes nobody reaches from `whole`: pages and columns (axis scopes) are expected here; anything else is a G2 finding. */
  unreachable(): Scope[] {
    const reached = new Set(this.walk().map((s) => s.at));
    return [...this.scopes.values()].filter((s) => !reached.has(s.at));
  }

  /** The nearest scope (smallest span) that contains `at`, excluding `at` itself; null when only `whole` does. */
  enclosing(at: string): Scope | null {
    const key = canonicalAt(at);
    let best: Scope | null = null;
    for (const s of this.scopes.values()) {
      if (s.at === key || s.at === "whole") continue;
      if (!contains(s.at, key)) continue;
      if (!best || contains(best.at, s.at)) best = s;
    }
    return best ?? this.scopes.get("whole") ?? null;
  }

  /** Scopes inside `at` (contained, excluding itself), in file order. */
  within(at: string): Scope[] {
    const key = canonicalAt(at);
    if (key === "whole") return [...this.scopes.values()].filter((s) => s.at !== "whole");
    return [...this.scopes.values()].filter((s) => s.at !== key && contains(key, s.at));
  }

  /** The nearest descendant (by walk order, then containment) manifesting `term`, or the scope itself. */
  find(term: string, under = "whole"): Scope | null {
    const root = this.get(under);
    if (root?.terms.includes(term)) return root;
    for (const s of this.walk(under)) if (s.at !== canonicalAt(under) && s.terms.includes(term)) return s;
    for (const s of this.within(under)) if (s.terms.includes(term)) return s;
    return null;
  }

  findAll(term: string, under = "whole"): Scope[] {
    const walked = this.walk(under).filter((s) => s.terms.includes(term));
    if (walked.length) return walked;
    return this.within(under).filter((s) => s.terms.includes(term));
  }

  isAxis(s: Scope): boolean {
    if (isPageAt(s.at)) return true;
    const m = parseAddress(s.at).members[0]!;
    return m.kind === "col" && !s.parent;
  }

  get size(): number {
    return this.scopes.size;
  }
}
