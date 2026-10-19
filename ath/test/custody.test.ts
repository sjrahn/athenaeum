// custody.test.ts — custody in full (§18): stores declared and recognised by the id written into them; policies over
// labels, counting a constituent where its container is and a hardlinked copy once; status, plan and reconcile, which
// copies through the cheapest verified route and is a no-op when run again; eviction from the local store only when
// the policies hold without the copy; `custody remove`, the owner's; confinement refusing an ingest; an observed tree
// inventoried from the scanner's manifest, a file of it ingested by hardlink with the scanner's testimony kept; and a
// deleted index rebuilt by inventory, receipts and all.
import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { type CopyView, DEFAULT_POLICY, evaluate, holdsWithout, type Labels, parsePolicy, type StoreDecl } from "@ath/custody";
import { blake3Factory } from "@ath/scanner/hasher.ts";
import { Logger } from "@ath/scanner/log.ts";
import { scan } from "@ath/scanner/scanner.ts";
import { ath, type RunOpts, scratch } from "./harness.ts";

const FAKE_BIN = join(import.meta.dir, "fixtures", "bin");
const PATH = process.env.PATH;
beforeAll(() => {
  process.env.PATH = `${FAKE_BIN}:${PATH}`;
});
afterAll(() => {
  process.env.PATH = PATH;
});

/** A host of its own: a scratch home and XDG bases, an actor, and the instance under it. */
async function host() {
  const h = scratch("ath-host-");
  const env = {
    ATH_ACTOR: "owner-a",
    HOME: h,
    XDG_DATA_HOME: join(h, "data"),
    XDG_STATE_HOME: join(h, "state"),
    XDG_CONFIG_HOME: join(h, "config"),
    XDG_CACHE_HOME: join(h, "cache"),
  };
  const root = join(h, "household");
  expect((await ath(["instance", "init", root], { env })).code).toBe(0);
  const run = async (argv: string[], o: RunOpts = {}) => ath(["--json", ...argv], { env, cwd: root, ...o });
  const ok = async (argv: string[], o: RunOpts = {}) => {
    const r = await run(argv, o);
    expect(r.code, r.stdout + r.stderr).toBe(0);
    // biome-ignore lint/suspicious/noExplicitAny: each test reads the verb's data by the shape its contract gives
    return (r.json() as { data: Record<string, unknown> }).data as any;
  };
  const file = (name: string, text: string) => {
    const p = join(h, "in", name);
    mkdirSync(join(h, "in"), { recursive: true });
    writeFileSync(p, text);
    return p;
  };
  return { h, env, root, run, ok, file };
}

const decl = (name: string, tags: string[], role: "managed" | "observed" = "managed"): StoreDecl => ({
  name,
  id: crypto.randomUUID(),
  driver: "local",
  role,
  tags,
  encryption: "none",
  cost: 1,
});
const copy = (store: StoreDecl, o: Partial<CopyView> = {}): CopyView => ({
  store,
  state: "verified",
  verified_at: "2026-03-01T00:00:00Z",
  via: "direct",
  physical: `${store.id}:h`,
  held: "h",
  tree: "artifacts",
  ...o,
});
const labels: Labels = { shapes: ["statement"], origins: ["page-capture"], kinds: [], mime: "application/pdf", size: 10, testimony: false };
const now = new Date("2026-03-20T09:00:00Z");

describe("policies", () => {
  const local = decl("local", ["local"]);
  const nasW = decl("nas", ["hdd", "city:winnipeg"]);
  const offT = decl("offsite", ["object", "city:toronto"]);
  const tree = decl("photos", [], "observed");
  const two = parsePolicy(
    "two-cities",
    "select: {shape: statement}\nrequire:\n  - copies: 2\n    where: {not: [local]}\n    distinct: city\nverify: 30d\n",
    "two-cities.yaml",
  );

  test("the default policy: a copy only on the local store or an observed tree is unpersisted", () => {
    const f = evaluate("h", labels, [copy(local), copy(tree)], [DEFAULT_POLICY], now);
    expect(f.map((x) => x.kind)).toEqual(["unpersisted"]);
    expect(evaluate("h", labels, [copy(local), copy(nasW)], [DEFAULT_POLICY], now)).toEqual([]);
  });

  test("a constituent is held where its container is; one physical copy counts once; distinct values of a key", () => {
    const viaContainer = copy(nasW, { via: "container", physical: `${nasW.id}:container`, held: "container" });
    expect(evaluate("h", labels, [viaContainer], [DEFAULT_POLICY], now)).toEqual([]);
    // the artifact and its container on one store are two physical copies, but in one city
    const both = [copy(nasW, { physical: `${nasW.id}:h` }), viaContainer];
    expect(evaluate("h", labels, both, [two], now).map((x) => x.kind)).toEqual(["below"]);
    expect(evaluate("h", labels, [copy(nasW), copy(offT, { physical: `${offT.id}:h` })], [two], now)).toEqual([]);
    // a hardlinked local copy shares the observed file's storage: one physical copy
    const linked = copy(local, { via: "linked", physical: `${tree.id}:a.pdf` });
    const p1 = parsePolicy("any-two", "require: {copies: 2}\n", "any-two.yaml");
    expect(
      evaluate("h", labels, [linked, copy(local, { via: "linked", physical: `${tree.id}:a.pdf` })], [p1], now).map((x) => x.kind),
    ).toEqual(["below"]);
  });

  test("verification recency, confinement, and holding without a copy", () => {
    const stale = copy(offT, { physical: `${offT.id}:h`, verified_at: "2026-01-01T00:00:00Z" });
    const f = evaluate("h", labels, [copy(nasW), stale], [two], now);
    expect(f.map((x) => x.kind).sort()).toEqual(["below", "overdue"]);
    const ca = parsePolicy("ca", 'select: {origin: page-capture}\nconfine: {all: ["country:ca"]}\n', "ca.yaml");
    expect(evaluate("h", labels, [copy(nasW)], [ca], now).map((x) => x.kind)).toEqual(["outside"]);
    const fresh = [copy(local, { physical: `${local.id}:h` }), copy(nasW), copy(offT, { physical: `${offT.id}:h` })];
    expect(holdsWithout(labels, fresh, (c) => c.store === local, [DEFAULT_POLICY, two], now)).toBe(true);
    expect(holdsWithout(labels, fresh, (c) => c.store === nasW, [DEFAULT_POLICY, two], now)).toBe(false);
  });
});

describe("custody", () => {
  test("store add writes the id into the store; a second declaration of it adopts the id", async () => {
    const a = await host();
    const nas = join(a.h, "nas");
    const d = await a.ok(["store", "add", "nas", "--path", nas, "--tag", "hdd", "--tag", "city:winnipeg"]);
    expect(d.adopted).toBe(false);
    expect(readFileSync(join(nas, "store.yaml"), "utf8")).toContain(`id: ${d.id}`);
    expect(readFileSync(join(a.root, "stores", "nas.yaml"), "utf8")).toBe(
      `id: ${d.id}\ndriver: local\nrole: managed\ntags: ["hdd", "city:winnipeg"]\nencryption: none\n`,
    );
    expect(readFileSync(join(a.h, "config", "athenaeum", "access.yaml"), "utf8")).toContain(`${d.id}:\n  path: ${JSON.stringify(nas)}`);
    const b = await host();
    const again = await b.ok(["store", "add", "media", "--path", nas]);
    expect(again).toMatchObject({ adopted: true, id: d.id });
    expect((await a.run(["store", "add", "nas", "--path", join(a.h, "other")])).code).toBe(73);
    const list = await a.ok(["store", "list"]);
    expect(list.stores.map((s: { name: string; reachable: boolean }) => [s.name, s.reachable])).toEqual([
      ["local", true],
      ["nas", true],
    ]);
  });

  test("status, plan, reconcile: copies to the stores the policies need, then nothing to do", async () => {
    const a = await host();
    const f = a.file("note.txt", "a note kept in two cities\n");
    const ing = await a.ok(["ingest", f]);
    const hash = ing.results[0].hash as string;
    const receipt = ing.results[0].receipt as string;
    // only the local store: the artifact and its receipt are unpersisted, a verdict
    const st = await a.run(["custody", "status"]);
    expect(st.code).toBe(1);
    const findings = (st.json() as { data: { findings: { kind: string; hash: string }[] } }).data.findings;
    expect(findings.map((x) => [x.kind, x.hash]).sort()).toEqual(
      [
        ["unpersisted", hash],
        ["unpersisted", receipt],
      ].sort(),
    );
    await a.ok(["store", "add", "nas", "--path", join(a.h, "nas"), "--tag", "hdd", "--tag", "city:winnipeg", "--cost", "1"]);
    await a.ok([
      "store",
      "add",
      "offsite",
      "--driver",
      "rclone",
      "--remote",
      `fake:${join(a.h, "remote")}`,
      "--tag",
      "object",
      "--tag",
      "city:toronto",
      "--cost",
      "5",
    ]);
    expect(existsSync(join(a.h, "remote", "store.yaml"))).toBe(true);
    // the default policy needs one copy off the local store: the cheaper store takes it
    let plan = await a.ok(["custody", "plan"]);
    expect(plan.actions.map((x: { op: string; hash: string; store: string }) => [x.op, x.hash, x.store]).sort()).toEqual(
      [
        ["copy", hash, "nas"],
        ["copy", receipt, "nas"],
      ].sort(),
    );
    // an owner's policy: two copies off the local store, in distinct cities
    writeFileSync(
      join(a.root, "policies", "two-cities.yaml"),
      "select: {mime: text/plain}\nrequire:\n  - copies: 2\n    where: {not: [local]}\n    distinct: city\n",
    );
    plan = await a.ok(["custody", "plan"]);
    expect(plan.actions.filter((x: { hash: string }) => x.hash === hash).map((x: { store: string }) => x.store)).toEqual([
      "nas",
      "offsite",
    ]);
    const rec = await a.ok(["custody", "reconcile"]);
    expect(rec.failed).toEqual([]);
    expect(rec.done.length).toBe(3);
    expect(existsSync(join(a.h, "nas", "artifacts", hash.slice(0, 2), hash))).toBe(true);
    expect(existsSync(join(a.h, "remote", "artifacts", hash.slice(0, 2), hash))).toBe(true);
    expect((await a.ok(["custody", "reconcile"])).done).toEqual([]);
    expect((await a.run(["custody", "status"])).code).toBe(0);
    const where = await a.ok(["custody", "where", hash.slice(0, 12)]);
    expect(where.copies.map((c: { store: string; state: string }) => `${c.store} ${c.state}`).sort()).toEqual([
      "local verified",
      "nas verified",
      "offsite verified",
    ]);
    // an unreachable store is skipped, and its copies still count as the index believes them
    process.env.FAKE_RCLONE_DOWN = "1";
    try {
      expect((await a.run(["custody", "status"])).code).toBe(0);
      expect((await a.run(["custody", "inventory", "offsite"])).code).toBe(71);
    } finally {
      delete process.env.FAKE_RCLONE_DOWN;
    }
  });

  test("eviction sheds local copies only where the policies hold without them, the others re-hashed then", async () => {
    const a = await host();
    const kept = a.file("kept.txt", "persisted elsewhere\n");
    const lone = a.file("lone.txt", "held only here\n");
    await a.ok(["ingest", kept]);
    const lh = (await a.ok(["ingest", lone])).results[0].hash as string;
    await a.ok(["store", "add", "nas", "--path", join(a.h, "nas"), "--tag", "hdd"]);
    await a.ok(["custody", "reconcile"]);
    // a copy now lost from nas: its local copy must stay
    rmSync(join(a.h, "nas", "artifacts", lh.slice(0, 2), lh));
    writeFileSync(
      join(a.h, "config", "athenaeum", "access.yaml"),
      `${readFileSync(join(a.h, "config", "athenaeum", "access.yaml"), "utf8")}local:\n  evict: {above: 0%}\n  capacity: 1MB\n`,
    );
    const run = await a.run(["custody", "reconcile"]);
    expect(run.code).toBe(1); // a failed action is a verdict
    const rec = (run.json() as { data: { done: { op: string; hash: string }[]; failed: { op: string; hash: string; error: string }[] } })
      .data;
    const evicted = rec.done.filter((x: { op: string }) => x.op === "evict").map((x: { hash: string }) => x.hash);
    const failed = rec.failed.filter((x: { op: string }) => x.op === "evict");
    expect(failed.map((x: { hash: string }) => x.hash)).toEqual([lh]);
    expect(failed[0]!.error).toContain("would not hold");
    expect(existsSync(join(a.h, "data", "athenaeum", "artifacts", lh.slice(0, 2), lh))).toBe(true);
    for (const e of evicted) expect(existsSync(join(a.h, "data", "athenaeum", "artifacts", e.slice(0, 2), e))).toBe(false);
    expect(evicted.length).toBeGreaterThan(0);
  });

  test("custody remove is the owner's, one copy, refused unless the policies hold without it", async () => {
    const a = await host();
    const h = (await a.ok(["ingest", a.file("x.txt", "one copy away\n")])).results[0].hash as string;
    await a.ok(["store", "add", "nas", "--path", join(a.h, "nas"), "--tag", "hdd"]);
    await a.ok(["custody", "reconcile"]);
    const owner = { env: a.env, cwd: a.root, tty: true, confirm: async () => "custody remove" };
    expect((await ath(["custody", "remove", h, "--from", "nas"], { env: a.env, cwd: a.root })).code).toBe(64);
    const refused = await ath(["custody", "remove", h, "--from", "nas"], owner);
    expect(refused.code).toBe(73);
    expect(refused.stdout + refused.stderr).toContain("would not hold");
    await a.ok(["store", "add", "usb", "--path", join(a.h, "usb"), "--tag", "ssd"]);
    writeFileSync(join(a.root, "policies", "two.yaml"), "require: {copies: 2, where: {not: [local]}}\n");
    await a.ok(["custody", "reconcile"]);
    rmSync(join(a.root, "policies", "two.yaml"));
    const r = await ath(["custody", "remove", h, "--from", "nas"], owner);
    expect(r.code, r.stderr).toBe(0);
    expect(existsSync(join(a.h, "nas", "artifacts", h.slice(0, 2), h))).toBe(false);
    expect(existsSync(join(a.h, "usb", "artifacts", h.slice(0, 2), h))).toBe(true);
  });

  test("ingest refuses an artifact a policy confines to stores the local one is not", async () => {
    const a = await host();
    writeFileSync(join(a.root, "policies", "canada.yaml"), 'select: {mime: text/plain}\nconfine: {all: ["country:ca"]}\n');
    const r = await a.run(["ingest", a.file("secret.txt", "kept in one country\n")]);
    expect(r.code).toBe(73);
    expect(r.stdout).toContain("policy canada confines it");
    mkdirSync(join(a.h, "config", "athenaeum"), { recursive: true });
    writeFileSync(join(a.h, "config", "athenaeum", "access.yaml"), 'local:\n  tags: ["country:ca"]\n');
    expect((await a.run(["ingest", a.file("secret.txt", "kept in one country\n")])).code).toBe(0);
  });

  test("an observed tree: inventoried from the scanner's manifest; a file of it ingested by hardlink with the scanner's testimony", async () => {
    const a = await host();
    const tree = join(a.h, "photos");
    mkdirSync(join(tree, "2026"), { recursive: true });
    writeFileSync(join(tree, "2026", "trip.txt"), "a day by the lake\n");
    writeFileSync(join(tree, "2026", "other.txt"), "not yet ingested\n");
    await scan({ root: tree, manifestDir: join(tree, ".athenaeum"), factory: blake3Factory, log: new Logger("quiet"), concurrency: 2 });
    await a.ok(["store", "add", "photos", "--role", "observed", "--path", tree, "--link", "hardlink"]);
    expect(existsSync(join(tree, ".athenaeum", "store.yaml"))).toBe(true);
    const inv = await a.ok(["custody", "inventory", "photos"]);
    expect(inv.stores[0]).toMatchObject({ store: "photos", present: 2, missing: 0 });
    const ing = await a.ok(["ingest", join(tree, "2026", "trip.txt")]);
    const r = ing.results[0];
    expect(r.placed).toBe("hardlink");
    expect(r.testimony.map((t: { name: string }) => t.name)).toEqual(["ath-scan 2026/trip.txt"]);
    expect(statSync(join(a.h, "data", "athenaeum", "artifacts", r.hash.slice(0, 2), r.hash)).ino).toBe(
      statSync(join(tree, "2026", "trip.txt")).ino,
    );
    const scanned = readFileSync(join(a.h, "data", "athenaeum", "testimony", r.testimony[0].hash.slice(0, 2), r.testimony[0].hash), "utf8");
    expect(scanned).toContain(`subject: b3:${r.hash}`);
    expect(scanned).toContain("  tool: ath-scan");
    expect(scanned).toContain(`  path: ${JSON.stringify(join(tree, "2026", "trip.txt"))}`);
    const where = await a.ok(["custody", "where", r.hash]);
    expect(where.copies.find((c: { store: string }) => c.store === "local").via).toBe("linked");
    expect(where.observed).toEqual([{ store: "photos", path: "2026/trip.txt", link: expect.stringContaining("hardlink") }]);
    const report = await a.ok(["custody", "report", "photos"]);
    expect(report.at_risk.map((x: { path: string }) => x.path)).toEqual([]);
    expect(report.also.map((x: { path: string }) => x.path)).toEqual(["2026/trip.txt"]);
    expect(report.candidates.map((x: { path: string }) => x.path)).toEqual(["2026/other.txt"]);
    // the hardlinked copy is unpersisted until an independent copy is made
    const st = (await a.run(["custody", "status"])).json() as { data: { findings: { kind: string; hash: string }[] } };
    expect(st.data.findings.some((x) => x.kind === "unpersisted" && x.hash === r.hash)).toBe(true);
  });

  test("a deleted index is rebuilt by inventory, receipts and all", async () => {
    const a = await host();
    const ing = await a.ok(["ingest", a.file("y.txt", "receipts live in the stores\n")]);
    rmSync(join(a.h, "state", "athenaeum", "index.sqlite"), { force: true });
    rmSync(join(a.h, "state", "athenaeum", "index.sqlite-wal"), { force: true });
    rmSync(join(a.h, "state", "athenaeum", "index.sqlite-shm"), { force: true });
    const inv = await a.ok(["custody", "inventory", "local"]);
    expect(inv.stores[0]).toMatchObject({ store: "local", present: 2, receipts: 1 });
    const st = (await a.run(["custody", "status"])).json() as { data: { findings: { hash: string }[] } };
    expect(st.data.findings.map((x) => x.hash).sort()).toEqual([ing.results[0].hash, ing.results[0].receipt].sort());
  });
});
