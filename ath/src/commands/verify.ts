// verify.ts — `ath verify [<slug>…|--all]`: every evidence entry bound against the corpus, every claim's derived
// status, the demand list, stale passes. A flagged entry is a verdict (exit 1).
import { defineContract, z } from "../../contracts/index.ts";
import { openChain, openOntology } from "../engine/context.ts";
import { loadArtifact } from "../engine/corpus/derive.ts";
import { listSubjects } from "../engine/layer/store.ts";
import { ontologyPin } from "../engine/ontology/hash.ts";
import { verifyLedger } from "../engine/verify.ts";
import { defineCommand } from "../kit/define.ts";
import { AthError } from "../kit/errors.ts";

const claimRow = z.object({
  subject: z.string(),
  predicate: z.string(),
  status: z.string(),
  why: z.string(),
  bindings: z.array(z.object({ state: z.string(), at: z.string(), why: z.string().optional() })),
});

export const verify = defineCommand({
  meta: {
    summary: "bindings (bound · held · flagged), derived status per claim, demand, stale passes",
    tier: "read",
    mutating: false,
    examples: ["ath verify --all", "ath verify g8board-post-3758863 --bindings", "ath verify --stale"],
  },
  contract: defineContract({
    key: "verify",
    args: z.object({
      subjects: z.array(z.string()).default([]),
      all: z.boolean().default(false),
      bindings: z.boolean().default(false),
      status: z.boolean().default(false),
      demand: z.boolean().default(false),
      stale: z.boolean().default(false),
    }),
    argv: {
      positionals: [{ name: "subjects", variadic: true }],
      flags: {
        all: { type: "boolean" },
        bindings: { type: "boolean" },
        status: { type: "boolean" },
        demand: { type: "boolean" },
        stale: { type: "boolean" },
      },
    },
    data: z.object({
      counts: z.object({
        concepts: z.number(),
        claims: z.number(),
        entries: z.number(),
        bound: z.number(),
        held: z.number(),
        flagged: z.number(),
        byStatus: z.record(z.string(), z.number()),
      }),
      claims: z.array(claimRow),
      demand: z.array(z.object({ kind: z.string(), subject: z.string(), detail: z.string() })),
      stale: z.array(z.object({ subject: z.string(), pass: z.string(), pinned: z.string() })),
      pin: z.string(),
    }),
  }),
  async run(ctx, a) {
    const chain = openChain(ctx);
    const o = openOntology(chain);
    const pin = await ontologyPin(o);
    if (!a.all && !a.subjects.length && !a.stale) throw new AthError("USAGE", "name concepts, pass --all, or --stale");
    const r =
      a.all || a.subjects.length
        ? await verifyLedger(chain, o, a.all ? undefined : a.subjects)
        : { concepts: [], counts: { concepts: 0, claims: 0, entries: 0, bound: 0, held: 0, flagged: 0, byStatus: {} } };
    const claims = r.concepts.flatMap((c) =>
      c.judged.map((j) => ({
        subject: c.concept.slug,
        predicate: j.claim.predicate,
        status: j.status,
        why: j.why,
        bindings: j.bindings.map((b) => ({ state: b.state, at: b.at, why: b.why })),
      })),
    );
    const demand = r.concepts.flatMap((c) => c.demand);
    const stale: { subject: string; pass: string; pinned: string }[] = [];
    if (a.stale || a.all) {
      for (const id of listSubjects(chain, "corpus")) {
        const art = await loadArtifact(chain, o, id, { bytes: false });
        for (const p of art.passes.values()) {
          const v = p.value as { id: string; ontology: string };
          if (v.ontology !== pin) stale.push({ subject: id, pass: v.id, pinned: v.ontology });
        }
      }
    }
    const bad = r.counts.flagged > 0 || stale.length > 0;
    return { data: { counts: r.counts, claims, demand, stale, pin }, exitCode: bad ? 1 : 0 };
  },
  text(d, io, ctx) {
    const all = !ctx.prog.includes("--");
    const c = d.counts;
    if (c.concepts)
      io.out(
        `${c.concepts} concepts · ${c.claims} claims · ${c.entries} entries: ${c.bound} bound, ${c.held} held, ${c.flagged} flagged · ${Object.entries(
          c.byStatus,
        )
          .map(([k, v]) => `${v} ${k}`)
          .join(", ")}\n`,
      );
    for (const cl of d.claims) {
      const flagged = cl.bindings.filter((b) => b.state !== "bound");
      if (flagged.length || all)
        io.out(
          `${cl.status.padEnd(12)} ${cl.subject} ${cl.predicate}${flagged.length ? `  ${flagged.map((b) => `${b.state} at ${b.at}: ${b.why ?? ""}`).join("; ")}` : ""}\n`,
        );
    }
    for (const dm of d.demand) io.out(`demand ${dm.kind.padEnd(8)} ${dm.subject}: ${dm.detail}\n`);
    for (const s of d.stale) io.out(`stale  ${s.subject.slice(0, 16)} pass ${s.pass} pinned ${s.pinned} (now ${d.pin})\n`);
  },
});
