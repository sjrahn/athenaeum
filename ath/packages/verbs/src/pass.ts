// pass.ts — `ath pass open|stage|sign|abandon|show` (spec §13.1–§13.2) and `ath readings` (§13.4). A pass is one author
// and one verifier over one artifact: the author opens and stages it in the instance's host state, outside the
// repository; the verifier, who is not the author, signs it, and signing lays it over the record and runs the record,
// per-file and per-form checks — any blocking finding refuses the signature and leaves the staging untouched. The
// signature is refused against a record that changed since the pass was opened. Abandoning discards the staging, and
// its id is free again. An extension never judges its base's artifacts: that is demand on the base (§4.4).
import { existsSync, readFileSync } from "node:fs";
import { resolve as resolvePath } from "node:path";
import { defineContract, z } from "@ath/contracts";
import { canonicalAt } from "@ath/engine/address/address.ts";
import { type Finding, recordChecks } from "@ath/engine/checks/record.ts";
import { Parses } from "@ath/engine/formats/index.ts";
import { entityView, isEntityName, ownEntity } from "@ath/engine/graph/entity.ts";
import { accepted, rulingsOf } from "@ath/engine/graph/rulings.ts";
import { holdings, type Instance, ownRecord, recordPath, recordView, resolvePrefix, writeRecord } from "@ath/engine/instance/instance.ts";
import { answers, superseded } from "@ath/engine/pass/coverage.ts";
import { readingCheck, unreadUnits } from "@ath/engine/pass/reading-check.ts";
import { applyStaged } from "@ath/engine/pass/sign.ts";
import { dropStaged, nextId, openPasses, readStaged, type StagedPass, writeStaged } from "@ath/engine/pass/staging.ts";
import type { Reading, Scope } from "@ath/engine/record/document.ts";
import { pin } from "@ath/engine/vocab/terms.ts";
import { defineCommand } from "@ath/kit/define.ts";
import { AthError } from "@ath/kit/errors.ts";
import { blake3Hex } from "@ath/kit/hash.ts";
import type { KitCtx } from "@ath/kit/types.ts";
import { resolver } from "./artifacts.ts";
import { custodyIndex, instanceOf, localStore } from "./context.ts";
import { entityFileHash, kindsOfEntity, nextEntityPass, signEntityLines, writeEntity } from "./entity-pass.ts";
import { openGraph } from "./graph.ts";
import { viewer } from "./view.ts";

const finding = z.object({ check: z.string(), level: z.string(), at: z.string().optional(), message: z.string() });

function stateOf(ctx: KitCtx): string {
  if (!ctx.instance) throw new AthError("CONFIG", "no instance with an id");
  return ctx.instance.state;
}

/** The artifact a record pass is over: a hash or prefix the chain holds, as a record or a constituent. */
async function subjectOf(ctx: KitCtx, inst: Instance, subject: string): Promise<string> {
  const index = custodyIndex(ctx);
  try {
    const vw = viewer(inst, resolver(inst, localStore(ctx), index).resolve);
    return resolvePrefix(subject, new Set([...holdings(inst).keys(), ...vw.containers.keys()]));
  } finally {
    index.close();
  }
}

const fileHash = async (inst: Instance, hash: string): Promise<string | null> => {
  const p = recordPath(inst, hash);
  return existsSync(p) ? blake3Hex(new Uint8Array(readFileSync(p))) : null;
};

function refuseBase(inst: Instance, hash: string): void {
  const v = recordView(inst, hash);
  if (v && v.holder !== inst)
    throw new AthError(
      "CONFLICT",
      `${hash} is held by the base ${v.holder.config.name}: reading or forming it is demand on the base (§4.4)`,
    );
}

/** Sign an entity pass: bind and check its lines, write the pass line and the lines under it. */
async function signEntity(ctx: KitCtx, inst: Instance, name: string, id: string) {
  const state = stateOf(ctx);
  const s = readStaged(state, name, id);
  const verify = ctx.caller.actor!;
  if (verify === s.by) throw new AthError("DENIED", `${s.by} authored ${id}; its verifier is someone else (§13.1.1)`);
  if ((await entityFileHash(inst, name)) !== s.against)
    throw new AthError("CONFLICT", `${name}'s file changed since ${id} was opened; abandon it and open a pass against the current file`);
  if (!s.lines?.length) throw new AthError("CONFLICT", `${id} stages no line`);
  const g = await openGraph(ctx, inst);
  try {
    const v = g.viewer.vocab.vocab;
    if (v.kinds.has(name)) throw new AthError("CONFLICT", `${name} is a kind; an entity and a kind never share a name`);
    const held = holdings(inst);
    const known = (h: string) => held.has(h) || g.viewer.containers.has(h);
    const { lines, problems } = await signEntityLines(s.lines, id, g.locate, v, known, kindsOfEntity(inst));
    if (problems.length) throw new AthError("CONFLICT", `${id} is not signed:\n${problems.map((p) => `  ${p}`).join("\n")}`, { problems });
    const pass = {
      pred: "pass",
      val: { by: s.by, date: ctx.wall.date(), id, verify, vocab: s.vocab, ...(s.note ? { note: s.note } : {}) },
    };
    const path = writeEntity(inst, name, [...(ownEntity(inst, name) ?? []), pass, ...lines]);
    dropStaged(state, name, id);
    return { data: { subject: name, id, record: path, over: null, findings: [], advisories: [] } };
  } finally {
    g.close();
  }
}

// ── open ────────────────────────────────────────────────────────────────────────────────────────────────────────────

export const passOpen = defineCommand({
  meta: {
    summary: "open a pass over an artifact (a hash) or an entity (a name), its author the actor; staged in host state",
    tier: "write",
    mutating: true,
    locks: ["repository"],
  },
  contract: defineContract({
    key: "pass-open",
    args: z.object({ subject: z.string(), note: z.string().optional() }),
    argv: { positionals: [{ name: "subject", required: true }], flags: { note: { type: "string" } } },
    data: z.object({ subject: z.string(), id: z.string(), by: z.string(), vocab: z.string() }),
  }),
  async run(ctx, a) {
    const inst = instanceOf(ctx);
    if (isEntityName(a.subject)) {
      // a pass over an entity: its lines' authorship, against the graph's vocabulary
      const state = stateOf(ctx);
      const index = custodyIndex(ctx);
      let vocab: string;
      try {
        vocab = await pin(viewer(inst, resolver(inst, localStore(ctx), index).resolve).vocab.vocab, "graph");
      } finally {
        index.close();
      }
      const id = nextEntityPass(inst, state, a.subject);
      const s: StagedPass = {
        subject: a.subject,
        kind: "entity",
        id,
        by: ctx.caller.actor!,
        vocab,
        opened: ctx.wall.iso(),
        against: await entityFileHash(inst, a.subject),
        ...(a.note ? { note: a.note } : {}),
      };
      writeStaged(state, s);
      return { data: { subject: a.subject, id, by: s.by, vocab } };
    }
    const hash = await subjectOf(ctx, inst, a.subject);
    refuseBase(inst, hash);
    const state = stateOf(ctx);
    const own = ownRecord(inst, hash);
    const id = nextId(Object.keys(own?.passes ?? {}), openPasses(state, hash));
    const index = custodyIndex(ctx);
    let vocab: string;
    try {
      vocab = await pin(viewer(inst, resolver(inst, localStore(ctx), index).resolve).vocab.vocab, "corpus");
    } finally {
      index.close();
    }
    const s: StagedPass = {
      subject: hash,
      kind: "record",
      id,
      by: ctx.caller.actor!,
      vocab,
      opened: ctx.wall.iso(),
      against: await fileHash(inst, hash),
      ...(a.note ? { note: a.note } : {}),
    };
    writeStaged(state, s);
    return { data: { subject: hash, id, by: s.by, vocab } };
  },
  text: (d, io) => io.out(`opened ${d.id} on ${d.subject} by ${d.by} against ${d.vocab}\n`),
});

// ── stage ───────────────────────────────────────────────────────────────────────────────────────────────────────────

const stageFile = z
  .object({
    readings: z
      .record(
        z.string(),
        z.object({ text: z.string().optional(), cells: z.array(z.string()).optional(), tex: z.string().optional() }).strict(),
      )
      .optional(),
    retire: z.array(z.string()).optional(),
    scopes: z.array(z.record(z.string(), z.unknown())).optional(),
    chrome: z.array(z.record(z.string(), z.unknown())).optional(),
    shape: z.string().optional(),
    attests: z.array(z.enum(["readings", "structure"])).optional(),
    note: z.string().optional(),
    lines: z.array(z.record(z.string(), z.unknown())).optional(),
  })
  .strict();

export const passStage = defineCommand({
  meta: {
    summary: "stage readings, a tree, chrome, a shape or what the pass attests, from flags or a YAML file",
    tier: "write",
    mutating: true,
    locks: ["repository"],
    help: "A file holds any of: readings (address → {text|cells|tex}), retire (addresses), scopes (the whole tree), chrome, shape, attests, note. Readings merge by address; the rest replace.",
    examples: [
      "ath pass stage 5e6e497d p2 --at 'page=1&bbox=0.14,0.69,0.09,0.01' --text 'Version 02.1'",
      "ath pass stage 5e6e497d p2 --file tree.yaml",
    ],
  },
  contract: defineContract({
    key: "pass-stage",
    args: z.object({
      subject: z.string(),
      id: z.string(),
      file: z.string().optional(),
      at: z.string().optional(),
      text: z.string().optional(),
      cells: z.string().optional(),
      tex: z.string().optional(),
      retire: z.array(z.string()).default([]),
      attests: z.array(z.enum(["readings", "structure"])).default([]),
      shape: z.string().optional(),
      note: z.string().optional(),
      line: z.array(z.string()).default([]),
    }),
    argv: {
      positionals: [
        { name: "subject", required: true },
        { name: "id", required: true },
      ],
      flags: {
        file: { type: "string", metavar: "YAML" },
        at: { type: "string", help: "the reading's intrinsic address" },
        text: { type: "string" },
        cells: { type: "string", help: "one row's cells, a JSON list of strings" },
        tex: { type: "string" },
        retire: { type: "string", repeat: true, metavar: "AT" },
        attests: { type: "string", repeat: true, help: "readings or structure" },
        shape: { type: "string" },
        note: { type: "string" },
        line: { type: "string", repeat: true, metavar: "JSON", help: "an entity pass's claim or is line: {pred, val, qual?, ev?}" },
      },
    },
    data: z.object({
      subject: z.string(),
      id: z.string(),
      readings: z.number(),
      scopes: z.number(),
      attests: z.array(z.string()),
      lines: z.number(),
    }),
  }),
  async run(ctx, a) {
    const inst = instanceOf(ctx);
    const hash = isEntityName(a.subject) ? a.subject : await subjectOf(ctx, inst, a.subject);
    const state = stateOf(ctx);
    const s = readStaged(state, hash, a.id);
    if (s.by !== ctx.caller.actor) throw new AthError("DENIED", `${a.id} is ${s.by}'s to stage`);
    if (s.kind === "entity" && (a.at !== undefined || a.retire.length || a.attests.length || a.shape !== undefined))
      throw new AthError("USAGE", "an entity pass stages lines, from --file {lines: […]} or --line");
    if (a.file) {
      const p = resolvePath(ctx.cwd, a.file);
      let doc: unknown;
      try {
        doc = Bun.YAML.parse(readFileSync(p, "utf8"));
      } catch (e) {
        throw new AthError("USAGE", `${a.file}: ${(e as Error).message}`);
      }
      const r = stageFile.safeParse(doc);
      if (!r.success)
        throw new AthError("USAGE", `${a.file}: ${r.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`);
      const f = r.data;
      if (f.readings)
        s.readings = {
          ...(s.readings ?? {}),
          ...Object.fromEntries(Object.entries(f.readings).map(([at, b]) => [canonicalAt(at), b as Reading])),
        };
      if (f.retire) s.retire = [...new Set([...(s.retire ?? []), ...f.retire.map(canonicalAt)])];
      if (f.scopes) s.scopes = f.scopes as Scope[];
      if (f.chrome) s.chrome = f.chrome;
      if (f.shape !== undefined) s.shape = f.shape;
      if (f.attests) s.attests = f.attests;
      if (f.note !== undefined) s.note = f.note;
      if (f.lines) {
        if (s.kind !== "entity") throw new AthError("USAGE", "lines are staged on an entity pass");
        s.lines = [...(s.lines ?? []), ...f.lines];
      } else if (s.kind === "entity" && (f.readings || f.scopes || f.retire || f.chrome || f.shape))
        throw new AthError("USAGE", "an entity pass stages lines");
    }
    for (const l of a.line) {
      if (s.kind !== "entity") throw new AthError("USAGE", "--line stages a line on an entity pass");
      let v: unknown;
      try {
        v = JSON.parse(l);
      } catch (e) {
        throw new AthError("USAGE", `--line is JSON: ${(e as Error).message}`);
      }
      s.lines = [...(s.lines ?? []), v as Record<string, unknown>];
    }
    if (a.at !== undefined) {
      const body: Reading = {};
      if (a.text !== undefined) body.text = a.text;
      if (a.tex !== undefined) body.tex = a.tex;
      if (a.cells !== undefined) {
        const c = JSON.parse(a.cells) as unknown;
        if (!Array.isArray(c) || !c.every((x) => typeof x === "string"))
          throw new AthError("USAGE", "--cells is a JSON list of strings: one row");
        body.cells = c;
      }
      if (!Object.keys(body).length) throw new AthError("USAGE", "--at needs --text, --cells or --tex");
      s.readings = { ...(s.readings ?? {}), [canonicalAt(a.at)]: body };
    } else if (a.text !== undefined || a.cells !== undefined || a.tex !== undefined)
      throw new AthError("USAGE", "a body needs --at, its address");
    if (a.retire.length) s.retire = [...new Set([...(s.retire ?? []), ...a.retire.map(canonicalAt)])];
    if (a.attests.length) s.attests = [...new Set(a.attests)];
    if (a.shape !== undefined) s.shape = a.shape;
    if (a.note !== undefined) s.note = a.note;
    writeStaged(state, s);
    return {
      data: {
        subject: hash,
        id: a.id,
        readings: Object.keys(s.readings ?? {}).length,
        scopes: s.scopes?.length ?? 0,
        attests: s.attests ?? [],
        lines: s.lines?.length ?? 0,
      },
    };
  },
  text: (d, io) =>
    io.out(
      `${d.id} on ${d.subject}: ${d.readings} readings, ${d.scopes} top-level scopes staged${d.attests.length ? `, attests ${d.attests.join(", ")}` : ""}\n`,
    ),
});

// ── sign ────────────────────────────────────────────────────────────────────────────────────────────────────────────

export const passSign = defineCommand({
  meta: {
    summary: "sign a staged pass as its verifier: lay it over the record and run the checks; a blocking finding refuses",
    tier: "write",
    mutating: true,
    locks: ["repository"],
  },
  contract: defineContract({
    key: "pass-sign",
    args: z.object({ subject: z.string(), id: z.string() }),
    argv: {
      positionals: [
        { name: "subject", required: true },
        { name: "id", required: true },
      ],
    },
    data: z.object({
      subject: z.string(),
      id: z.string(),
      record: z.string(),
      over: z.array(z.string()).nullable(),
      findings: z.array(finding),
      advisories: z.array(z.record(z.string(), z.unknown())),
    }),
  }),
  async run(ctx, a) {
    const inst = instanceOf(ctx);
    if (isEntityName(a.subject)) return signEntity(ctx, inst, a.subject, a.id);
    const hash = await subjectOf(ctx, inst, a.subject);
    refuseBase(inst, hash);
    const state = stateOf(ctx);
    const s = readStaged(state, hash, a.id);
    const verify = ctx.caller.actor!;
    if (verify === s.by) throw new AthError("DENIED", `${s.by} authored ${a.id}; its verifier is someone else (§13.1.1)`);
    if ((await fileHash(inst, hash)) !== s.against)
      throw new AthError("CONFLICT", `the record changed since ${a.id} was opened; abandon it and open a pass against the current record`);
    const index = custodyIndex(ctx);
    try {
      const res = resolver(inst, localStore(ctx), index);
      const vw = viewer(inst, res.resolve);
      const view = await vw.view(hash);
      const { record, problems } = applyStaged(ownRecord(inst, hash), view.intrinsics, s, verify, ctx.wall.date());
      const findings: Finding[] = [
        ...problems.map((m) => ({ check: "coverage" as const, level: "block" as const, message: m })),
        ...recordChecks(record, { vocab: vw.vocab.vocab, format: view.format, intrinsics: view.intrinsics, matched: view.shape.matched }),
      ];
      const blocking = findings.filter((f) => f.level === "block");
      if (blocking.length)
        throw new AthError(
          "CONFLICT",
          `${a.id} is not signed:\n${blocking.map((f) => `  ${f.check}${f.at ? ` ${f.at}` : ""}: ${f.message}`).join("\n")}`,
          { findings },
        );
      const { bytes } = await res.resolve(hash);
      const advisories =
        view.format.class === "rendered"
          ? await readingCheck(record, view.format, new Parses(bytes), vw.vocab.vocab, accepted(rulingsOf(inst)), hash)
          : [];
      const path = writeRecord(inst, hash, record);
      dropStaged(state, hash, a.id);
      return {
        data: {
          subject: hash,
          id: a.id,
          record: path,
          over: record.passes![a.id]!.over ?? null,
          findings,
          advisories: advisories.filter((x) => x.state !== "agrees") as never,
        },
      };
    } finally {
      index.close();
    }
  },
  text(d, io) {
    io.out(`signed ${d.id} on ${d.subject} → ${d.record} · covers ${d.over ? d.over.join(" ") : "everything"}\n`);
    for (const f of d.findings) io.out(`${f.level.padEnd(8)} ${f.check}${f.at ? ` ${f.at}` : ""}: ${f.message}\n`);
    for (const x of d.advisories) io.out(`advisory ${x.at} ${x.aspect}: ${x.state}${x.detail ? ` — ${x.detail}` : ""}\n`);
  },
});

// ── abandon, show ───────────────────────────────────────────────────────────────────────────────────────────────────

export const passAbandon = defineCommand({
  meta: { summary: "discard a staged pass; its id is free again", tier: "write", mutating: true, locks: ["repository"] },
  contract: defineContract({
    key: "pass-abandon",
    args: z.object({ subject: z.string(), id: z.string() }),
    argv: {
      positionals: [
        { name: "subject", required: true },
        { name: "id", required: true },
      ],
    },
    data: z.object({ subject: z.string(), id: z.string() }),
  }),
  async run(ctx, a) {
    const inst = instanceOf(ctx);
    const hash = isEntityName(a.subject) ? a.subject : await subjectOf(ctx, inst, a.subject);
    readStaged(stateOf(ctx), hash, a.id);
    dropStaged(stateOf(ctx), hash, a.id);
    return { data: { subject: hash, id: a.id } };
  },
  text: (d, io) => io.out(`abandoned ${d.id} on ${d.subject}\n`),
});

export const passShow = defineCommand({
  meta: {
    summary: "a subject's passes: the signed, with what each answers for, and the open, with what they stage",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "pass-show",
    args: z.object({ subject: z.string() }),
    argv: { positionals: [{ name: "subject", required: true }] },
    data: z.object({
      subject: z.string(),
      signed: z.array(
        z.object({
          id: z.string(),
          by: z.string(),
          verify: z.string(),
          date: z.string(),
          answers: z.array(z.string()),
          superseded: z.boolean(),
        }),
      ),
      open: z.array(z.record(z.string(), z.unknown())),
    }),
  }),
  async run(ctx, a) {
    const inst = instanceOf(ctx);
    if (isEntityName(a.subject)) {
      const lines = entityView(inst, a.subject) ?? [];
      const signed = lines
        .filter((h) => h.line.pred === "pass")
        .map((h) => {
          const p = h.line.val as Record<string, string>;
          return {
            id: p.id!,
            by: p.by!,
            verify: p.verify!,
            date: p.date!,
            answers: lines.filter((x) => x.line.pass === p.id && x.instance === h.instance).map((x) => x.line.pred),
            superseded: false,
          };
        });
      const state = stateOf(ctx);
      return {
        data: {
          subject: a.subject,
          signed,
          open: openPasses(state, a.subject).map((id) => readStaged(state, a.subject, id) as unknown as Record<string, unknown>),
        },
      };
    }
    const hash = await subjectOf(ctx, inst, a.subject);
    const r = recordView(inst, hash)?.record;
    const ans = r ? answers(r) : new Map<string, string[]>();
    const sup = new Set(r ? superseded(r) : []);
    const signed = Object.entries(r?.passes ?? {}).map(([id, p]) => ({
      id,
      by: p.by,
      verify: p.verify,
      date: p.date,
      answers: ans.get(id) ?? [],
      superseded: sup.has(id),
    }));
    const state = stateOf(ctx);
    const open = openPasses(state, hash).map((id) => readStaged(state, hash, id) as unknown as Record<string, unknown>);
    return { data: { subject: hash, signed, open } };
  },
  text(d, io) {
    for (const p of d.signed)
      io.out(`${p.id}  ${p.by} / ${p.verify}  ${p.date}${p.superseded ? "  superseded" : `  answers for ${p.answers.length}`}\n`);
    for (const o of d.open) io.out(`${o.id}  open by ${o.by} since ${o.opened}\n`);
  },
});

// ── readings ────────────────────────────────────────────────────────────────────────────────────────────────────────

export const readingsCommand = defineCommand({
  meta: {
    summary: "the reading check's advisories for an artifact, and the hint's units outside every reading and chrome",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "readings",
    args: z.object({ subject: z.string() }),
    argv: { positionals: [{ name: "subject", required: true }] },
    data: z.object({
      subject: z.string(),
      advisories: z.array(z.record(z.string(), z.unknown())),
      unread: z.array(z.object({ text: z.string(), at: z.string() })),
    }),
  }),
  async run(ctx, a) {
    const inst = instanceOf(ctx);
    const hash = await subjectOf(ctx, inst, a.subject);
    const index = custodyIndex(ctx);
    try {
      const res = resolver(inst, localStore(ctx), index);
      const vw = viewer(inst, res.resolve);
      const view = await vw.view(hash);
      if (!view.record) throw new AthError("NOT_FOUND", `${hash} has no record`);
      if (view.format.class !== "rendered") throw new AthError("USAGE", `${view.mime} is not rendered: it holds no readings`);
      const parses = new Parses((await res.resolve(hash)).bytes);
      const advisories = await readingCheck(view.record, view.format, parses, vw.vocab.vocab, accepted(rulingsOf(inst)), hash);
      const unread = await unreadUnits(
        view.record,
        view.format,
        parses,
        view.chrome.map((c) => c.at),
      );
      return { data: { subject: hash, advisories: advisories as never, unread } };
    } finally {
      index.close();
    }
  },
  text(d, io) {
    for (const x of d.advisories) io.out(`${String(x.state).padEnd(9)} ${x.at} ${x.aspect}${x.detail ? ` — ${x.detail}` : ""}\n`);
    if (d.unread.length) io.out(`${d.unread.length} hint units outside every reading and chrome\n`);
  },
});
