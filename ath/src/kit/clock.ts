// clock.ts — the injected clock: `--now` fixes it for reproducible pass dates; otherwise the wall clock.
import type { Clock } from "./types.ts";

export function makeClock(now?: string): Clock {
  if (now !== undefined) {
    const d = new Date(now);
    if (Number.isNaN(d.getTime())) throw new Error(`--now: not an ISO-8601 instant: '${now}'`);
    return { now: () => new Date(d.getTime()), iso: () => d.toISOString() };
  }
  return { now: () => new Date(), iso: () => new Date().toISOString() };
}
