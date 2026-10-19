// instance.ts — `ath instance init|show|check|repin|reshard` (spec §19.5, §4).
import { existsSync, mkdirSync, readdirSync, readFileSync } from "node:fs";
import { basename, join, relative, resolve } from "node:path";
import { defineContract, z } from "@ath/contracts";
import { formatOf, intrinsicsOp, parseIntrinsicsOp } from "@ath/engine/formats/index.ts";
import { emitConfig, type InstanceConfig, parseConfig } from "@ath/engine/instance/config.ts";
import { chain, headCommit, type Instance, openInstance, ownRecord, ownRecords, recordPath } from "@ath/engine/instance/instance.ts";
import { serializeTerm } from "@ath/engine/vocab/terms.ts";
import { defineCommand } from "@ath/kit/define.ts";
import { AthError } from "@ath/kit/errors.ts";
import { writeAtomic } from "@ath/kit/fs.ts";
import { commitJournal, type JournalWrite } from "@ath/kit/journal.ts";
import { CONFIG_FILE } from "@ath/kit/root.ts";
import { instanceState } from "@ath/kit/xdg.ts";
import { instanceOf } from "./context.ts";

const DIRS = ["corpus/forms", "corpus/shapes", "corpus/records", "graph/kinds", "graph/properties", "graph/entities", "stores", "policies"];

const chainRow = z.object({ name: z.string(), id: z.string(), root: z.string(), commit: z.string().nullable() });
const chainOf = (i: Instance) => chain(i).map((x) => ({ name: x.config.name, id: x.config.id, root: x.root, commit: x.commit ?? null }));

// ── init ────────────────────────────────────────────────────────────────────────────────────────────────────────────

export const instanceInit = defineCommand({
  meta: {
    summary: "write athenaeum.yaml and the empty directories: a standalone instance, or an extension pinned to its base's commit",
    tier: "write",
    mutating: true,
    examples: ["ath instance init ~/instances/reference", "ath instance init ~/instances/household --extends ../reference"],
  },
  contract: defineContract({
    key: "instance-init",
    args: z.object({ dir: z.string().default("."), extends: z.string().optional(), name: z.string().optional() }),
    argv: {
      positionals: [{ name: "dir", help: "where (default: the working directory)" }],
      flags: {
        extends: { type: "string", metavar: "PATH", help: "the base, a git repository holding an instance; pinned at its HEAD" },
        name: { type: "string", help: "the instance's name (default: the directory's)" },
      },
    },
    data: z.object({ root: z.string(), config: z.string(), chain: z.array(chainRow) }),
  }),
  run(ctx, a) {
    const root = resolve(ctx.cwd, a.dir);
    if (existsSync(join(root, CONFIG_FILE))) throw new AthError("CONFLICT", `${root} already holds an instance`);
    const name = (a.name ?? basename(root))
      .toLowerCase()
      .replace(/[^a-z0-9-]+/g, "-")
      .replace(/^-+|-+$/g, "");
    if (!/^[a-z0-9][a-z0-9-]*$/.test(name))
      throw new AthError("USAGE", `cannot name an instance from '${a.name ?? basename(root)}'; pass --name`);
    const cfg: InstanceConfig = { id: crypto.randomUUID(), name, shard: { records: 2, entities: 2 } };
    if (a.extends) {
      const base = resolve(ctx.cwd, a.extends);
      if (!existsSync(join(base, CONFIG_FILE))) throw new AthError("CONFIG", `${base} holds no instance`);
      cfg.extends = { path: relative(root, base) || ".", commit: headCommit(base) };
    }
    for (const d of DIRS) mkdirSync(join(root, d), { recursive: true });
    writeAtomic(join(root, CONFIG_FILE), emitConfig(cfg));
    // a standalone instance carries the one property the tooling relies on (§11.9)
    if (!cfg.extends)
      writeAtomic(
        join(root, "graph/properties/source.jsonl"),
        serializeTerm([
          { pred: "range", val: "artifact" },
          { pred: "authority", val: true },
          { pred: "definition", val: "an artifact that is an authoritative source for the entity that carries it" },
        ]),
      );
    const inst = openInstance(root, ctx.host);
    return { data: { root, config: join(root, CONFIG_FILE), chain: chainOf(inst) } };
  },
  text(d, io) {
    io.out(`wrote ${d.config}\n`);
    for (const c of d.chain.slice(1)) io.out(`extends ${c.name} (${c.id}) at ${c.commit}\n`);
  },
});

// ── show ────────────────────────────────────────────────────────────────────────────────────────────────────────────

export const instanceShow = defineCommand({
  meta: { summary: "the instance and what it builds on", tier: "read", mutating: false },
  contract: defineContract({
    key: "instance-show",
    args: z.object({}),
    argv: {},
    data: z.object({
      chain: z.array(chainRow.extend({ records: z.number(), shard: z.object({ records: z.number(), entities: z.number() }) })),
      state: z.string(),
    }),
  }),
  run(ctx) {
    const inst = instanceOf(ctx);
    return {
      data: {
        chain: chain(inst).map((x) => ({
          name: x.config.name,
          id: x.config.id,
          root: x.root,
          commit: x.commit ?? null,
          records: ownRecords(x).length,
          shard: x.config.shard,
        })),
        state: instanceState(ctx.host, inst.config.id),
      },
    };
  },
  text(d, io) {
    for (const [i, c] of d.chain.entries())
      io.out(
        `${i ? "  extends " : ""}${c.name}  ${c.id}  ${c.records} records${c.commit ? `  @${c.commit.slice(0, 12)}` : ""}  ${c.root}\n`,
      );
    io.out(`state ${d.state}\n`);
  },
});

// ── check ───────────────────────────────────────────────────────────────────────────────────────────────────────────

const finding = z.object({ instance: z.string(), what: z.string(), detail: z.string() });

export const instanceCheck = defineCommand({
  meta: {
    summary: "verify the chain, its pins, its configuration, and that this tool can serve it",
    tier: "read",
    mutating: false,
    help: "A record whose intrinsics were written by an op newer than this tool's, or by an op it does not register, is a configuration error (§19.2.2).",
  },
  contract: defineContract({
    key: "instance-check",
    args: z.object({}),
    argv: {},
    data: z.object({ chain: z.array(chainRow), findings: z.array(finding) }),
  }),
  run(ctx) {
    const inst = instanceOf(ctx);
    const findings: z.input<typeof finding>[] = [];
    for (const x of chain(inst))
      for (const h of ownRecords(x)) {
        let r: ReturnType<typeof ownRecord>;
        try {
          r = ownRecord(x, h);
        } catch (e) {
          findings.push({ instance: x.config.name, what: "record", detail: (e as Error).message });
          continue;
        }
        if (!r?.intrinsics) continue;
        const have = parseIntrinsicsOp(r.intrinsics.op);
        const tool = parseIntrinsicsOp(intrinsicsOp(formatOf(String(r.intrinsics.mime))))!;
        if (!have) findings.push({ instance: x.config.name, what: "intrinsics", detail: `${h}: \`op\` is not an intrinsics op` });
        else if (have.name !== tool.name && have.name !== "bytes")
          findings.push({
            instance: x.config.name,
            what: "intrinsics",
            detail: `${h}: written by ${r.intrinsics.op}, which this tool does not register for ${r.intrinsics.mime}`,
          });
        else if (have.name === tool.name && have.version > tool.version)
          findings.push({
            instance: x.config.name,
            what: "intrinsics",
            detail: `${h}: written by ${r.intrinsics.op}, newer than this tool's ${tool.name}.intrinsics@${tool.version}`,
          });
      }
    if (findings.some((f) => f.what === "intrinsics"))
      throw new AthError("CONFIG", `this tool cannot serve the chain:\n${findings.map((f) => `  ${f.instance}: ${f.detail}`).join("\n")}`, {
        findings,
      });
    return { data: { chain: chainOf(inst), findings }, exitCode: findings.length ? 1 : 0 };
  },
  text(d, io) {
    for (const c of d.chain) io.out(`ok  ${c.name}${c.commit ? ` @${c.commit.slice(0, 12)}` : ""}\n`);
    for (const f of d.findings) io.out(`${f.instance}: ${f.what}: ${f.detail}\n`);
  },
});

// ── repin ───────────────────────────────────────────────────────────────────────────────────────────────────────────

export const instanceRepin = defineCommand({
  meta: {
    summary: "move the base pin to the base's current commit and report what the move makes stale",
    tier: "admin",
    mutating: true,
    locks: ["repository"],
    help: "A record the extension holds judgments of, for an artifact the base now holds, is left in place and listed; moving it is the owner's verb.",
  },
  contract: defineContract({
    key: "instance-repin",
    args: z.object({}),
    argv: {},
    data: z.object({ from: z.string(), to: z.string(), judged: z.array(z.string()) }),
  }),
  run(ctx) {
    const inst = instanceOf(ctx);
    if (!inst.config.extends) throw new AthError("USAGE", `${inst.config.name} is standalone; it has no base to repin`);
    const path = resolve(inst.root, inst.config.extends.path);
    const from = inst.config.extends.commit;
    const to = headCommit(path);
    const cfg = parseConfig(readFileSync(join(inst.root, CONFIG_FILE), "utf8"), CONFIG_FILE);
    cfg.extends = { path: inst.config.extends.path, commit: to };
    writeAtomic(join(inst.root, CONFIG_FILE), emitConfig(cfg));
    const after = openInstance(inst.root, ctx.host);
    const baseHolds = new Set(after.base ? chain(after.base).flatMap((x) => ownRecords(x)) : []);
    const judged = ownRecords(after).filter((h) => {
      const r = ownRecord(after, h)!;
      return baseHolds.has(h) && (r.intrinsics !== undefined || r.passes !== undefined);
    });
    return { data: { from, to, judged } };
  },
  text(d, io) {
    io.out(`${d.from === d.to ? "already at" : `moved ${d.from.slice(0, 12)} →`} ${d.to.slice(0, 12)}\n`);
    for (const h of d.judged) io.out(`judged here, now held by the base: ${h}\n`);
  },
});

// ── reshard ─────────────────────────────────────────────────────────────────────────────────────────────────────────

export const instanceReshard = defineCommand({
  meta: {
    summary: "move records to the shard widths athenaeum.yaml declares; no line changes",
    tier: "admin",
    mutating: true,
    locks: ["repository"],
  },
  contract: defineContract({ key: "instance-reshard", args: z.object({}), argv: {}, data: z.object({ moved: z.number() }) }),
  run(ctx) {
    const inst = instanceOf(ctx);
    const writes: JournalWrite[] = [];
    const dir = join(inst.root, "corpus", "records");
    const walk = (d: string): string[] =>
      existsSync(d)
        ? readdirSync(d, { recursive: true, withFileTypes: true })
            .filter((e) => e.isFile() && e.name.endsWith(".yaml"))
            .map((e) => join(e.parentPath, e.name))
        : [];
    for (const p of walk(dir)) {
      const h = basename(p, ".yaml");
      if (!/^[0-9a-f]{64}$/.test(h)) continue;
      const want = recordPath(inst, h);
      if (want === p) continue;
      writes.push({ path: want, content: readFileSync(p) }, { path: p, content: null });
    }
    if (writes.length) commitJournal(instanceState(ctx.host, inst.config.id), writes);
    return { data: { moved: writes.length / 2 } };
  },
  text: (d, io) => io.out(`moved ${d.moved} records\n`),
});
