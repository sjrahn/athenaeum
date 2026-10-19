// server.ts — the host daemon (§18.9): one socket for every `read` and `write` verb, and custody kept without asking.
// The socket is `$XDG_RUNTIME_DIR/athenaeum/athd.sock`, the host user's alone. `POST /v1/<verb>` carries the verb's
// arguments and the instance root as one JSON object and is run through `invoke` on the registry the daemon is handed
// — the same gates, locks and history as at the terminal — and answered with the envelope `--json` prints and the
// status §19.4.2 gives it. A socket caller is an `agent` at most; an admin verb, a global flag and a verb that runs
// until stopped are refused. Custody: each instance's jobs (`custody inventory`, `verify`, `reconcile`) run on the
// intervals `host.yaml` binds, after an ingest the daemon served, and when a store becomes available or an observed
// tree finishes a new generation; one job runs at a time, the index being the host's. A reconcile drains the
// instance's transfer queue — the actions its plan owes — which is kept in the host state, resumed when the daemon
// starts again, and retried after a back-off when a transfer fails. The daemon knows no custody of its own: every
// job is a verb anyone can run by hand.
import { chmodSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { isAbsolute } from "node:path";
import { errEnvelope } from "@ath/kit/envelope.ts";
import { AthError } from "@ath/kit/errors.ts";
import { writeAtomic } from "@ath/kit/fs.ts";
import { httpStatus, invoke } from "@ath/kit/invoke.ts";
import { narrowerProfile, parseProfile } from "@ath/kit/profiles.ts";
import type { Registry } from "@ath/kit/registry.ts";
import { findRoot, instanceId } from "@ath/kit/root.ts";
import type { Caller, Envelope } from "@ath/kit/types.ts";
import { hostPaths } from "@ath/kit/xdg.ts";
import { pidAlive } from "./client.ts";
import { type DaemonConfig, daemonPaths, JOBS, type JobKind, loadDaemonConfig } from "./config.ts";
import { emptyState, type JobState, jobKey, loadPersisted, nextAt, type Queued, savePersisted, settle } from "./jobs.ts";

export interface Timers {
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(t: unknown): void;
}

const realTimers: Timers = {
  setTimeout: (f, ms) => setTimeout(f, ms),
  clearTimeout: (t) => clearTimeout(t as ReturnType<typeof setTimeout>),
};

export interface StartOpts {
  registry: Registry;
  env: Record<string, string | undefined>;
  /** The clock the schedule runs on (ms); never `--now`. */
  now?: () => number;
  /** The wall clock the verbs it runs see. */
  wall?: () => Date;
  timers?: Timers;
  log?: (line: string) => void;
  /** How long after an ingest the instance is reconciled; ingests within it are reconciled together. */
  settleMs?: number;
  /** How long `stop` lets a running job finish. */
  stopWaitMs?: number;
}

interface Run {
  kind: JobKind;
  root: string;
  /** One store, for an inventory a store's event asked for. */
  store?: string;
}

export interface DaemonStatus {
  pid: number;
  socket: string;
  started_at: string;
  instances: string[];
  every: Partial<Record<JobKind, number>>;
  poll: number | null;
  reload_error: string | null;
  running: (Run & { since: string }) | null;
  pending: Run[];
  jobs: (Run & JobState & { next_at: string | null })[];
  queue: (Queued & { root: string })[];
}

export interface DaemonHandle {
  socket: string;
  pid: number;
  status(): DaemonStatus;
  /** Queue a job now, for one instance or every one the daemon keeps. */
  trigger(kind: JobKind, root: string | null): Run[];
  /** Re-read `host.yaml`; a broken one is refused and the running configuration kept. */
  reload(): DaemonConfig;
  /** One look at the schedule now: due jobs queued, the stores looked at when a look is due. */
  tick(): Promise<void>;
  /** Look at every instance's stores now. */
  poll(): Promise<void>;
  /** Resolves when no job runs or waits. */
  idle(): Promise<void>;
  stop(): Promise<void>;
}

/** Global flags (§19.4.1): the socket takes none of them. */
const GLOBALS = ["json", "now", "profile", "verbose", "quiet"];
/** Verbs that run until stopped: no request answers them. */
const RESIDENT: Record<string, string> = {
  "daemon-run": "the daemon is running: it is the one answering",
  serve: "serve runs until it is stopped, at a terminal or as a service of its own; it is not a request",
};

const iso = (ms: number) => `${new Date(ms).toISOString().slice(0, 19)}Z`;
const sameRun = (a: Run, b: Run) => a.kind === b.kind && a.root === b.root && a.store === b.store;

export async function startDaemon(o: StartOpts): Promise<DaemonHandle> {
  const host = hostPaths(o.env);
  const paths = daemonPaths(host);
  const now = o.now ?? Date.now;
  const timers = o.timers ?? realTimers;
  const log = o.log ?? (() => {});
  let config = loadDaemonConfig(host, o.env);
  let reloadError: string | null = null;

  mkdirSync(host.runtime, { recursive: true, mode: 0o700 });
  const prior = pidAlive(paths.pid);
  if (prior !== null && prior !== process.pid)
    throw new AthError("CONFLICT", `a host daemon is already running (pid ${prior}, ${paths.pid})`);
  writeAtomic(paths.pid, `${process.pid}\n`, 0o600);
  rmSync(paths.socket, { force: true }); // a dead daemon's socket

  const persisted = loadPersisted(paths.state);
  const save = () => {
    try {
      savePersisted(paths.state, persisted);
    } catch (e) {
      log(`could not save the jobs' state: ${(e as Error).message}`);
    }
  };
  const startedMs = now();
  const self: Caller = {
    profile: "agent",
    kind: "script",
    session: null,
    basis: ["the host daemon's own job → agent"],
    actor: o.env.ATH_ACTOR?.trim() || "athd",
    tty: false,
  };
  const run = (verb: string, args: Record<string, unknown>, root: string, history = true) =>
    invoke({
      registry: o.registry,
      verb,
      args,
      caller: self,
      root,
      env: o.env,
      cwd: root,
      wall: o.wall,
      history,
      via: "by the host daemon",
    });

  // ── the jobs: one at a time ──────────────────────────────────────────────────────────
  const pending: Run[] = [];
  let current: (Run & { since: string }) | null = null;
  let worker: Promise<void> | null = null;
  let stopped = false;

  const everyMs = (r: Run): number | undefined =>
    config.instances.includes(r.root) && config.every[r.kind] ? config.every[r.kind]! * 1000 : undefined;

  async function perform(r: Run): Promise<{ ok: boolean; detail: string }> {
    if (r.kind === "reconcile") {
      const p = await run("custody-plan", {}, r.root);
      if (p.envelope.ok) {
        const actions = (p.envelope.data as { actions: Queued["actions"] }).actions;
        if (actions.length) persisted.queue.set(r.root, { state: "running", at: iso(now()), actions });
        else persisted.queue.delete(r.root);
        save();
      }
      const res = await run("custody-reconcile", {}, r.root);
      const q = persisted.queue.get(r.root);
      if (!res.envelope.ok) {
        if (q) persisted.queue.set(r.root, { ...q, state: "pending" });
        return { ok: false, detail: res.envelope.error.message };
      }
      const d = res.envelope.data as { done: unknown[]; failed: (Queued["actions"][number] & { error: string })[]; unmet: unknown[] };
      if (d.failed.length)
        persisted.queue.set(r.root, {
          state: "pending",
          at: iso(now()),
          actions: d.failed.map(({ error: _e, ...a }) => a),
        });
      else persisted.queue.delete(r.root);
      const detail = `${d.done.length} done, ${d.failed.length} failed, ${d.unmet.length} unmet`;
      return { ok: res.exit === 0, detail: d.failed.length ? `${detail}: ${d.failed[0]!.error}` : detail };
    }
    if (r.kind === "inventory") {
      const res = await run("custody-inventory", r.store ? { store: r.store } : {}, r.root);
      if (!res.envelope.ok) return { ok: false, detail: res.envelope.error.message };
      const d = res.envelope.data as { stores: { store: string; present: number; missing: number }[]; unreachable: string[] };
      return {
        ok: true,
        detail: `${d.stores.map((s) => `${s.store} ${s.present} present, ${s.missing} missing`).join("; ")}${d.unreachable.length ? `; unreachable ${d.unreachable.join(", ")}` : ""}`,
      };
    }
    const res = await run("custody-verify", {}, r.root);
    if (!res.envelope.ok) return { ok: false, detail: res.envelope.error.message };
    const d = res.envelope.data as { verified: number; failed: unknown[] };
    // a copy that no longer verifies is a finding for reconcile, not a failure of the job
    if (d.failed.length) enqueue({ kind: "reconcile", root: r.root }, true);
    return { ok: true, detail: `${d.verified} verified, ${d.failed.length} failed` };
  }

  async function drain(): Promise<void> {
    while (pending.length && !stopped) {
      const r = pending.shift()!;
      current = { ...r, since: iso(now()) };
      log(`${r.kind}${r.store ? ` ${r.store}` : ""} for ${r.root}`);
      let out: { ok: boolean; detail: string };
      try {
        out = await perform(r);
      } catch (e) {
        out = { ok: false, detail: (e as Error).message };
      }
      const key = jobKey(r.kind, r.root);
      persisted.jobs.set(key, settle(persisted.jobs.get(key) ?? emptyState(), out.ok, out.detail, now(), everyMs(r)));
      save();
      log(`${r.kind} for ${r.root}: ${out.ok ? "" : "failed: "}${out.detail}`);
      current = null;
    }
  }

  const kick = () => {
    if (worker || stopped) return;
    worker = drain().finally(() => {
      worker = null;
      if (pending.length) kick();
      else arm();
    });
  };

  /** Queue a job; `again` queues it behind a run of the same job already under way (an event that came after it). */
  function enqueue(r: Run, again = false): boolean {
    if (stopped || pending.some((p) => sameRun(p, r))) return false;
    if (!again && current && sameRun(current, r)) return false;
    pending.push(r);
    kick();
    return true;
  }

  // ── the schedule ─────────────────────────────────────────────────────────────────────
  let lastPoll = Number.NEGATIVE_INFINITY;
  let wake: unknown;
  const busy = (r: Run) => (current && sameRun(current, r)) || pending.some((p) => sameRun(p, r));

  /** Every job the schedule or a back-off owes a time, with that time. */
  function owed(): { run: Run; at: number }[] {
    const out: { run: Run; at: number }[] = [];
    for (const root of config.instances)
      for (const kind of JOBS) {
        const r = { kind, root };
        const at = nextAt(persisted.jobs.get(jobKey(kind, root)) ?? emptyState(), everyMs(r), startedMs);
        if (at !== null) out.push({ run: r, at });
      }
    for (const [key, st] of persisted.jobs) {
      if (!st.failures || !st.retry_at) continue;
      const sp = key.indexOf(" ");
      const r = { kind: key.slice(0, sp) as JobKind, root: key.slice(sp + 1) };
      if (!out.some((x) => sameRun(x.run, r))) out.push({ run: r, at: Date.parse(st.retry_at) });
    }
    return out;
  }

  function arm(): void {
    if (stopped) return;
    if (wake !== undefined) timers.clearTimeout(wake);
    const t = now();
    let next = t + 3600_000;
    for (const x of owed()) if (!busy(x.run)) next = Math.min(next, x.at);
    if (config.poll) next = Math.min(next, lastPoll + config.poll * 1000);
    wake = timers.setTimeout(() => void tick().finally(arm), Math.max(1000, next - t));
  }

  async function tick(): Promise<void> {
    const t = now();
    for (const x of owed()) if (x.at <= t && !busy(x.run)) enqueue(x.run);
    if (config.poll && t - lastPoll >= config.poll * 1000) await poll();
  }

  // what each store looked like at the last look: a store becoming available, or an observed tree's new generation
  const seen = new Map<string, { reachable: boolean; generation?: number }>();
  async function poll(): Promise<void> {
    lastPoll = now();
    for (const root of config.instances) {
      const { envelope } = await run("store-list", {}, root, false);
      if (!envelope.ok) {
        log(`stores of ${root}: ${envelope.error.message}`);
        continue;
      }
      for (const s of (envelope.data as { stores: { id: string; name: string; reachable: boolean; generation?: number }[] }).stores) {
        const k = `${root} ${s.id}`;
        const was = seen.get(k);
        seen.set(k, { reachable: s.reachable, ...(s.generation !== undefined ? { generation: s.generation } : {}) });
        if (!was) continue;
        const back = s.reachable && !was.reachable;
        const newer = s.generation !== undefined && s.generation > (was.generation ?? -1);
        if (!back && !newer) continue;
        log(`${s.name} of ${root}: ${back ? "available again" : `generation ${s.generation}`}`);
        enqueue({ kind: "inventory", root, store: s.name }, true);
        enqueue({ kind: "reconcile", root }, true);
      }
    }
  }

  const settling = new Map<string, unknown>();
  function ingested(root: string): void {
    const t = settling.get(root);
    if (t !== undefined) timers.clearTimeout(t);
    settling.set(
      root,
      timers.setTimeout(() => {
        settling.delete(root);
        enqueue({ kind: "reconcile", root }, true);
      }, o.settleMs ?? 5000),
    );
  }

  // ── the socket ───────────────────────────────────────────────────────────────────────
  const reply = (env: Envelope) =>
    new Response(`${JSON.stringify(env)}\n`, {
      status: httpStatus(env),
      headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
    });
  const refuse = (cmd: string, code: AthError["code"], msg: string) => reply(errEnvelope(cmd, new AthError(code, msg), 0));

  async function answer(req: Request): Promise<Response> {
    const path = new URL(req.url).pathname;
    const m = /^\/v1\/([a-z][a-z0-9-]*)$/.exec(path);
    if (!m) return refuse("", "NOT_FOUND", `no route ${path}: a verb is POST /v1/<verb>`);
    const verb = m[1]!;
    if (req.method !== "POST") return refuse(verb, "USAGE", `${verb}: a verb is asked with POST`);
    const def = o.registry.resolve([verb])?.def;
    const key = def?.contract.key ?? verb;
    if (RESIDENT[key]) return refuse(key, "USAGE", `${key}: ${RESIDENT[key]}`);
    let body: Record<string, unknown>;
    try {
      const text = await req.text();
      body = text.trim() ? (JSON.parse(text) as Record<string, unknown>) : {};
    } catch {
      return refuse(key, "USAGE", `${key}: the body is not JSON`);
    }
    if (!body || typeof body !== "object" || Array.isArray(body)) return refuse(key, "USAGE", `${key}: the arguments are one JSON object`);
    const declared = def ? Object.keys((def.contract.args as { shape?: object }).shape ?? {}) : [];
    for (const g of GLOBALS)
      if (g in body && !declared.includes(g)) return refuse(key, "USAGE", `${key}: \`${g}\` is a global flag; the socket takes none`);
    const { root: rootArg, ...args } = body;
    const cwd = req.headers.get("ath-cwd") ?? undefined;
    if (cwd !== undefined && !isAbsolute(cwd)) return refuse(key, "USAGE", `${key}: ath-cwd is an absolute path`);
    if (rootArg !== undefined && (typeof rootArg !== "string" || !isAbsolute(rootArg)))
      return refuse(key, "USAGE", `${key}: root is an absolute path`);
    const root = (rootArg as string | undefined) ?? findRoot(cwd ?? "/", {});
    let profile: Caller["profile"] = "agent";
    const asked = req.headers.get("ath-profile");
    if (asked) {
      try {
        profile = narrowerProfile("agent", parseProfile(asked, "ath-profile"));
      } catch (e) {
        return refuse(key, "USAGE", (e as Error).message);
      }
    }
    const caller: Caller = {
      profile,
      kind: "script",
      session: null,
      basis: ["a caller over the daemon's socket → agent at most"],
      actor: req.headers.get("ath-actor")?.trim() || null,
      tty: false,
    };
    const { envelope } = await invoke({
      registry: o.registry,
      verb,
      args,
      caller,
      root,
      env: o.env,
      cwd: cwd ?? root ?? "/",
      wall: o.wall,
      via: "over the daemon's socket",
    });
    if (key === "ingest" && envelope.ok && root) ingested(root);
    return reply(envelope);
  }

  let server: ReturnType<typeof Bun.serve>;
  try {
    server = Bun.serve({
      unix: paths.socket,
      fetch: (req) => answer(req).catch((e: unknown) => refuse("", "INTERNAL", (e as Error).message)),
    });
    chmodSync(paths.socket, 0o600);
  } catch (e) {
    rmSync(paths.pid, { force: true });
    throw new AthError("EXTERNAL", `could not listen on ${paths.socket}: ${(e as Error).message}`);
  }

  // an interrupted queue resumes first; then a baseline look at the stores, and the schedule
  for (const [root, q] of persisted.queue) if (q.actions.length) enqueue({ kind: "reconcile", root });
  if (config.poll) await poll();
  await tick();
  arm();

  const handle: DaemonHandle = {
    socket: paths.socket,
    pid: process.pid,
    status() {
      const runs = new Map<string, Run>();
      for (const root of config.instances) for (const kind of JOBS) if (config.every[kind]) runs.set(jobKey(kind, root), { kind, root });
      for (const k of persisted.jobs.keys()) {
        const sp = k.indexOf(" ");
        runs.set(k, { kind: k.slice(0, sp) as JobKind, root: k.slice(sp + 1) });
      }
      return {
        pid: process.pid,
        socket: paths.socket,
        started_at: iso(startedMs),
        instances: config.instances,
        every: config.every,
        poll: config.poll ?? null,
        reload_error: reloadError,
        running: current,
        pending: [...pending],
        jobs: [...runs]
          .sort(([a], [b]) => (a < b ? -1 : 1))
          .map(([k, r]) => {
            const st = persisted.jobs.get(k) ?? emptyState();
            const at = nextAt(st, everyMs(r), startedMs);
            return { ...r, ...st, next_at: at === null ? null : iso(Math.max(at, now())) };
          }),
        queue: [...persisted.queue].map(([root, q]) => ({ root, ...q })),
      };
    },
    trigger(kind, root) {
      const roots = root ? [root] : config.instances;
      if (root && !instanceId(root)) throw new AthError("NOT_FOUND", `no instance at ${root}`);
      if (!roots.length) throw new AthError("NOT_FOUND", "host.yaml binds no instance to the daemon, and none was named");
      const out: Run[] = [];
      for (const r of roots) {
        const run = { kind, root: r };
        enqueue(run, true);
        out.push(run);
      }
      return out;
    },
    reload() {
      try {
        config = loadDaemonConfig(host, o.env);
      } catch (e) {
        reloadError = (e as Error).message;
        throw e;
      }
      reloadError = null;
      log(`configuration re-read: ${config.instances.length} instances`);
      arm();
      return config;
    },
    tick,
    poll,
    async idle() {
      while (worker || pending.length || settling.size) await (worker ?? Bun.sleep(5));
    },
    async stop() {
      if (stopped) return;
      stopped = true;
      if (wake !== undefined) timers.clearTimeout(wake);
      for (const t of settling.values()) timers.clearTimeout(t);
      settling.clear();
      pending.length = 0;
      await server.stop(true);
      if (worker) {
        let t: ReturnType<typeof setTimeout> | undefined;
        await Promise.race([worker, new Promise<void>((r) => (t = setTimeout(r, o.stopWaitMs ?? 60_000)))]);
        clearTimeout(t);
      }
      save();
      rmSync(paths.socket, { force: true });
      try {
        if (readFileSync(paths.pid, "utf8").trim() === String(process.pid)) rmSync(paths.pid, { force: true });
      } catch {
        // already gone
      }
    },
  };
  return handle;
}
