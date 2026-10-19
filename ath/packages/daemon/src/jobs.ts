// jobs.ts — when the daemon's jobs run, as pure functions of their state and the clock. A job is one custody verb for
// one instance. A scheduled job runs at the daemon's start when it never ran, then each interval after its last run;
// a failing job is retried after a back-off that doubles from a minute to six hours (never beyond its interval) and
// resets on success. Intervals are spans of real time, so a change of the clocks' offset moves nothing.
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { isoSecond } from "@ath/kit/clock.ts";
import { writeAtomic } from "@ath/kit/fs.ts";
import type { JobKind } from "./config.ts";

export interface JobState {
  last_run: string | null;
  last_ok: boolean | null;
  failures: number;
  retry_at: string | null;
  /** What the last run said of itself. */
  detail: string | null;
}

export const jobKey = (kind: JobKind, root: string): string => `${kind} ${root}`;
export const emptyState = (): JobState => ({ last_run: null, last_ok: null, failures: 0, retry_at: null, detail: null });

const MINUTE = 60_000;
const BACKOFF_CAP = 6 * 3600_000;

/** How long a job waits after its `failures`-th failure in a row. */
export function backoffMs(failures: number, everyMs?: number): number {
  const d = Math.min(MINUTE * 2 ** Math.max(0, failures - 1), BACKOFF_CAP);
  return everyMs ? Math.min(d, everyMs) : d;
}

/** When a job next runs, in ms: its retry when failing, else its interval after the last run (at once when it never
 * ran), else never. */
export function nextAt(s: JobState, everyMs: number | undefined, startedMs: number): number | null {
  if (s.failures > 0 && s.retry_at) return Date.parse(s.retry_at);
  if (!everyMs) return null;
  if (!s.last_run) return startedMs;
  return Date.parse(s.last_run) + everyMs;
}

/** The state after a run that ended at `nowMs`. */
export function settle(s: JobState, ok: boolean, detail: string, nowMs: number, everyMs?: number): JobState {
  const at = isoSecond(new Date(nowMs));
  if (ok) return { last_run: at, last_ok: true, failures: 0, retry_at: null, detail };
  const failures = s.failures + 1;
  return { last_run: at, last_ok: false, failures, retry_at: isoSecond(new Date(nowMs + backoffMs(failures, everyMs))), detail };
}

/** The transfer queue of one instance: the actions its last plan owed, and whether a reconcile is draining them. */
export interface Queued {
  state: "pending" | "running";
  at: string;
  actions: { op: string; hash: string; tree: string; store: string; why: string }[];
}

export interface Persisted {
  jobs: Map<string, JobState>;
  queue: Map<string, Queued>;
}

const readJson = (p: string): Record<string, unknown> => {
  if (!existsSync(p)) return {};
  try {
    return JSON.parse(readFileSync(p, "utf8")) as Record<string, unknown>;
  } catch {
    return {};
  }
};

/** The jobs' state and the queue as the last daemon left them; an unreadable file is a fresh start. */
export function loadPersisted(dir: string): Persisted {
  return {
    jobs: new Map(Object.entries(readJson(join(dir, "jobs.json"))).map(([k, v]) => [k, { ...emptyState(), ...(v as JobState) }])),
    queue: new Map(Object.entries(readJson(join(dir, "queue.json"))) as [string, Queued][]),
  };
}

export function savePersisted(dir: string, p: Persisted): void {
  const sorted = <V>(m: Map<string, V>) => Object.fromEntries([...m].sort(([a], [b]) => (a < b ? -1 : 1)));
  writeAtomic(join(dir, "jobs.json"), `${JSON.stringify(sorted(p.jobs), null, 2)}\n`, 0o600);
  writeAtomic(join(dir, "queue.json"), `${JSON.stringify(sorted(p.queue), null, 2)}\n`, 0o600);
}
