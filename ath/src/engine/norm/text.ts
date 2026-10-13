// text.ts — the one normaliser G4 and L7 share (D-L7): NFKC, quote and dash folding, NBSP → space, whitespace
// collapse; then a second pass with whitespace and hyphens removed. A quote is in a surface when either pass finds
// it; prefix/suffix, when given, must bracket the match.
const QUOTES: Record<string, string> = { "‘": "'", "’": "'", "‚": "'", "‛": "'", "“": '"', "”": '"', "„": '"', "′": "'", "″": '"' };
const DASHES = /[‐‑‒–—―−]/g;

export function normalize(s: string): string {
  return s
    .normalize("NFKC")
    .replace(/[‘’‚‛“”„′″]/g, (c) => QUOTES[c] ?? c)
    .replace(DASHES, "-")
    .replace(/[   ]/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\s+([,.;:!?)])/g, "$1")
    .trim();
}

export function squash(s: string): string {
  return normalize(s)
    .replace(/[\s-]+/g, "")
    .toLowerCase();
}

export interface QuoteMatch {
  found: boolean;
  /** Which pass matched: exact (after normalisation) or squashed. */
  pass?: "normalized" | "squashed";
  /** Why not, when not. */
  why?: string;
}

export function quoteIn(surface: string, quote: string, prefix?: string, suffix?: string): QuoteMatch {
  const S = normalize(surface);
  const Q = normalize(quote);
  if (!Q) return { found: false, why: "empty quote" };
  if (S.includes(Q)) {
    if (prefix !== undefined || suffix !== undefined) {
      const needle = `${prefix ? normalize(prefix) : ""}${Q}${suffix ? normalize(suffix) : ""}`;
      if (!S.includes(needle)) return { found: false, why: "quote found but not between its prefix and suffix" };
    }
    return { found: true, pass: "normalized" };
  }
  const s2 = squash(surface);
  const q2 = squash(quote);
  if (q2 && s2.includes(q2)) return { found: true, pass: "squashed" };
  return { found: false, why: "quote not in surface" };
}

/** Collapse a cells body (string[] or string[][]) to one matchable surface. */
export function cellsSurface(body: unknown): string {
  if (typeof body === "string") return body;
  if (Array.isArray(body)) return body.map((c) => (Array.isArray(c) ? c.map(String).join("\t") : String(c))).join("\n");
  return String(body);
}
