// daemon.test.ts — the host daemon (§18.9, §19.4.2): every read and write verb over its socket through the same
// registry, the envelope `--json` prints byte for byte and the status each code answers with; a socket caller an agent
// at most, admin verbs, global flags and resident verbs refused, the actor taken from the request; verbs that write the
// host index handed to the daemon while it runs and run in-process when it does not, failing closed when its process
// lives and its socket does not answer; the `daemon` verbs `unavailable` without it; jobs on a schedule, after an
// ingest and when a store becomes available, one at a time, with a back-off and a transfer queue resumed after a
// restart; the service unit; bandwidth limits and a store's availability read from its mark.

import { Database } from "bun:sqlite";
import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { buildRegistry } from "@ath/cli/main.ts";
import { loadAccess, openIndex } from "@ath/custody";
import { pace } from "@ath/custody/drivers.ts";
import { backoffMs, type DaemonHandle, daemonPaths, forwarder, loadDaemonConfig, nextAt, request, settle, startDaemon } from "@ath/daemon";
import { instanceId } from "@ath/kit/root.ts";
import { hostPaths } from "@ath/kit/xdg.ts";
import { ath, type RunOpts, scratch } from "./harness.ts";

const FAKE_BIN = join(import.meta.dir, "fixtures", "bin");
const PATH = process.env.PATH;
beforeAll(() => {
  process.env.PATH = `${FAKE_BIN}:${PATH}`;
});
afterAll(() => {
  process.env.PATH = PATH;
});

const WALL = new Date("2026-03-20T09:00:00Z");

/** A host of its own — scratch home, XDG bases, runtime directory — with an instance under it. */
async function host() {
  const h = scratch("ath-d-");
  const env: Record<string, string> = {
    ATH_ACTOR: "owner-a",
    HOME: h,
    XDG_DATA_HOME: join(h, "data"),
    XDG_STATE_HOME: join(h, "state"),
    XDG_CONFIG_HOME: join(h, "config"),
    XDG_CACHE_HOME: join(h, "cache"),
    XDG_RUNTIME_DIR: join(h, "run"),
  };
  const root = join(h, "household");
  expect((await ath(["instance", "init", root], { env })).code).toBe(0);
  const paths = daemonPaths(hostPaths(env));
  const run = async (argv: string[], o: RunOpts = {}) => ath(["--json", ...argv], { env, cwd: root, ...o });
  const ok = async (argv: string[], o: RunOpts = {}) => {
    const r = await run(argv, o);
    expect(r.code, r.stdout + r.stderr).toBe(0);
    // biome-ignore lint/suspicious/noExplicitAny: each test reads the verb's data by the shape its contract gives
    return (r.json() as { data: Record<string, unknown> }).data as any;
  };
  const file = (name: string, text: string) => {
    mkdirSync(join(h, "in"), { recursive: true });
    writeFileSync(join(h, "in", name), text);
    return join(h, "in", name);
  };
  const hostYaml = (text: string) => {
    mkdirSync(join(h, "config", "athenaeum"), { recursive: true });
    writeFileSync(join(h, "config", "athenaeum", "host.yaml"), text);
  };
  let clock = WALL.getTime();
  const local: { handle: DaemonHandle | null } = { handle: null };
  const start = async () => {
    // the daemon's process environment: the host's bases, its own actor
    const h2 = await startDaemon({
      registry: buildRegistry({ local }),
      env: { ...process.env, ...env, ATH_ACTOR: "athd" },
      now: () => clock,
      wall: () => WALL,
      settleMs: 1,
    });
    local.handle = h2;
    return h2;
  };
  /** POST a verb to the socket as a client would. */
  const post = async (verb: string, body: Record<string, unknown>, headers: Record<string, string> = {}) => {
    const res = await fetch(`http://athd/v1/${verb}`, {
      unix: paths.socket,
      method: "POST",
      headers: { "ath-actor": "agent-b", ...headers },
      body: JSON.stringify(body),
    } as RequestInit);
    const text = await res.text();
    return { status: res.status, text, env: JSON.parse(text) };
  };
  return {
    h,
    env,
    root,
    paths,
    run,
    ok,
    file,
    hostYaml,
    start,
    post,
    /** The instance's history, as written so far. */
    history: () => readFileSync(join(h, "state", "athenaeum", "instances", instanceId(root)!, "history.jsonl"), "utf8"),
    tick: (ms: number) => {
      clock += ms;
    },
  };
}

describe("daemon configuration and schedule", () => {
  test("host.yaml's daemon section: instances, intervals, the look at the stores; anything else refused", async () => {
    const a = await host();
    const hp = hostPaths(a.env);
    expect(loadDaemonConfig(hp, a.env)).toEqual({ instances: [], every: {} });
    a.hostYaml("speech: {command: [true]}\ndaemon:\n  instances: [~/household]\n  every: {reconcile: 1h, verify: 30d}\n  poll: 5m\n");
    expect(loadDaemonConfig(hp, a.env)).toEqual({ instances: [a.root], every: { reconcile: 3600, verify: 2592000 }, poll: 300 });
    for (const bad of [
      "daemon: {instances: [relative/path]}\n",
      "daemon: {every: {sweep: 1h}}\n",
      "daemon: {every: {reconcile: hourly}}\n",
      "daemon: {schedule: 1h}\n",
    ]) {
      a.hostYaml(bad);
      expect(() => loadDaemonConfig(hp, a.env)).toThrow(/daemon/);
    }
  });

  test("a job runs at start when it never ran, then each interval; a failure backs off, doubling, never past it", () => {
    const t0 = WALL.getTime();
    expect(nextAt({ last_run: null, last_ok: null, failures: 0, retry_at: null, detail: null }, 3600_000, t0)).toBe(t0);
    expect(nextAt({ last_run: null, last_ok: null, failures: 0, retry_at: null, detail: null }, undefined, t0)).toBeNull();
    const ok = settle({ last_run: null, last_ok: null, failures: 0, retry_at: null, detail: null }, true, "done", t0, 3600_000);
    expect(nextAt(ok, 3600_000, t0)).toBe(t0 + 3600_000);
    const f1 = settle(ok, false, "remote down", t0, 3600_000);
    const f2 = settle(f1, false, "remote down", t0, 3600_000);
    expect([f1.failures, f1.retry_at, f2.retry_at]).toEqual([1, "2026-03-20T09:01:00Z", "2026-03-20T09:02:00Z"]);
    expect([backoffMs(1), backoffMs(4), backoffMs(30), backoffMs(30, 600_000)]).toEqual([60_000, 480_000, 6 * 3600_000, 600_000]);
    expect(settle(f2, true, "done", t0, 3600_000)).toMatchObject({ failures: 0, retry_at: null, last_ok: true });
  });
});

describe("the daemon's socket", () => {
  test("every verb over POST /v1/<verb>: the envelope --json prints, byte for byte, and §19.4.2's statuses", async () => {
    const a = await host();
    const d = await a.start();
    try {
      expect(readFileSync(a.paths.pid, "utf8").trim()).toBe(String(process.pid));
      const cli = await a.run(["store", "list"]);
      const sock = await a.post("store-list", { root: a.root });
      const zero = (s: string) => s.replace(/"elapsed_ms":\d+/, '"elapsed_ms":0');
      expect(sock.status).toBe(200);
      expect(zero(sock.text)).toBe(zero(cli.stdout));
      // a verdict is ok, with its exit code
      a.file("x.txt", "x\n");
      const ing = await a.post("ingest", { root: a.root, files: ["in/x.txt"] }, { "ath-cwd": a.h });
      expect(ing.status, ing.text).toBe(200);
      const st = await a.post("custody-status", { root: a.root });
      expect([st.status, st.env.ok, st.env.exit_code]).toEqual([200, true, 1]);
      // the actor is the request's, recorded in the history
      const log = a.history();
      expect(log).toContain('"actor":"agent-b"');
      const refusals: [string, Record<string, unknown>, Record<string, string>, number, string][] = [
        // an admin verb does not exist for an agent (§19.1.1)
        ["custody-remove", { root: a.root, hash: "ab", from: "nas" }, {}, 400, "USAGE"],
        ["store-list", { root: a.root, now: "2026-01-01T00:00:00Z" }, {}, 400, "USAGE"],
        ["ingest", { root: a.root, files: ["in/x.txt"] }, { "ath-actor": "" }, 403, "DENIED"],
        ["ingest", { root: a.root, files: ["in/x.txt"] }, { "ath-profile": "reader" }, 400, "USAGE"],
        ["serve", { root: a.root }, {}, 400, "USAGE"],
        ["daemon-run", {}, {}, 400, "USAGE"],
        ["record", { root: a.root, subject: "00000000" }, {}, 404, "NOT_FOUND"],
        ["no-such-verb", {}, {}, 400, "USAGE"],
        ["store-list", { root: "relative" }, {}, 400, "USAGE"],
      ];
      for (const [verb, body, headers, status, code] of refusals) {
        const r = await a.post(verb, body, headers);
        expect([verb, r.status, r.env.error?.code], r.text).toEqual([verb, status, code]);
      }
      // a denial at the gates is recorded as at the terminal; an argument error is not
      const denied = a
        .history()
        .trim()
        .split("\n")
        .map((l) => JSON.parse(l) as { cmd: string; error?: string })
        .filter((l) => l.error);
      expect(denied.map((l) => [l.cmd, l.error])).toEqual([
        ["ingest", "DENIED"],
        ["record", "NOT_FOUND"],
      ]);
      const get = await fetch(`http://athd/v1/store-list`, { unix: a.paths.socket } as RequestInit);
      expect(get.status).toBe(400);
    } finally {
      await d.stop();
    }
    expect(existsSync(a.paths.socket) || existsSync(a.paths.pid)).toBe(false);
  });

  test("verbs that write the index go to the daemon while it runs, run here when it does not, and fail closed", async () => {
    const a = await host();
    const fwd = forwarder(a.paths.socket, a.paths.pid);
    const f = a.file("note.txt", "a note\n");
    // no daemon: in-process, the history line carries the argv
    const here = await a.ok(["ingest", f], { forward: fwd });
    const d = await a.start();
    let there: Record<string, unknown>;
    try {
      const g = a.file("other.txt", "another note\n");
      there = await a.ok(["ingest", "../in/other.txt"], { forward: fwd });
      expect((there.results as { status: string; name: string }[])[0]).toMatchObject({ status: "new" });
      expect(existsSync(g)).toBe(true);
      // the same verb through the daemon and in-process answers alike
      const inv = await a.ok(["custody", "inventory"], { forward: fwd });
      expect(inv.stores.map((s: { store: string }) => s.store)).toEqual(["local"]);
      // a verb that only reads stays here, and --now keeps a verb here too
      expect((await a.run(["--now", "2026-03-20T09:00:00Z", "custody", "inventory"], { forward: fwd })).code).toBe(0);
    } finally {
      await d.stop();
    }
    expect((here.results as { status: string }[])[0]!.status).toBe("new");
    const hist = a.history().trim().split("\n");
    const ingests = hist.map((l) => JSON.parse(l)).filter((l: { cmd: string }) => l.cmd === "ingest");
    // the first ran here (argv as typed), the second in the daemon (its arguments as one object), once each
    expect(ingests.map((l: { argv: string[]; actor: string }) => [l.argv[0]!.startsWith("{"), l.actor])).toEqual([
      [false, "owner-a"],
      [true, "owner-a"],
    ]);
    // the daemon's process alive, its socket silent: nothing is written beside it
    writeFileSync(a.paths.pid, `${process.pid}\n`);
    writeFileSync(a.paths.socket, "");
    const busy = await a.run(["custody", "inventory"], { forward: fwd });
    expect(busy.code).toBe(75);
  });

  test("the daemon verbs: unavailable without a daemon; status, trigger and reload answered by it", async () => {
    const a = await host();
    expect((await a.run(["daemon", "status"])).code).toBe(69);
    a.hostYaml(`daemon:\n  instances: [${a.root}]\n`);
    const d = await a.start();
    try {
      const st = await a.ok(["daemon", "status"]);
      expect(st).toMatchObject({ pid: process.pid, instances: [a.root], poll: null, running: null });
      const tr = await a.ok(["daemon", "trigger", "inventory"]);
      expect(tr.queued).toEqual([{ kind: "inventory", root: a.root }]);
      await d.idle();
      // asked of the daemon, recorded once, by the daemon, with the asker's actor
      const hist = a.history();
      const triggers = hist
        .trim()
        .split("\n")
        .map((l) => JSON.parse(l))
        .filter((l: { cmd: string }) => l.cmd === "daemon-trigger");
      expect(triggers.map((l: { argv: string[]; actor: string }) => [l.argv, l.actor])).toEqual([[['{"job":"inventory"}'], "owner-a"]]);
      const after = await a.ok(["daemon", "status"]);
      expect(after.jobs).toEqual([
        expect.objectContaining({ kind: "inventory", root: a.root, last_ok: true, failures: 0, detail: "local 0 present, 0 missing" }),
      ]);
      a.hostYaml("daemon: {every: {sweep: 1h}}\n");
      const bad = await a.run(["daemon", "reload"]);
      expect(bad.code).toBe(78);
      const reloads = a
        .history()
        .trim()
        .split("\n")
        .filter((l) => l.includes('"cmd":"daemon-reload"'));
      expect(reloads.length).toBe(1);
      expect((await a.ok(["daemon", "status"])).reload_error).toContain("sweep");
      a.hostYaml(`daemon:\n  instances: [${a.root}]\n  every: {reconcile: 1h}\n`);
      expect((await a.ok(["daemon", "reload"])).every).toEqual({ reconcile: 3600 });
    } finally {
      await d.stop();
    }
    expect((await a.run(["daemon", "trigger", "reconcile"])).code).toBe(69);
  });
});

describe("custody kept by the daemon", () => {
  test("reconcile at start and after an ingest; a store come back is inventoried and reconciled", async () => {
    const a = await host();
    const f = a.file("note.txt", "kept off this host\n");
    const hash = (await a.ok(["ingest", f])).results[0].hash as string;
    await a.ok(["store", "add", "usb", "--path", join(a.h, "usb"), "--tag", "hdd"]);
    a.hostYaml(`daemon:\n  instances: [${a.root}]\n  every: {reconcile: 1h}\n  poll: 5m\n`);
    const d = await a.start();
    try {
      await d.idle();
      const at = (h: string) => join(a.h, "usb", "artifacts", h.slice(0, 2), h);
      expect(existsSync(at(hash))).toBe(true);
      // an ingest over the socket is reconciled once it settles
      a.file("late.txt", "came later\n");
      const late = await a.post("ingest", { root: a.root, files: [join(a.h, "in", "late.txt")] });
      const lateHash = late.env.data.results[0].hash as string;
      await Bun.sleep(5);
      await d.idle();
      expect(existsSync(at(lateHash))).toBe(true);
      // the disk unplugged: its mark gone, nothing reads as lost; plugged in again: inventoried and reconciled
      renameSync(join(a.h, "usb"), join(a.h, "usb-away"));
      a.tick(300_000);
      await d.tick();
      await d.idle();
      expect((await a.ok(["store", "list"])).stores.find((s: { name: string }) => s.name === "usb").reachable).toBe(false);
      expect((await a.run(["custody", "inventory", "usb"])).code).toBe(71);
      renameSync(join(a.h, "usb-away"), join(a.h, "usb"));
      a.tick(300_000);
      await d.tick();
      await d.idle();
      const st = d.status();
      expect(st.jobs.find((j) => j.kind === "inventory")).toMatchObject({ last_ok: true, detail: "usb 4 present, 0 missing" });
      expect(st.jobs.find((j) => j.kind === "reconcile")).toMatchObject({ last_ok: true, failures: 0 });
      expect(st.queue).toEqual([]);
    } finally {
      await d.stop();
    }
  });

  test("a failing transfer backs off, keeps its queue across a restart, and drains when the store answers", async () => {
    const a = await host();
    const f = a.file("note.txt", "for the remote\n");
    const hash = (await a.ok(["ingest", f])).results[0].hash as string;
    await a.ok(["store", "add", "offsite", "--driver", "rclone", "--remote", `fake:${join(a.h, "remote")}`, "--tag", "object"]);
    a.hostYaml(`daemon:\n  instances: [${a.root}]\n  every: {reconcile: 1h}\n`);
    process.env.FAKE_RCLONE_DOWN = "1";
    let d: DaemonHandle | null = null;
    try {
      d = await a.start();
      await d.idle();
      const st = d.status();
      expect(st.jobs[0]).toMatchObject({ kind: "reconcile", last_ok: false, failures: 1, retry_at: "2026-03-20T09:01:00Z" });
      expect(st.queue).toEqual([expect.objectContaining({ root: a.root, state: "pending" })]);
      expect(st.queue[0]!.actions.map((x) => x.hash)).toContain(hash);
      await d.stop();
      // a restart resumes the queue at once, and backs off further while the remote stays down
      d = await a.start();
      await d.idle();
      expect(d.status().jobs[0]).toMatchObject({ failures: 2, retry_at: "2026-03-20T09:02:00Z" });
      delete process.env.FAKE_RCLONE_DOWN;
      a.tick(120_000);
      await d.tick();
      await d.idle();
      expect(d.status().jobs[0]).toMatchObject({ last_ok: true, failures: 0 });
      expect(d.status().queue).toEqual([]);
      expect(existsSync(join(a.h, "remote", "artifacts", hash.slice(0, 2), hash))).toBe(true);
    } finally {
      delete process.env.FAKE_RCLONE_DOWN;
      await d?.stop();
    }
  });

  test("a second daemon on the host is refused", async () => {
    const a = await host();
    const d = await a.start();
    try {
      // a live process that is not this one holds the pid file
      const other = Bun.spawn(["sleep", "5"]);
      writeFileSync(a.paths.pid, `${other.pid}\n`);
      await expect(startDaemon({ registry: buildRegistry(), env: { ...process.env, ...a.env } })).rejects.toThrow(/already running/);
      other.kill();
      writeFileSync(a.paths.pid, `${process.pid}\n`);
    } finally {
      await d.stop();
    }
  });
});

describe("the service unit, bandwidth, availability", () => {
  test("daemon install and uninstall: the owner's, at a terminal; the unit runs ath daemon run", async () => {
    const a = await host();
    const calls: string[] = [];
    const registry = buildRegistry({
      systemctl: (args) => {
        calls.push(args.join(" "));
        return { ok: true, err: "" };
      },
    });
    const confirm = async () => "daemon install";
    // an agent does not see it; the owner confirms it
    expect((await a.run(["daemon", "install"], { registry })).code).toBe(64);
    const r = await ath(["daemon", "install"], { env: { ...a.env, ATH_BIN: "/opt/ath/bin/ath" }, tty: true, confirm, registry });
    expect(r.code, r.stderr).toBe(0);
    const unit = readFileSync(join(a.h, "config", "systemd", "user", "athd.service"), "utf8");
    expect(unit).toContain("ExecStart=/opt/ath/bin/ath daemon run\n");
    expect(unit).toContain("Environment=ATH_ACTOR=athd\n");
    expect(calls).toEqual(["daemon-reload", "enable --now athd.service"]);
    const u = await ath(["daemon", "uninstall"], { env: a.env, tty: true, confirm: async () => "daemon uninstall", registry });
    expect(u.code, u.stderr).toBe(0);
    expect(existsSync(join(a.h, "config", "systemd", "user", "athd.service"))).toBe(false);
    expect(calls.slice(2)).toEqual(["disable --now athd.service", "daemon-reload"]);
  });

  test("a store's bandwidth on this host, from the access file; a transfer held to it", async () => {
    const a = await host();
    const id = crypto.randomUUID();
    mkdirSync(join(a.h, "config", "athenaeum"), { recursive: true });
    writeFileSync(join(a.h, "config", "athenaeum", "access.yaml"), `${id}:\n  remote: "fake:/x"\n  bwlimit: 2MB/s\n`);
    expect(loadAccess(join(a.h, "config", "athenaeum")).stores.get(id)).toEqual({ remote: "fake:/x", bwlimit: 2e6 });
    writeFileSync(join(a.h, "config", "athenaeum", "access.yaml"), `${id}:\n  remote: "fake:/x"\n  bwlimit: fast\n`);
    expect(() => loadAccess(join(a.h, "config", "athenaeum"))).toThrow(/bwlimit/);
    const slept: number[] = [];
    await pace(4e6, performance.now(), 2e6, async (ms) => void slept.push(ms));
    expect(slept[0]).toBeGreaterThan(1900);
    await pace(4e6, performance.now(), undefined, async (ms) => void slept.push(ms));
    expect(slept.length).toBe(1);
  });

  test("an index another schema wrote: an older one is dropped and rebuilt, a newer one left to the tool that knows it", async () => {
    const a = await host();
    const path = join(a.h, "state", "athenaeum", "index.sqlite");
    const copy = { store: "s", tree: "artifacts", hash: "h", state: "claimed", size: 1, verified_at: null, generation: 1 } as const;
    const first = openIndex(path);
    first.putCopy(copy);
    first.close();
    const set = (v: string) => {
      const db = new Database(path);
      db.run("UPDATE meta SET value = ? WHERE key = 'schema'", [v]);
      db.close();
    };
    set("1");
    const rebuilt = openIndex(path);
    expect(rebuilt.copies("h")).toEqual([]);
    rebuilt.putCopy(copy);
    rebuilt.close();
    set("9");
    expect(() => openIndex(path)).toThrow(/schema 9/);
    expect((await a.run(["custody", "status"])).code).toBe(78);
    const kept = new Database(path);
    expect(kept.query("SELECT count(*) AS n FROM copies").get()).toEqual({ n: 1 });
    kept.close();
    // a reader drops an older one only under the index lock: busy while a writer holds it, rebuilt once it is free
    set("1");
    const lock = join(a.h, "state", "athenaeum", "locks", "index.lock");
    mkdirSync(dirname(lock), { recursive: true });
    writeFileSync(lock, JSON.stringify({ pid: process.ppid, until: new Date(Date.now() + 60_000).toISOString() }));
    expect((await a.run(["custody", "status"])).code).toBe(75);
    const held = new Database(path);
    expect(held.query("SELECT count(*) AS n FROM copies").get()).toEqual({ n: 1 });
    held.close();
    rmSync(lock);
    expect((await a.run(["custody", "status"])).code).not.toBe(75);
    expect(existsSync(lock)).toBe(false);
    const after = openIndex(path);
    expect(after.copies("h")).toEqual([]);
    after.putCopy(copy);
    after.close();
    // a verb that holds the index lock rebuilds under the lock it holds
    set("1");
    expect((await a.run(["custody", "inventory"])).code).not.toBe(75);
    const own = openIndex(path);
    expect(own.copies("h")).toEqual([]);
    own.close();
  });

  test("the request client: no socket is no daemon", async () => {
    const a = await host();
    await expect(request({ socket: a.paths.socket, verb: "whoami", body: {} })).rejects.toThrow(/no daemon socket/);
    expect(
      await forwarder(
        a.paths.socket,
        a.paths.pid,
      )({
        verb: "custody-inventory",
        args: {},
        root: a.root,
        cwd: a.root,
        caller: { profile: "agent", kind: "script", session: null, basis: [], actor: "x", tty: false },
      }),
    ).toBeNull();
  });
});
