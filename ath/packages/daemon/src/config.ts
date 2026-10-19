// config.ts — what the host binds for its daemon, the `daemon` section of `$XDG_CONFIG_HOME/athenaeum/host.yaml`
// (§5.6): the instances whose custody it keeps, how often each job runs for each of them, and how often it looks at
// the stores for one becoming available or an observed tree's new generation. A job with no interval runs on events
// and on demand only. The socket and the pid live under the runtime directory; the jobs' state and the transfer queue
// under the host state.
import { existsSync, readFileSync } from "node:fs";
import { isAbsolute, join } from "node:path";
import { parseDuration } from "@ath/kit/duration.ts";
import { AthError } from "@ath/kit/errors.ts";
import type { HostPaths } from "@ath/kit/xdg.ts";

/** The daemon's jobs, each a custody verb (§19.5) run for one instance. */
export const JOBS = ["inventory", "verify", "reconcile"] as const;
export type JobKind = (typeof JOBS)[number];

export interface DaemonConfig {
  instances: string[];
  /** Seconds between runs, per job; a job absent here is not scheduled. */
  every: Partial<Record<JobKind, number>>;
  /** Seconds between looks at every instance's stores; absent, the daemon does not look. */
  poll?: number;
}

export interface DaemonPaths {
  socket: string;
  pid: string;
  /** `jobs.json`, `queue.json`. */
  state: string;
}

export const daemonPaths = (host: HostPaths): DaemonPaths => ({
  socket: join(host.runtime, "athd.sock"),
  pid: join(host.runtime, "athd.pid"),
  state: join(host.state, "daemon"),
});

export function loadDaemonConfig(host: HostPaths, env: Record<string, string | undefined>): DaemonConfig {
  const p = join(host.config, "host.yaml");
  const out: DaemonConfig = { instances: [], every: {} };
  if (!existsSync(p)) return out;
  const bad = (m: string): never => {
    throw new AthError("CONFIG", `${p}: daemon: ${m}`);
  };
  let doc: { daemon?: unknown } | null;
  try {
    doc = Bun.YAML.parse(readFileSync(p, "utf8")) as typeof doc;
  } catch (e) {
    throw new AthError("CONFIG", `${p}: ${(e as Error).message}`);
  }
  const d = doc?.daemon;
  if (d === undefined || d === null) return out;
  if (typeof d !== "object" || Array.isArray(d)) return bad("is a mapping: instances, every, poll");
  const o = d as Record<string, unknown>;
  for (const k of Object.keys(o)) if (!["instances", "every", "poll"].includes(k)) bad(`\`${k}\` is not a key of the daemon`);
  const inst = o.instances ?? [];
  if (!Array.isArray(inst) || !inst.every((x) => typeof x === "string")) bad("`instances` is a list of paths");
  for (const x of inst as string[]) {
    const path = x.startsWith("~/") && env.HOME ? join(env.HOME, x.slice(2)) : x;
    if (!isAbsolute(path)) bad(`instance ${x} is not an absolute path`);
    if (!out.instances.includes(path)) out.instances.push(path);
  }
  const every = o.every ?? {};
  if (typeof every !== "object" || Array.isArray(every)) bad("`every` maps a job to a duration: {reconcile: 1h}");
  for (const [k, v] of Object.entries(every as Record<string, unknown>)) {
    if (!(JOBS as readonly string[]).includes(k)) bad(`every: \`${k}\` is not a job (${JOBS.join(", ")})`);
    const s = parseDuration(v);
    if (!s) bad(`every.${k} is a duration: 1h`);
    out.every[k as JobKind] = s!;
  }
  if (o.poll !== undefined) {
    const s = parseDuration(o.poll);
    if (!s) bad("`poll` is a duration: 5m");
    out.poll = s!;
  }
  return out;
}
