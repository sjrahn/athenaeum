// match.ts — classification (spec §7.2 `matches`): the most specific term whose `matches` lines all hold for the
// artifact — its mime, a header fingerprint (CSV), a root selector (HTML), a magic, the root term of its container, a
// path on its own roster. A
// stored `manifests` at `whole`
// overrides the derived answer.
import { MatchesDecl } from "../model/term.ts";
import { refinesChain } from "./chain.ts";
import { linesOf, type Ontology } from "./load.ts";

export interface Probe {
  mime: string;
  /** The CSV header row's cells, when there is one. */
  header?: string[];
  /** Whether a CSS selector matches the document (HTML). */
  selectorMatches?: (selector: string) => boolean;
  /** The first bytes, for magic. */
  head?: Uint8Array;
  /** The root term of the container this artifact is a member of (D-epub: a chapter is told by its package). */
  container?: string | null;
  /** The paths on the artifact's own roster (D-roster: a bundle is told by its layout). */
  members?: readonly string[];
  /** The artifact's own path inside its container (D-roster: a member is told by its name). */
  path?: string | null;
}

// A member or path probe: a prefix, or a glob where `*` stands for any run of characters ("*.metadata.json",
// "*-diagnostics-*" followed by "/smart/"); a glob matches from the start, so `*` leads when the start is free.
const pathTest = (want: string) => {
  if (!want.includes("*")) return (m: string) => m.startsWith(want);
  const special = new Set([".", "+", "?", "^", "$", "(", ")", "|", "[", "]", "{", "}", "\\"]);
  const quote = (p: string) => [...p].map((c) => (special.has(c) ? `\\${c}` : c)).join("");
  const re = new RegExp(`^${want.split("*").map(quote).join(".*")}`);
  return (m: string) => re.test(m);
};

export interface Match {
  term: string;
  /** How many conditions held: the specificity. */
  conditions: number;
}

function holds(decl: MatchesDecl, p: Probe): number | null {
  let n = 0;
  if (decl.mime !== undefined) {
    if (decl.mime !== p.mime) return null;
    n++;
  }
  if (decl.header !== undefined) {
    if (!p.header) return null;
    const have = p.header.slice(0, decl.header.length);
    if (have.length !== decl.header.length || decl.header.some((h, i) => h !== have[i])) return null;
    n++;
  }
  if (decl.selector !== undefined) {
    if (!p.selectorMatches?.(decl.selector)) return null;
    n++;
  }
  if (decl.container !== undefined) {
    if (!p.container || decl.container !== p.container) return null;
    n++;
  }
  if (decl.member !== undefined) {
    if (!p.members?.some(pathTest(decl.member))) return null;
    n++;
  }
  if (decl.path !== undefined) {
    if (!p.path || !pathTest(decl.path)(p.path)) return null;
    n++;
  }
  if (decl.magic !== undefined) {
    if (!p.head) return null;
    const want = new TextEncoder().encode(decl.magic);
    if (p.head.length < want.length || want.some((b, i) => p.head![i] !== b)) return null;
    n++;
  }
  return n;
}

/** Every matching term with its specificity, best first (more conditions, then the longer refines chain). */
export function matches(o: Ontology, p: Probe): Match[] {
  const out: Match[] = [];
  for (const term of o.terms.keys()) {
    const decls = linesOf(o, term, "matches")
      .map((l) => MatchesDecl.safeParse(l.value))
      .flatMap((r) => (r.success ? [r.data] : []));
    if (!decls.length) continue;
    let total = 0;
    let ok = true;
    for (const d of decls) {
      const n = holds(d, p);
      if (n === null) {
        ok = false;
        break;
      }
      total += n;
    }
    if (ok) out.push({ term, conditions: total });
  }
  return out.sort(
    (a, b) =>
      b.conditions - a.conditions || refinesChain(o, b.term).length - refinesChain(o, a.term).length || a.term.localeCompare(b.term),
  );
}

/** The root term `whole` manifests by derivation, or null when nothing matches. */
export function classify(o: Ontology, p: Probe): string | null {
  return matches(o, p)[0]?.term ?? null;
}
