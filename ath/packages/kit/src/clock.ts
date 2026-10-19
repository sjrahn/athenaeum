// clock.ts — the injected clock: `--now` fixes it for reproducible output; otherwise the wall clock. Every instant
// is written in whole-second UTC (`YYYY-MM-DDTHH:MM:SSZ`), one format everywhere.
import type { Clock } from "./types.ts";

/** An instant in whole-second UTC. */
export const isoSecond = (d: Date): string => `${d.toISOString().slice(0, 19)}Z`;

const at = (now: () => Date): Clock => ({ now, iso: () => isoSecond(now()), date: () => now().toISOString().slice(0, 10) });

/** The wall clock, which `--now` never moves. */
export const wallClock = (): Clock => at(() => new Date());

export function makeClock(now?: string): Clock {
  if (now === undefined) return wallClock();
  const d = new Date(now);
  if (Number.isNaN(d.getTime())) throw new Error(`--now: not an ISO-8601 instant: '${now}'`);
  return at(() => new Date(d.getTime()));
}
