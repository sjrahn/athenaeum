// rule.ts — `ath rule distrust|accept|seek|defer|decline <target>`, `ath rule revoke <id>`, `ath rulings` and
// `ath relevant [<subject>]` (spec §13.5, §19.5). Writing or removing a ruling is the owner's, confirmed at a terminal;
// listing them says what each currently affects; `relevant` names the `seek` rulings a subject meets.
import { defineContract, z } from "@ath/contracts";
import { demandKey } from "@ath/engine/graph/demand.ts";
import { isEntityName } from "@ath/engine/graph/entity.ts";
import { nextRulingId, ownRulings, type Ruling, type RulingPred, rulingProblem, writeRulings } from "@ath/engine/graph/rulings.ts";
import { chain, containersIndex, holdings, recordView, resolvePrefix } from "@ath/engine/instance/instance.ts";
import { scopesOf } from "@ath/engine/record/tree.ts";
import { refinesChain } from "@ath/engine/vocab/load.ts";
import { defineCommand } from "@ath/kit/define.ts";
import { AthError } from "@ath/kit/errors.ts";
import type { KitCtx } from "@ath/kit/types.ts";
import { custodyIndex, instanceOf } from "./context.ts";
import { openGraph } from "./graph.ts";

const target = (ctx: KitCtx, on: string): string => {
  // a hash prefix at the terminal stands for the full hash, which is what is stored (§7.1.3)
  const m = /^(?:ath:\/\/)?([0-9a-z][0-9a-z-]*)([?#].*)?$/.exec(on.trim());
  if (!m) throw new AthError("USAGE", `'${on}' names no subject: ath://<hash or name>[?<at>][#<pass>]`);
  const inst = instanceOf(ctx);
  let subject = m[1]!;
  if (/^[0-9a-f]{8,64}$/.test(subject)) {
    // anything the chain holds or holds through a container, and every testimony its receipts delivered
    const index = custodyIndex(ctx);
    try {
      const known = new Set([
        ...holdings(inst).keys(),
        ...containersIndex(inst).keys(),
        ...chain(inst).flatMap((x) => index.testimonyOf(x.config.id).map((t) => t.hash)),
      ]);
      subject = resolvePrefix(subject, known);
    } finally {
      index.close();
    }
  }
  if (!/^[0-9a-f]{64}$/.test(subject) && !isEntityName(subject))
    throw new AthError("USAGE", `'${m[1]}' is neither a hash nor an entity name`);
  return `ath://${subject}${m[2] ?? ""}`;
};

const ruleVerb = (pred: RulingPred) =>
  defineCommand({
    meta: {
      summary:
        pred === "distrust"
          ? "hold everything bound through a testimony, an op's output at a scope (--op), or a pass (#p<n>)"
          : pred === "accept"
            ? "mark a finding known: a reading-check divergence by scope and revision (--rev), or a check finding (--finding)"
            : pred === "seek"
              ? "demand a selection (--kind, --form, --origin, --entity), optionally its owed properties (--owes), and make it relevant"
              : pred === "defer"
                ? "order demand after everything not deferred: an item (its key or subject) or a selection (--kind)"
                : "remove demand: an item (its key or subject, --demand its kind) or a selection (--kind)",
      tier: "admin",
      mutating: true,
      locks: ["repository"],
    },
    contract: defineContract({
      key: `rule-${pred}`,
      args: z.object({
        target: z.string().optional(),
        why: z.string().optional(),
        op: z.string().optional(),
        rev: z.string().optional(),
        finding: z.string().optional(),
        owes: z.array(z.string()).default([]),
        kind: z.string().optional(),
        form: z.string().optional(),
        origin: z.string().optional(),
        entity: z.string().optional(),
        demand: z.string().optional(),
      }),
      argv: {
        positionals: [{ name: "target" }],
        flags: {
          why: { type: "string", help: "the owner's note to themself; never evidence, never exported" },
          op: { type: "string" },
          rev: { type: "string" },
          finding: { type: "string" },
          owes: { type: "string", repeat: true },
          kind: { type: "string" },
          form: { type: "string" },
          origin: { type: "string" },
          entity: { type: "string" },
          demand: { type: "string" },
        },
      },
      data: z.object({ id: z.string(), ruling: z.record(z.string(), z.unknown()) }),
    }),
    run(ctx, a) {
      const inst = instanceOf(ctx);
      const val: Record<string, unknown> = {};
      const sel: Record<string, string> = {};
      for (const k of ["kind", "form", "origin", "entity"] as const)
        if (a[k] !== undefined) sel[k] = k === "entity" ? `ath://${String(a[k]).replace(/^ath:\/\//, "")}` : String(a[k]);
      if (a.target !== undefined)
        val.on =
          pred === "defer" || pred === "decline"
            ? a.target.includes(":") && !a.target.startsWith("ath://")
              ? a.target
              : target(ctx, a.target)
            : target(ctx, a.target);
      if (Object.keys(sel).length) val.select = sel;
      if (a.op !== undefined) val.op = a.op;
      if (a.rev !== undefined) val.rev = a.rev;
      if (a.finding !== undefined) val.finding = a.finding;
      if (a.owes.length) val.owes = a.owes;
      if (a.demand !== undefined) val.demand = a.demand;
      if (a.why !== undefined) val.why = a.why;
      const r: Ruling = { id: nextRulingId(inst), pred, date: ctx.wall.date(), val: val as never, by: "owner" };
      const p = rulingProblem(r);
      if (p) throw new AthError("USAGE", p);
      writeRulings(inst, [...ownRulings(inst), r]);
      return { data: { id: r.id, ruling: r } };
    },
    text: (d, io) => io.out(`${d.id}  ${JSON.stringify(d.ruling.val)}\n`),
  });

export const ruleDistrust = ruleVerb("distrust");
export const ruleAccept = ruleVerb("accept");
export const ruleSeek = ruleVerb("seek");
export const ruleDefer = ruleVerb("defer");
export const ruleDecline = ruleVerb("decline");

export const ruleRevoke = defineCommand({
  meta: { summary: "remove a ruling", tier: "admin", mutating: true, locks: ["repository"] },
  contract: defineContract({
    key: "rule-revoke",
    args: z.object({ id: z.string() }),
    argv: { positionals: [{ name: "id", required: true }] },
    data: z.object({ id: z.string() }),
  }),
  run(ctx, a) {
    const inst = instanceOf(ctx);
    const all = ownRulings(inst);
    if (!all.some((r) => r.id === a.id)) throw new AthError("NOT_FOUND", `${inst.config.name} has no ruling ${a.id}`);
    writeRulings(
      inst,
      all.filter((r) => r.id !== a.id),
    );
    return { data: { id: a.id } };
  },
  text: (d, io) => io.out(`revoked ${d.id}\n`),
});

export const rulingsCommand = defineCommand({
  meta: { summary: "the rulings the instance relies on, and what each currently affects", tier: "read", mutating: false },
  contract: defineContract({
    key: "rulings",
    args: z.object({}),
    argv: {},
    data: z.object({
      rulings: z.array(
        z.object({
          id: z.string(),
          pred: z.string(),
          instance: z.string(),
          val: z.record(z.string(), z.unknown()),
          affects: z.array(z.string()),
        }),
      ),
    }),
  }),
  async run(ctx) {
    const inst = instanceOf(ctx);
    const g = await openGraph(ctx, inst);
    try {
      const rulings = g.rulings.map((r) => {
        let affects: string[] = [];
        if (r.pred === "seek") affects = g.demand.filter((d) => d.ruling === r.id).map(demandKey);
        else if (r.pred === "defer") affects = g.demand.filter((d) => d.deferred === r.id).map(demandKey);
        else if (r.pred === "distrust") {
          const on = String(r.val.on);
          for (const c of g.statuses.claims)
            for (const e of c.entries)
              if (
                e.state.state === "held" &&
                e.state.reason?.includes("distrust") &&
                (e.entry.anchor.startsWith(on.split("#")[0]!) || on.endsWith(`#${e.line.line.pass}`))
              )
                affects.push(`${c.entity} ${c.pred}`);
        }
        return { id: r.id, pred: r.pred, instance: r.instance, val: r.val, affects: [...new Set(affects)] };
      });
      return { data: { rulings } };
    } finally {
      g.close();
    }
  },
  text(d, io) {
    for (const r of d.rulings)
      io.out(
        `${r.id.padEnd(4)} ${r.pred.padEnd(8)} ${JSON.stringify(r.val)}${r.affects.length ? `  affects ${r.affects.length}` : ""}${r.instance ? `  (${r.instance})` : ""}\n`,
      );
  },
});

export const relevantCommand = defineCommand({
  meta: { summary: "the seek rulings an artifact, a scope or an entity meets", tier: "read", mutating: false },
  contract: defineContract({
    key: "relevant",
    args: z.object({ subject: z.string().optional() }),
    argv: { positionals: [{ name: "subject" }] },
    data: z.object({ relevant: z.array(z.object({ ruling: z.string(), subject: z.string(), why: z.string() })) }),
  }),
  async run(ctx, a) {
    const inst = instanceOf(ctx);
    const g = await openGraph(ctx, inst);
    try {
      const v = g.viewer.vocab.vocab;
      const out: { ruling: string; subject: string; why: string }[] = [];
      const seeks = g.rulings.filter((r) => r.pred === "seek");
      const kindsOf = (e: string) =>
        (g.entities.get(e) ?? []).filter((h) => h.line.pred === "is").flatMap((h) => refinesChain(v, "kinds", String(h.line.val)));
      const subjects = a.subject
        ? [isEntityName(a.subject) ? a.subject : resolvePrefix(a.subject, holdings(inst).keys())]
        : [...g.entities.keys(), ...holdings(inst).keys()];
      for (const r of seeks) {
        const sel = r.val.select as Record<string, string>;
        for (const s of subjects) {
          if (isEntityName(s)) {
            if (sel.kind && kindsOf(s).includes(sel.kind)) out.push({ ruling: r.id, subject: s, why: `is a ${sel.kind}` });
            if (sel.entity === `ath://${s}`) out.push({ ruling: r.id, subject: s, why: "is the entity it seeks" });
            continue;
          }
          const rec = recordView(inst, s)?.record;
          if (sel.origin && rec?.origins?.some((o) => (o.producer as { tool?: string } | undefined)?.tool === sel.origin))
            out.push({ ruling: r.id, subject: s, why: `came from ${sel.origin}` });
          if (
            sel.form &&
            [...scopesOf(rec?.scopes)].some(({ scope }) => [scope.form].flat().some((f) => refinesChain(v, "forms", f).includes(sel.form!)))
          )
            out.push({ ruling: r.id, subject: s, why: `has a ${sel.form}` });
          if (sel.kind)
            for (const c of g.statuses.claims)
              if (kindsOf(c.entity).includes(sel.kind) && c.entries.some((e) => e.entry.anchor.includes(s))) {
                out.push({ ruling: r.id, subject: s, why: `evidences ${c.entity}, a ${sel.kind}` });
                break;
              }
        }
      }
      return { data: { relevant: out } };
    } finally {
      g.close();
    }
  },
  text: (d, io) => {
    for (const r of d.relevant) io.out(`${r.ruling.padEnd(4)} ${r.subject}  ${r.why}\n`);
  },
});
