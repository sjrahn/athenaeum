// duration.ts — a span of time as written in a declaration: a whole number and a unit, `90d`, `6h`, `30s`. A policy's
// `verify` and the daemon's schedule (§18.6, §18.9) read it.
const DUR = /^(\d+)\s*(s|m|h|d|w|y)$/;
const SECONDS: Record<string, number> = { s: 1, m: 60, h: 3600, d: 86400, w: 604800, y: 31557600 };

/** Seconds, or null when the text is no duration. */
export function parseDuration(v: unknown): number | null {
  const m = DUR.exec(String(v).trim());
  return m ? Number(m[1]) * SECONDS[m[2]!]! : null;
}
