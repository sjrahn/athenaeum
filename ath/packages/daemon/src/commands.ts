// commands.ts — the `daemon` verbs (§19.5): `run` the daemon in the foreground; `status`, `trigger <job>` and
// `reload`, which a caller asks of the running daemon over its socket — `unavailable` (69) when none runs — and which
// the daemon answers from itself when the request lands there; `install` and `uninstall` the host's service unit,
// the owner's, confirmed at a terminal.
import { existsSync, rmSync } from "node:fs";
import { join } from "node:path";
import { defineContract, z } from "@ath/contracts";
import { defineCommand } from "@ath/kit/define.ts";
import { AthError } from "@ath/kit/errors.ts";
import { writeAtomic } from "@ath/kit/fs.ts";
import type { Registry } from "@ath/kit/registry.ts";
import type { KitCtx } from "@ath/kit/types.ts";
import { ask, type SocketFetch } from "./client.ts";
import { daemonPaths, JOBS } from "./config.ts";
import { type DaemonHandle, type DaemonStatus, type StartOpts, startDaemon } from "./server.ts";
import { athBin, renderUnit, UNIT_NAME, unitDir } from "./unit.ts";

export interface DaemonDeps {
  /** The daemon running in this process, once `daemon run` has started it. */
  local?: { handle: DaemonHandle | null };
  start?: (o: StartOpts) => Promise<DaemonHandle>;
  /** Resolves when the process is told to stop (default SIGTERM or SIGINT); `reload` is called on SIGHUP. */
  untilStopped?: (reload: () => void) => Promise<void>;
  fetch?: SocketFetch;
  /** `systemctl --user <args>`; absent, the host's. */
  systemctl?: (args: string[]) => { ok: boolean; err: string };
}

const untilSignal = (reload: () => void): Promise<void> =>
  new Promise((resolve) => {
    process.on("SIGHUP", reload);
    const done = () => {
      process.off("SIGHUP", reload);
      resolve();
    };
    process.once("SIGTERM", done);
    process.once("SIGINT", done);
  });

const hostSystemctl = (args: string[]) => {
  const exe = Bun.which("systemctl", { PATH: process.env.PATH ?? "" });
  if (!exe) return { ok: false, err: "systemctl is not on PATH" };
  const r = Bun.spawnSync([exe, "--user", ...args], { stdout: "pipe", stderr: "pipe", env: process.env });
  return { ok: r.exitCode === 0, err: r.stderr.toString().trim() };
};

const runRow = z.object({ kind: z.enum(JOBS), root: z.string(), store: z.string().optional() });
const actionRow = z.object({ op: z.string(), hash: z.string(), tree: z.string(), store: z.string(), why: z.string() });
const statusData = z.object({
  pid: z.number(),
  socket: z.string(),
  started_at: z.string(),
  instances: z.array(z.string()),
  every: z.record(z.string(), z.number()),
  poll: z.number().nullable(),
  reload_error: z.string().nullable(),
  running: runRow.extend({ since: z.string() }).nullable(),
  pending: z.array(runRow),
  jobs: z.array(
    runRow.extend({
      last_run: z.string().nullable(),
      last_ok: z.boolean().nullable(),
      failures: z.number(),
      retry_at: z.string().nullable(),
      detail: z.string().nullable(),
      next_at: z.string().nullable(),
    }),
  ),
  queue: z.array(z.object({ root: z.string(), state: z.enum(["pending", "running"]), at: z.string(), actions: z.array(actionRow) })),
});

const secs = (n: number) => (n % 86400 === 0 ? `${n / 86400}d` : n % 3600 === 0 ? `${n / 3600}h` : n % 60 === 0 ? `${n / 60}m` : `${n}s`);

export function registerDaemon(r: Registry, deps: DaemonDeps = {}): void {
  const local = deps.local ?? { handle: null };
  const socketOf = (ctx: KitCtx) => daemonPaths(ctx.host).socket;
  const askDaemon = <D>(ctx: KitCtx, verb: string, body: Record<string, unknown> = {}) =>
    ask<D>({
      socket: socketOf(ctx),
      verb,
      body: { ...body, ...(ctx.root ? { root: ctx.root } : {}) },
      caller: ctx.caller,
      cwd: ctx.cwd,
      ...(deps.fetch ? { fetch: deps.fetch } : {}),
    });

  r.registerGroup("daemon", "the host daemon: one socket for every verb, and custody kept on a schedule and on events");

  r.register(
    defineCommand({
      meta: {
        summary: "run the host daemon in the foreground until it is stopped (the service unit's command)",
        tier: "write",
        mutating: true,
        help: "Reads the `daemon` section of $XDG_CONFIG_HOME/athenaeum/host.yaml:\n\n  daemon:\n    instances: [~/athenaeum]\n    every: {inventory: 1d, verify: 30d, reconcile: 1h}\n    poll: 5m\n\nSIGHUP re-reads it; SIGTERM stops the daemon once a running job has finished.",
      },
      contract: defineContract({
        key: "daemon-run",
        args: z.object({}),
        argv: {},
        data: z.object({ socket: z.string(), pid: z.number() }),
      }),
      async run(ctx) {
        if (local.handle) throw new AthError("CONFLICT", "the daemon is already running in this process");
        const h = await (deps.start ?? startDaemon)({
          registry: r,
          env: ctx.env,
          wall: () => ctx.wall.now(),
          log: (line) => ctx.events.emit({ kind: "daemon.log", level: "info", msg: line }),
        });
        local.handle = h;
        ctx.events.emit({ kind: "daemon.started", level: "info", msg: `athd ${h.pid} on ${h.socket}` });
        try {
          await (deps.untilStopped ?? untilSignal)(() => {
            try {
              h.reload();
            } catch (e) {
              ctx.events.emit({ kind: "daemon.log", level: "warn", msg: `reload refused: ${(e as Error).message}` });
            }
          });
        } finally {
          await h.stop();
          local.handle = null;
        }
        return { data: { socket: h.socket, pid: h.pid } };
      },
      text: (d, io) => io.out(`athd ${d.pid} stopped (${d.socket})\n`),
    }),
  );

  r.register(
    defineCommand({
      meta: {
        summary: "the running daemon: its instances, its jobs and when each runs next, and the transfer queue",
        tier: "read",
        mutating: false,
      },
      contract: defineContract({ key: "daemon-status", args: z.object({}), argv: {}, data: statusData }),
      async run(ctx) {
        if (local.handle) return { data: local.handle.status() };
        return askDaemon<DaemonStatus>(ctx, "daemon-status");
      },
      text(d, io) {
        io.out(`athd ${d.pid} since ${d.started_at} on ${d.socket}\n`);
        if (d.reload_error) io.out(`  reload refused: ${d.reload_error}\n`);
        const every = Object.entries(d.every).map(([k, v]) => `${k} every ${secs(v)}`);
        io.out(
          `  ${d.instances.length} instances${every.length ? `; ${every.join(", ")}` : ""}${d.poll ? `; stores looked at every ${secs(d.poll)}` : ""}\n`,
        );
        if (d.running)
          io.out(
            `  running  ${d.running.kind}${d.running.store ? ` ${d.running.store}` : ""} for ${d.running.root} since ${d.running.since}\n`,
          );
        for (const p of d.pending) io.out(`  waiting  ${p.kind}${p.store ? ` ${p.store}` : ""} for ${p.root}\n`);
        for (const j of d.jobs)
          io.out(
            `  ${j.kind.padEnd(9)} ${j.root}  ${j.last_ok === null ? "never ran" : j.last_ok ? `ok ${j.last_run}` : `failing ×${j.failures}, retry ${j.retry_at}`}${j.next_at ? `, next ${j.next_at}` : ""}${j.detail ? `  (${j.detail})` : ""}\n`,
          );
        for (const q of d.queue) io.out(`  queue    ${q.root}: ${q.actions.length} actions ${q.state} since ${q.at}\n`);
      },
    }),
  );

  r.register(
    defineCommand({
      meta: {
        summary: "run a job now: for the instance the caller is in, else for every instance the daemon keeps",
        tier: "write",
        mutating: true,
        examples: ["ath daemon trigger reconcile"],
      },
      contract: defineContract({
        key: "daemon-trigger",
        args: z.object({ job: z.enum(JOBS) }),
        argv: { positionals: [{ name: "job", required: true, help: JOBS.join(" · ") }] },
        data: z.object({ queued: z.array(runRow) }),
      }),
      async run(ctx, a) {
        if (local.handle) return { data: { queued: local.handle.trigger(a.job, ctx.root) } };
        return askDaemon<{ queued: z.infer<typeof runRow>[] }>(ctx, "daemon-trigger", { job: a.job });
      },
      text: (d, io) => {
        for (const q of d.queued) io.out(`${q.kind} queued for ${q.root}\n`);
      },
    }),
  );

  r.register(
    defineCommand({
      meta: {
        summary: "the running daemon re-reads host.yaml; a broken file is refused and the running one kept",
        tier: "write",
        mutating: true,
      },
      contract: defineContract({
        key: "daemon-reload",
        args: z.object({}),
        argv: {},
        data: z.object({ instances: z.array(z.string()), every: z.record(z.string(), z.number()), poll: z.number().nullable() }),
      }),
      async run(ctx) {
        if (local.handle) {
          const c = local.handle.reload();
          return { data: { instances: c.instances, every: c.every, poll: c.poll ?? null } };
        }
        return askDaemon<{ instances: string[]; every: Record<string, number>; poll: number | null }>(ctx, "daemon-reload");
      },
      text: (d, io) => io.out(`re-read: ${d.instances.length} instances\n`),
    }),
  );

  const systemctl = (args: string[]) => (deps.systemctl ?? hostSystemctl)(args);
  const unitPath = (ctx: KitCtx) => join(unitDir(ctx.host.config), UNIT_NAME);

  r.register(
    defineCommand({
      meta: { summary: "install the host's service unit for athd and start it", tier: "admin", mutating: true },
      contract: defineContract({
        key: "daemon-install",
        args: z.object({}),
        argv: {},
        data: z.object({ unit: z.string(), bin: z.string() }),
      }),
      run(ctx) {
        const bin = athBin(ctx.env);
        const path = unitPath(ctx);
        writeAtomic(path, renderUnit({ bin, path: ctx.env.PATH ?? "/usr/local/bin:/usr/bin:/bin" }));
        for (const args of [["daemon-reload"], ["enable", "--now", UNIT_NAME]]) {
          const res = systemctl(args);
          if (!res.ok) throw new AthError("EXTERNAL", `systemctl --user ${args.join(" ")}: ${res.err}`);
        }
        return { data: { unit: path, bin } };
      },
      text: (d, io) => io.out(`installed ${d.unit}, running ${d.bin} daemon run\n`),
    }),
  );

  r.register(
    defineCommand({
      meta: { summary: "stop athd and remove the host's service unit", tier: "admin", mutating: true },
      contract: defineContract({
        key: "daemon-uninstall",
        args: z.object({}),
        argv: {},
        data: z.object({ unit: z.string(), removed: z.boolean() }),
      }),
      run(ctx) {
        const path = unitPath(ctx);
        const was = existsSync(path);
        if (was) {
          const off = systemctl(["disable", "--now", UNIT_NAME]);
          if (!off.ok) throw new AthError("EXTERNAL", `systemctl --user disable --now ${UNIT_NAME}: ${off.err}`);
          rmSync(path, { force: true });
          const res = systemctl(["daemon-reload"]);
          if (!res.ok) throw new AthError("EXTERNAL", `systemctl --user daemon-reload: ${res.err}`);
        }
        return { data: { unit: path, removed: was } };
      },
      text: (d, io) => io.out(d.removed ? `removed ${d.unit}\n` : `no unit at ${d.unit}\n`),
    }),
  );
}
