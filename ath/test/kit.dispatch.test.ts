// kit.dispatch.test.ts — runCli end to end over a small fake registry: envelope, verdicts, usage, gates, help, schema.
import { describe, expect, test } from "bun:test";
import { existsSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { defineContract, z } from "@ath/contracts";
import { defineCommand } from "@ath/kit/define.ts";
import { AthError } from "@ath/kit/errors.ts";
import { readHistory } from "@ath/kit/history.ts";
import { createRegistry } from "@ath/kit/registry.ts";
import { hostPaths, instanceState } from "@ath/kit/xdg.ts";
import { ath, scratch } from "./harness.ts";

function fakeRegistry() {
  const r = createRegistry();
  r.registerGroup("greet", "greetings");
  r.register(
    defineCommand({
      meta: { summary: "greet someone", tier: "read", mutating: false, examples: ["ath greet bob"] },
      contract: defineContract({
        key: "greet",
        args: z.object({ name: z.string(), loud: z.boolean().default(false) }),
        argv: { positionals: [{ name: "name", required: true }], flags: { loud: { type: "boolean", short: "l" } } },
        data: z.object({ msg: z.string() }),
      }),
      run: (ctx, a) => {
        ctx.events.emit({ kind: "x", level: "warn", msg: "careful" });
        return { data: { msg: `hi ${a.loud ? a.name.toUpperCase() : a.name}` } };
      },
      text: (d, io) => io.out(`${d.msg}\n`),
    }),
  );
  r.register(
    defineCommand({
      meta: { summary: "a verdict", tier: "read", mutating: false },
      contract: defineContract({ key: "greet-check", args: z.object({}), argv: {}, data: z.object({ ok: z.boolean() }) }),
      run: () => ({ data: { ok: false }, exitCode: 1 }),
    }),
  );
  r.register(
    defineCommand({
      meta: { summary: "writes", tier: "write", mutating: true, locks: ["repository"] },
      contract: defineContract({ key: "greet-write", args: z.object({}), argv: {}, data: z.object({ wrote: z.boolean() }) }),
      run: () => ({ data: { wrote: true } }),
    }),
  );
  r.register(
    defineCommand({
      meta: { summary: "owner only", tier: "admin", mutating: true },
      contract: defineContract({ key: "greet-admin", args: z.object({}), argv: {}, data: z.object({ done: z.boolean() }) }),
      run: () => ({ data: { done: true } }),
    }),
  );
  r.register(
    defineCommand({
      meta: { summary: "throws", tier: "read", mutating: false },
      contract: defineContract({
        key: "greet-boom",
        args: z.object({ code: z.string().optional() }),
        argv: { flags: { code: { type: "string" } } },
        data: z.object({}),
      }),
      run: (_c, a) => {
        if (a.code === "nf") throw new AthError("NOT_FOUND", "no such thing");
        throw new Error("kaboom");
      },
    }),
  );
  return r;
}

const reg = fakeRegistry();

describe("dispatch", () => {
  test("text output, then --json envelope", async () => {
    const t = await ath(["greet", "bob"], { registry: reg });
    expect(t.code).toBe(0);
    expect(t.stdout).toBe("hi bob\n");
    expect(t.stderr).toBe("warn: careful\n");
    const j = await ath(["--json", "greet", "bob", "--loud"], { registry: reg });
    expect(j.code).toBe(0);
    const env = j.json() as { ok: boolean; cmd: string; data: { msg: string }; version: string };
    expect(env.ok).toBe(true);
    expect(env.cmd).toBe("greet");
    expect(env.data.msg).toBe("hi BOB");
    expect(j.stderr).toBe("");
  });

  test("a verdict is an ok envelope with exit_code 1", async () => {
    const r = await ath(["--json", "greet", "check"], { registry: reg });
    expect(r.code).toBe(1);
    expect(r.json()).toMatchObject({ ok: true, exit_code: 1, data: { ok: false } });
  });

  test("usage errors are 64 with the usage text", async () => {
    const r = await ath(["greet"], { registry: reg });
    expect(r.code).toBe(64);
    expect(r.stderr).toContain("missing required argument: name");
    expect(r.stderr).toContain("usage: ath greet <name>");
    const u = await ath(["greet", "bob", "--nope"], { registry: reg });
    expect(u.code).toBe(64);
    const j = await ath(["--json", "greet"], { registry: reg });
    expect(j.json()).toMatchObject({ ok: false, error: { code: "USAGE" } });
  });

  test("errors map to their codes; an unexpected throw is 70", async () => {
    expect((await ath(["greet", "boom", "--code", "nf"], { registry: reg })).code).toBe(66);
    const r = await ath(["--json", "greet", "boom"], { registry: reg });
    expect(r.code).toBe(70);
    expect(r.json()).toMatchObject({ ok: false, error: { code: "INTERNAL" } });
    expect((await ath(["nothing", "here"], { registry: reg })).code).toBe(64);
  });

  test("profiles: owner at a terminal, agent under Claude, reader by env; narrow-only", async () => {
    const owner = await ath(["--json", "whoami"], { tty: true });
    expect((owner.json() as { data: { profile: string } }).data.profile).toBe("owner");
    const session = { id: "s1", pid: 1, name: "arbre" };
    const agent = await ath(["--json", "whoami"], { tty: true, session });
    expect((agent.json() as { data: { profile: string; basis: string[] } }).data.profile).toBe("agent");
    const script = await ath(["--json", "whoami"]);
    expect((script.json() as { data: { profile: string } }).data.profile).toBe("agent");
    const reader = await ath(["--json", "whoami"], { tty: true, env: { ATH_PROFILE: "reader" } });
    expect((reader.json() as { data: { profile: string } }).data.profile).toBe("reader");
    const widen = await ath(["--json", "--profile", "owner", "whoami"], { session });
    expect((widen.json() as { data: { profile: string } }).data.profile).toBe("agent");
  });

  test("gates: admin is hidden from agents and refused without a terminal; write needs an actor off-terminal", async () => {
    const hidden = await ath(["greet", "admin"], { registry: reg });
    expect(hidden.code).toBe(64);
    expect(hidden.stderr).toContain("unknown command 'greet admin'");
    const reader = await ath(["greet", "write"], { registry: reg, env: { ATH_PROFILE: "reader" } });
    expect(reader.code).toBe(64);
    const noActor = await ath(["greet", "write"], { registry: reg, env: { USER: undefined, ATH_ACTOR: undefined } });
    expect(noActor.code).toBe(77);
    expect(noActor.stderr).toContain("ATH_ACTOR");
    const ownerNoTty = await ath(["greet", "admin"], { registry: reg, tty: true, confirm: undefined });
    expect(ownerNoTty.code).toBe(77);
    const confirmed = await ath(["greet", "admin"], { registry: reg, tty: true, confirm: async () => "greet admin" });
    expect(confirmed.code).toBe(0);
    const refused = await ath(["greet", "admin"], { registry: reg, tty: true, confirm: async () => "no" });
    expect(refused.code).toBe(77);
    const underJson = await ath(["--json", "greet", "admin"], { registry: reg, tty: true, confirm: async () => "greet admin" });
    expect(underJson.code).toBe(77);
  });

  test("locks need an instance; a write takes and releases its lock in host state, and history records it there", async () => {
    const noRoot = await ath(["greet", "write"], { registry: reg, env: { ATH_ACTOR: "t" }, cwd: scratch() });
    expect(noRoot.code).toBe(78);
    const root = scratch();
    writeFileSync(join(root, "athenaeum.yaml"), "name: t\n");
    expect((await ath(["greet", "write"], { registry: reg, env: { ATH_ACTOR: "t" }, cwd: root })).code).toBe(78); // no id
    const id = "0f4c2a8e-7b1d-4e5a-9c3f-6d2e8b1a4c70";
    writeFileSync(join(root, "athenaeum.yaml"), `id: ${id}\nname: t\n`);
    const ok = await ath(["greet", "write"], { registry: reg, env: { ATH_ACTOR: "t" }, cwd: root });
    expect(ok.code).toBe(0);
    const again = await ath(["greet", "write"], { registry: reg, env: { ATH_ACTOR: "t" }, cwd: root });
    expect(again.code).toBe(0);
    const state = instanceState(hostPaths(process.env), id);
    expect(existsSync(join(root, ".ath"))).toBe(false);
    const h = readHistory(state);
    expect(h.length).toBe(2);
    expect(h[0]).toMatchObject({ cmd: "greet-write", exit: 0, actor: "t", profile: "agent" });
  });

  test("help and --schema", async () => {
    const top = await ath(["help"], { registry: reg });
    expect(top.code).toBe(0);
    expect(top.stdout).toContain("greet");
    const grp = await ath(["help", "greet"], { registry: reg, tty: true });
    expect(grp.stdout).toContain("usage: ath greet <name>");
    const cmd = await ath(["greet", "check", "--help"], { registry: reg });
    expect(cmd.stdout).toContain("usage: ath greet check");
    const schema = await ath(["greet", "--schema"], { registry: reg });
    expect(JSON.parse(schema.stdout)).toMatchObject({ key: "greet" });
    const none = await ath([], { registry: reg });
    expect(none.code).toBe(64);
  });

  test("--now fixes the clock", async () => {
    const r = await ath(["--json", "--now", "2026-10-13T00:00:00Z", "whoami"]);
    expect((r.json() as { data: { now: string } }).data.now).toBe("2026-10-13T00:00:00Z");
    expect((await ath(["--now", "nope", "whoami"])).code).toBe(64);
  });
});
