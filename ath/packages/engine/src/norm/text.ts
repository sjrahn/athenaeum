// text.ts — the one normaliser (spec §13.4.2) the reading check and binding share: Unicode NFKC, typographic quotes and
// dashes folded to ASCII, no-break spaces to spaces, whitespace runs collapsed. Punctuation is content. The squashed
// comparison — whitespace and hyphens removed — serves the reading check alone and never binds a quote.
const QUOTES: Record<string, string> = { "‘": "'", "’": "'", "‚": "'", "‛": "'", "“": '"', "”": '"', "„": '"', "′": "'", "″": '"' };
const DASHES = /[‐‑‒–—―−]/g;

export function normalize(s: string): string {
  return s
    .normalize("NFKC")
    .replace(/[‘’‚‛“”„′″]/g, (c) => QUOTES[c] ?? c)
    .replace(DASHES, "-")
    .replace(/[   ]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function squash(s: string): string {
  return normalize(s)
    .replace(/[\s-]+/g, "")
    .toLowerCase();
}

/** Whether a quote, with its prefix and suffix, lies in a body under the normaliser — never squashed (§14.4.2). */
export function quoteIn(body: string, quote: string, prefix?: string, suffix?: string): boolean {
  if (!normalize(quote)) return false;
  // prefix, quote and suffix are one run of the body, normalised together
  return normalize(body).includes(normalize(`${prefix ?? ""}${quote}${suffix ?? ""}`));
}

/** Collapse a cells body (string[] or string[][]) to one matchable surface. */
export function cellsSurface(body: unknown): string {
  if (typeof body === "string") return body;
  if (Array.isArray(body)) return body.map((c) => (Array.isArray(c) ? c.map(String).join("\t") : String(c))).join("\n");
  return String(body);
}
