// records.ts — reading and keeping records (spec §19.5): `holdings`, `record`, `provenance`, `show`, `sort`, `sweep`.
// A subject is named by its full hash or by a prefix of 8 or more digits that names one artifact the chain holds.
import { readFileSync } from "node:fs";
import { relative } from "node:path";
import { defineContract, z } from "@ath/contracts";
import { formatOf, intrinsicsOf, intrinsicsOp, parseIntrinsicsOp } from "@ath/engine/formats/index.ts";
import {
  chain,
  containersIndex,
  holdings,
  type Instance,
  ownRecord,
  ownRecords,
  recordPath,
  recordView,
  resolvePrefix,
  shortest,
  writeRecord,
} from "@ath/engine/instance/instance.ts";
import { emitRecord, passOrder } from "@ath/engine/record/document.ts";
import { nextNeeds, stageOf } from "@ath/engine/record/stage.ts";
import { type ProvenanceStep, provenance } from "@ath/engine/testimony/testimony.ts";
import { defineCommand } from "@ath/kit/define.ts";
import { AthError } from "@ath/kit/errors.ts";
import type { Io } from "@ath/kit/io.ts";
import { custodyIndex, instanceOf, localStore } from "./context.ts";

const subjectArg = { positionals: [{ name: "subject", required: true, help: "a hash, or a prefix of 8 or more hex digits" }] };

/** Every hash a subject may name: held artifacts and the constituents of held containers. */
function known(inst: Instance): { all: Set<string>; held: Map<string, Instance>; containers: ReturnType<typeof containersIndex> } {
  const held = holdings(inst);
  const containers = containersIndex(inst);
  return { all: new Set([...held.keys(), ...containers.keys()]), held, containers };
}

// ── holdings ────────────────────────────────────────────────────────────────────────────────────────────────────────

const holdingRow = z.object({
  hash: z.string(),
  short: z.string(),
  mime: z.string().nullable(),
  stage: z.string().nullable(),
  receipts: z.number(),
  origins: z.number(),
  instance: z.string(),
});

export const holdingsCommand = defineCommand({
  meta: {
    summary: "what the instance holds: its records, each with its stage, receipts and origins, and its testimony",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "holdings",
    args: z.object({}),
    argv: {},
    data: z.object({ records: z.array(holdingRow), testimony: z.number(), assets: z.number() }),
  }),
  run(ctx) {
    const inst = instanceOf(ctx);
    const { held, containers } = known(inst);
    const hashes = [...held.keys()].sort();
    const records = hashes.map((h) => {
      const r = recordView(inst, h)!.record;
      return {
        hash: h,
        short: shortest(h, hashes),
        mime: typeof r.intrinsics?.mime === "string" ? r.intrinsics.mime : null,
        stage: stageOf(r),
        receipts: r.receipts?.length ?? 0,
        origins: r.origins?.length ?? 0,
        instance: held.get(h)!.config.name,
      };
    });
    const index = custodyIndex(ctx);
    try {
      const testimony = new Set(chain(inst).flatMap((x) => index.testimonyOf(x.config.id).map((t) => t.hash))).size;
      const assets = [...containers.entries()].filter(([h, cs]) => !held.has(h) && cs.some((c) => c.kind === "asset")).length;
      return { data: { records, testimony, assets } };
    } finally {
      index.close();
    }
  },
  text(d, io) {
    for (const r of d.records)
      io.out(
        `${r.short.padEnd(10)} ${(r.stage ?? "structured").padEnd(11)} ${String(r.mime).padEnd(28)} ${r.receipts}r ${r.origins}o  ${r.instance}\n`,
      );
    io.out(`${d.records.length} records · ${d.assets} assets held through their containers · ${d.testimony} testimony\n`);
  },
});

// ── record ──────────────────────────────────────────────────────────────────────────────────────────────────────────

export const recordCommand = defineCommand({
  meta: {
    summary: "a record's stage, its passes with what each covers and attests, and what the next stage needs",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "record",
    args: z.object({ subject: z.string() }),
    argv: subjectArg,
    data: z.object({
      hash: z.string(),
      record: z.string().nullable(),
      instance: z.string().nullable(),
      mime: z.string().nullable(),
      class: z.string().nullable(),
      stage: z.string().nullable(),
      passes: z.array(
        z.object({
          id: z.string(),
          by: z.string(),
          verify: z.string(),
          date: z.string(),
          over: z.array(z.string()).nullable(),
          attests: z.array(z.string()),
        }),
      ),
      readings: z.number(),
      scopes: z.number(),
      constituents: z.number(),
      within: z.array(z.object({ container: z.string(), path: z.string(), kind: z.string() })),
      next: z.string(),
    }),
  }),
  run(ctx, a) {
    const inst = instanceOf(ctx);
    const { all, containers } = known(inst);
    const hash = resolvePrefix(a.subject, all);
    const v = recordView(inst, hash);
    const within = containers.get(hash) ?? [];
    if (!v)
      return {
        data: {
          hash,
          record: null,
          instance: null,
          mime: null,
          class: null,
          stage: null,
          passes: [],
          readings: 0,
          scopes: 0,
          constituents: 0,
          within,
          next: "a record of its own, written by its first signed pass or by ingesting it alone; until then its container's record holds it",
        },
      };
    const r = v.record;
    const count = (s: { scopes?: unknown[] }[] | undefined): number => (s ?? []).reduce((n, x) => n + 1 + count(x.scopes as never), 0);
    const mime = typeof r.intrinsics?.mime === "string" ? r.intrinsics.mime : null;
    return {
      data: {
        hash,
        record: relative(inst.root, recordPath(v.holder, hash)),
        instance: v.holder.config.name,
        mime,
        class: mime ? (formatOf(mime).class ?? null) : null,
        stage: stageOf(r),
        passes: Object.keys(r.passes ?? {})
          .sort(passOrder)
          .map((id) => {
            const p = r.passes![id]!;
            return { id, by: p.by, verify: p.verify, date: p.date, over: p.over ?? null, attests: p.attests ?? [] };
          }),
        readings: Object.keys(r.readings ?? {}).length,
        scopes: count(r.scopes as never),
        constituents: Array.isArray(r.intrinsics?.constituents) ? r.intrinsics.constituents.length : 0,
        within,
        next: nextNeeds(r),
      },
    };
  },
  text(d, io) {
    io.out(`${d.hash}\n`);
    if (d.record)
      io.out(
        `record   ${d.record} (${d.instance})\n${d.mime ? `mime     ${d.mime} · ${d.class ?? "unregistered"}\n` : ""}stage    ${d.stage ?? "none (structured)"}\n`,
      );
    else io.out("record   none of its own\n");
    for (const p of d.passes)
      io.out(
        `pass     ${p.id} by ${p.by}, verified by ${p.verify}, ${p.date} · over ${p.over ? p.over.join(" ") : "everything"}${p.attests.length ? ` · attests ${p.attests.join(", ")}` : ""}\n`,
      );
    if (d.readings) io.out(`readings ${d.readings}\n`);
    if (d.scopes) io.out(`scopes   ${d.scopes}\n`);
    if (d.constituents) io.out(`holds    ${d.constituents} constituents\n`);
    for (const w of d.within) io.out(`within   ${w.container} at ${w.path} (${w.kind})\n`);
    io.out(`next     ${d.next}\n`);
  },
});

// ── provenance ──────────────────────────────────────────────────────────────────────────────────────────────────────

const step: z.ZodType<ProvenanceStep> = z.lazy(() =>
  z.object({
    artifact: z.string(),
    receipts: z.array(z.any()).optional(),
    origins: z.array(z.any()).optional(),
    within: z.array(z.object({ container: z.string(), path: z.string(), provenance: step })).optional(),
  }),
) as never;

function printChain(io: Io, s: ProvenanceStep, ind = ""): void {
  io.out(`${ind}${s.artifact}\n`);
  for (const r of s.receipts ?? []) io.out(`${ind}  received ${r.received} by ${r.actor} as ${r.name}\n`);
  for (const o of s.origins ?? []) io.out(`${ind}  origin   ${JSON.stringify(o)}\n`);
  for (const w of s.within ?? []) {
    io.out(`${ind}  ← path=${w.path} in\n`);
    printChain(io, w.provenance, `${ind}    `);
  }
}

export const provenanceCommand = defineCommand({
  meta: {
    summary: "an artifact's provenance: its receipts and origins, and every container that holds it, transitively",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({ key: "provenance", args: z.object({ subject: z.string() }), argv: subjectArg, data: step }),
  run(ctx, a) {
    const inst = instanceOf(ctx);
    const { all, containers } = known(inst);
    const hash = resolvePrefix(a.subject, all);
    return {
      data: provenance(
        hash,
        (h) => recordView(inst, h)?.record ?? null,
        (h) => containers.get(h) ?? [],
      ),
    };
  },
  text: (d, io) => printChain(io, d as ProvenanceStep),
});

// ── show, sort ──────────────────────────────────────────────────────────────────────────────────────────────────────

export const showCommand = defineCommand({
  meta: { summary: "a subject's document across the chain, as one record", tier: "read", mutating: false },
  contract: defineContract({
    key: "show",
    args: z.object({ subject: z.string() }),
    argv: subjectArg,
    data: z.object({ hash: z.string(), document: z.string() }),
  }),
  run(ctx, a) {
    const inst = instanceOf(ctx);
    const hash = resolvePrefix(a.subject, known(inst).all);
    const v = recordView(inst, hash);
    if (!v) throw new AthError("NOT_FOUND", `${hash} has no record of its own; it is held through its container`);
    return { data: { hash, document: emitRecord(v.record) } };
  },
  text: (d, io) => io.out(d.document),
});

export const sortCommand = defineCommand({
  meta: {
    summary: "rewrite a record of this instance in its canonical order and style",
    tier: "write",
    mutating: true,
    locks: ["repository"],
  },
  contract: defineContract({
    key: "sort",
    args: z.object({ subject: z.string() }),
    argv: subjectArg,
    data: z.object({ hash: z.string(), record: z.string(), changed: z.boolean() }),
  }),
  run(ctx, a) {
    const inst = instanceOf(ctx);
    const hash = resolvePrefix(a.subject, ownRecords(inst));
    const before = readFileSync(recordPath(inst, hash), "utf8");
    const r = ownRecord(inst, hash)!;
    const path = writeRecord(inst, hash, r);
    return { data: { hash, record: path, changed: emitRecord(r) !== before } };
  },
  text: (d, io) => io.out(`${d.changed ? "sorted" : "already canonical"}  ${d.record}\n`),
});

// ── sweep ───────────────────────────────────────────────────────────────────────────────────────────────────────────

export const sweepCommand = defineCommand({
  meta: {
    summary: "rewrite `intrinsics` wherever this tool's op for the format is newer than the one that wrote it",
    tier: "write",
    mutating: true,
    locks: ["repository"],
    help: "--stale lists what is stale and rewrites nothing. An artifact whose bytes this host cannot read is listed as unavailable.",
  },
  contract: defineContract({
    key: "sweep",
    args: z.object({ stale: z.boolean().default(false) }),
    argv: { flags: { stale: { type: "boolean", help: "list the stale projections, rewrite nothing" } } },
    data: z.object({
      stale: z.array(z.object({ hash: z.string(), from: z.string(), to: z.string(), done: z.boolean(), reason: z.string().optional() })),
    }),
  }),
  async run(ctx, a) {
    const inst = instanceOf(ctx);
    const store = localStore(ctx);
    const out: { hash: string; from: string; to: string; done: boolean; reason?: string }[] = [];
    for (const h of ownRecords(inst)) {
      const r = ownRecord(inst, h)!;
      if (!r.intrinsics) continue;
      const from = String(r.intrinsics.op);
      const want = intrinsicsOp(formatOf(String(r.intrinsics.mime)));
      const was = parseIntrinsicsOp(from);
      const now = parseIntrinsicsOp(want)!;
      if (was && was.name === now.name && was.version >= now.version) continue;
      const row: (typeof out)[number] = { hash: h, from, to: want, done: false };
      if (!a.stale) {
        const bytes = await store.get("artifacts", h);
        if (!bytes) row.reason = "unavailable on this host";
        else {
          r.intrinsics = (await intrinsicsOf(bytes, String(r.intrinsics.mime))).value;
          writeRecord(inst, h, r);
          row.done = true;
        }
      }
      out.push(row);
    }
    return { data: { stale: out } };
  },
  text(d, io) {
    for (const s of d.stale)
      io.out(`${s.done ? "rewrote" : "stale  "}  ${s.hash}  ${s.from} → ${s.to}${s.reason ? `  (${s.reason})` : ""}\n`);
    if (!d.stale.length) io.out("every projection is current\n");
  },
});
