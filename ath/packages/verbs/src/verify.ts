// verify.ts — `ath verify [<subject>…]` (spec §19.5, §14): every entry's binding state now (bound, held, flagged; a
// re-bind owed), every claim's status and its standing, the demand, and the stale passes. A flagged entry is a
// verdict (exit 1); a held one is demand. And `ath check [<subject>…] [--all]` (§17): the record checks over records,
// the vocabulary check, and over entities the sorts, standing, authorship, citation and per-file checks, and over
// every record's origins the testimony contract.
import { existsSync, readFileSync } from "node:fs";
import { defineContract, z } from "@ath/contracts";
import { type Finding, recordChecks } from "@ath/engine/checks/record.ts";
import { authorshipProblem, isEntityName, ownEntity, serializeEntity } from "@ath/engine/graph/entity.ts";
import { standing } from "@ath/engine/graph/status.ts";
import { entityNames, entityPath, holdings, ownRecords, resolvePrefix } from "@ath/engine/instance/instance.ts";
import { checkContract } from "@ath/engine/testimony/testimony.ts";
import { vocabularyCheck } from "@ath/engine/vocab/check.ts";
import { defineCommand } from "@ath/kit/define.ts";
import { instanceOf } from "./context.ts";
import { FIXED, kindsOfEntity, sortsProblems } from "./entity-pass.ts";
import { openGraph } from "./graph.ts";

const entryRow = z.object({
  anchor: z.string(),
  state: z.string(),
  reason: z.string().optional(),
  rebind: z.boolean().optional(),
  standing: z.string().optional(),
});
const claimRow = z.object({ entity: z.string(), pred: z.string(), val: z.unknown(), status: z.string(), entries: z.array(entryRow) });

export const verifyCommand = defineCommand({
  meta: { summary: "bindings, status, demand and stale passes; a flagged entry is a verdict", tier: "read", mutating: false },
  contract: defineContract({
    key: "verify",
    args: z.object({ subjects: z.array(z.string()).default([]) }),
    argv: { positionals: [{ name: "subjects", variadic: true, help: "entities, or artifacts their claims cite (default: all)" }] },
    data: z.object({
      claims: z.array(claimRow),
      demand: z.array(
        z.object({
          kind: z.string(),
          subject: z.string(),
          detail: z.string(),
          ruling: z.string().optional(),
          deferred: z.string().optional(),
        }),
      ),
      counts: z.record(z.string(), z.number()),
      rounds: z.number(),
    }),
  }),
  async run(ctx, a) {
    const inst = instanceOf(ctx);
    const g = await openGraph(ctx, inst);
    try {
      const want = a.subjects.map((s) => (isEntityName(s) ? s : resolvePrefix(s, holdings(inst).keys())));
      const keep = (entity: string, anchors: string[]) =>
        !want.length || want.includes(entity) || anchors.some((x) => want.some((w) => x.includes(w)));
      const claims = g.statuses.claims
        .filter((c) =>
          keep(
            c.entity,
            c.entries.map((e) => e.entry.anchor),
          ),
        )
        .map((c) => ({
          entity: c.entity,
          pred: c.pred,
          val: c.val,
          status: g.statuses.status.get(c.key) ?? "unsupported",
          entries: c.entries.map((e) => ({
            anchor: e.entry.anchor,
            state: e.state.state,
            ...(e.state.reason ? { reason: e.state.reason } : {}),
            ...(e.state.rebind ? { rebind: true } : {}),
            ...(e.state.state === "bound" ? { standing: standing(g.statuses, c.entity, e.state.artifact) } : {}),
          })),
        }));
      const demand = g.demand.filter((d) => !want.length || want.includes(d.subject));
      const counts: Record<string, number> = {};
      for (const c of claims) for (const e of c.entries) counts[e.state] = (counts[e.state] ?? 0) + 1;
      return { data: { claims, demand, counts, rounds: g.statuses.rounds }, exitCode: counts.flagged ? 1 : 0 };
    } finally {
      g.close();
    }
  },
  text(d, io) {
    for (const c of d.claims) {
      io.out(`${c.status.padEnd(12)} ${c.entity} ${c.pred} ${JSON.stringify(c.val)}\n`);
      for (const e of c.entries)
        if (e.state !== "bound")
          io.out(`             ${e.state}${e.rebind ? " (re-bind owed)" : ""} ${e.anchor}${e.reason ? ` — ${e.reason}` : ""}\n`);
    }
    for (const x of d.demand)
      io.out(`demand ${x.kind.padEnd(11)} ${x.subject} ${x.detail}${x.deferred ? ` (deferred by ${x.deferred})` : ""}\n`);
    io.out(
      `${
        Object.entries(d.counts)
          .map(([k, n]) => `${n} ${k}`)
          .join(" · ") || "no evidence"
      }\n`,
    );
  },
});

const finding = z.object({ subject: z.string(), check: z.string(), level: z.string(), at: z.string().optional(), message: z.string() });

export const checkCommand = defineCommand({
  meta: {
    summary: "the checks of §17 over records, entities, testimony and the vocabulary; a blocking finding is a verdict",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "check",
    args: z.object({ subjects: z.array(z.string()).default([]), all: z.boolean().default(false) }),
    argv: {
      positionals: [{ name: "subjects", variadic: true }],
      flags: { all: { type: "boolean", help: "every record and entity of the chain, not this instance's alone" } },
    },
    data: z.object({ findings: z.array(finding), checked: z.object({ records: z.number(), entities: z.number() }) }),
  }),
  async run(ctx, a) {
    const inst = instanceOf(ctx);
    const g = await openGraph(ctx, inst);
    try {
      const v = g.viewer.vocab.vocab;
      const out: z.input<typeof finding>[] = [];
      const add = (subject: string, f: Finding) => out.push({ subject, ...f });
      const held = holdings(inst);
      const records = a.subjects.length
        ? a.subjects.filter((s) => !isEntityName(s)).map((s) => resolvePrefix(s, held.keys()))
        : a.all
          ? [...held.keys()]
          : ownRecords(inst);
      const entities = a.subjects.length
        ? a.subjects.filter(isEntityName)
        : a.all
          ? entityNames(inst)
          : [...g.entities.keys()].filter((e) => ownEntity(inst, e));
      for (const h of records) {
        const view = await g.viewer.view(h);
        if (!view.record) continue;
        for (const f of recordChecks(view.record, {
          vocab: v,
          format: view.format,
          intrinsics: view.intrinsics,
          matched: view.shape.matched,
        }))
          add(h, f);
        for (const [i, o] of (view.record.origins ?? []).entries()) {
          const c = checkContract(o, false);
          if (!c.ok)
            add(h, { check: "per testimony", level: "soft", message: `origins[${i}] would not be admitted now: ${c.problems.join("; ")}` });
        }
        if (view.record.intrinsics && !String(view.record.intrinsics.op).startsWith(`${view.format.name}.`))
          add(h, { check: "per file", level: "soft", message: `intrinsics by ${view.record.intrinsics.op}: stale, sweep it` });
      }
      for (const f of vocabularyCheck(g.viewer.vocab, inst.config.name, entityNames(inst)))
        add(`${f.vocab}/${f.term}`, { check: "sorts", level: "block", message: f.problem });
      const kindsOf = kindsOfEntity(inst);
      for (const e of entities) {
        const own = ownEntity(inst, e) ?? [];
        const p = entityPath(inst, e);
        if (existsSync(p) && readFileSync(p, "utf8") !== serializeEntity(own))
          add(e, { check: "per file", level: "block", message: "the file is not sorted by identity in canonical form: `ath sort` it" });
        const passes = new Set(own.filter((l) => l.pred === "pass").map((l) => String((l.val as { id: string }).id)));
        for (const l of own) {
          const pr = authorshipProblem(l, passes);
          if (pr) add(e, { check: "per file", level: "block", message: `${l.pred}: ${pr}` });
          if (l.pred !== "pass")
            for (const s of sortsProblems(l, v, (h) => held.has(h) || g.viewer.containers.has(h), kindsOf))
              add(e, { check: "sorts", level: "block", message: s });
          for (const ev of l.ev ?? [])
            if ("standing" in (ev as object))
              add(e, { check: "standing", level: "block", message: "an evidence entry carries no standing; standing is derived" });
          if (
            !FIXED.has(l.pred) &&
            l.pred !== "pass" &&
            v.properties.get(l.pred)?.some((x) => x.pred === "authority" && x.val === true) &&
            typeof l.val === "string" &&
            !held.has(l.val.slice(6))
          )
            add(e, { check: "standing", level: "block", message: `${l.pred} names ${l.val}, which the instance does not hold` });
        }
      }
      // citation: every anchor resolves, every quote is in its bound body or surface (§17.2), by verify
      for (const c of g.statuses.claims)
        if (!entities.length || entities.includes(c.entity))
          for (const x of c.entries)
            if (x.state.state === "flagged")
              add(c.entity, { check: "citation", level: "block", message: `${c.pred}: ${x.entry.anchor} — ${x.state.reason}` });
      return {
        data: { findings: out, checked: { records: records.length, entities: entities.length } },
        exitCode: out.some((f) => f.level === "block") ? 1 : 0,
      };
    } finally {
      g.close();
    }
  },
  text(d, io) {
    for (const f of d.findings) io.out(`${f.level.padEnd(8)} ${f.check.padEnd(13)} ${f.subject}${f.at ? ` ${f.at}` : ""}: ${f.message}\n`);
    io.out(
      `checked ${d.checked.records} records and ${d.checked.entities} entities: ${d.findings.filter((f) => f.level === "block").length} blocking\n`,
    );
  },
});
