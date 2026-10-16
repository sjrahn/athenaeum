// ontology.ts — `ath ontology list|show|rules|hash|lint`: the terms, one term's lines and chain, a term's effective
// rules, the pin, the ontology lints.
import { defineContract, z } from "../../contracts/index.ts";
import { openChain, openOntology } from "../engine/context.ts";
import { parseOpRef } from "../engine/model/line.ts";
import { classOf, refinesChain } from "../engine/ontology/chain.ts";
import { effectiveRules } from "../engine/ontology/effective.ts";
import { harvestPin, ontologyPin } from "../engine/ontology/hash.ts";
import { lintOntology } from "../engine/ontology/lint.ts";
import { linesOf, toJson } from "../engine/ontology/load.ts";
import { opFor } from "../engine/ops/index.ts";
import { defineCommand } from "../kit/define.ts";
import { AthError } from "../kit/errors.ts";

export const ontologyList = defineCommand({
  meta: { summary: "every term with its root class, its parent and the layer that declares it", tier: "read", mutating: false },
  contract: defineContract({
    key: "ontology-list",
    args: z.object({ layer: z.string().optional() }),
    argv: { flags: { layer: { type: "string", help: "only terms declared in this layer (by name)" } } },
    data: z.object({
      terms: z.array(
        z.object({ term: z.string(), refines: z.string().nullable(), class: z.string().nullable(), layer: z.string(), lines: z.number() }),
      ),
    }),
  }),
  run(ctx, a) {
    const o = openOntology(openChain(ctx));
    const terms = [...o.terms.keys()]
      .sort()
      .map((t) => {
        const lines = o.terms.get(t)!;
        return {
          term: t,
          refines: (linesOf(o, t, "refines")[0]?.value as string | undefined) ?? null,
          class: classOf(o, t),
          layer: lines[0]!.layer.config.name,
          lines: lines.length,
        };
      })
      .filter((t) => !a.layer || t.layer === a.layer);
    return { data: { terms } };
  },
  text(d, io) {
    for (const t of d.terms)
      io.out(`${t.term.padEnd(24)} ${(t.refines ?? "-").padEnd(20)} ${(t.class ?? "-").padEnd(9)} ${t.layer.padEnd(12)} ${t.lines}\n`);
  },
});

export const ontologyShow = defineCommand({
  meta: { summary: "a term's lines and its refines chain", tier: "read", mutating: false },
  contract: defineContract({
    key: "ontology-show",
    args: z.object({ term: z.string() }),
    argv: { positionals: [{ name: "term", required: true }] },
    data: z.object({ term: z.string(), chain: z.array(z.string()), lines: z.array(z.record(z.string(), z.unknown())) }),
  }),
  run(ctx, a) {
    const o = openOntology(openChain(ctx));
    if (!o.terms.has(a.term)) throw new AthError("NOT_FOUND", `no term '${a.term}'`);
    return { data: { term: a.term, chain: refinesChain(o, a.term), lines: linesOf(o, a.term).map(toJson) } };
  },
  text(d, io) {
    io.out(`${d.chain.join(" → ")}\n`);
    for (const l of d.lines) io.out(`${JSON.stringify(l)}\n`);
  },
});

export const ontologyRules = defineCommand({
  meta: {
    summary: "the effective rules of a term (its chain's lines, most specific first) — what a scope manifesting it owes",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "ontology-rules",
    args: z.object({ terms: z.array(z.string()).min(1) }),
    argv: { positionals: [{ name: "terms", required: true, variadic: true, help: "one or more terms a scope manifests" }] },
    data: z.object({
      terms: z.array(z.string()),
      reads: z.string().nullable(),
      fields: z.array(z.record(z.string(), z.unknown())),
      expects: z.array(z.string()),
      owes: z.array(z.string()),
      conventions: z.array(z.string()),
      renders: z.record(z.string(), z.unknown()).nullable(),
      axes: z.array(z.string()).nullable(),
      tree: z.string().nullable(),
      derivation: z.string().nullable(),
      selects: z.number(),
      shapes: z.number(),
    }),
  }),
  run(ctx, a) {
    const o = openOntology(openChain(ctx));
    for (const t of a.terms) if (!o.terms.has(t)) throw new AthError("NOT_FOUND", `no term '${t}'`);
    const r = effectiveRules(o, a.terms);
    return {
      data: {
        terms: r.terms,
        reads: r.reads,
        fields: r.fields as Record<string, unknown>[],
        expects: r.expects,
        owes: r.owes,
        conventions: r.conventions,
        renders: r.renders,
        axes: r.axes,
        tree: r.tree,
        derivation: r.derivation,
        selects: r.selects.length,
        shapes: r.shapes.length,
      },
    };
  },
  text(d, io) {
    io.out(`terms       ${d.terms.join(" + ")}\n`);
    io.out(`reads       ${d.reads ?? "(none declared)"}\n`);
    for (const f of d.fields) io.out(`field       ${JSON.stringify(f)}\n`);
    if (d.expects.length) io.out(`expects     ${d.expects.join(", ")}\n`);
    if (d.owes.length) io.out(`owes        ${d.owes.join(", ")}\n`);
    for (const c of d.conventions) io.out(`convention  ${c}\n`);
    if (d.renders) io.out(`renders     ${JSON.stringify(d.renders)}\n`);
    if (d.axes) io.out(`axes        ${d.axes.join(", ")}\n`);
    if (d.tree) io.out(`tree        ${d.tree}\n`);
    if (d.derivation) {
      const r = parseOpRef(d.derivation);
      io.out(`derivation  ${d.derivation}${r && opFor(r.op) ? "" : "  (not an op of this engine)"}\n`);
    }
    if (d.selects || d.shapes) io.out(`derived by  ${d.selects} select, ${d.shapes} shape lines\n`);
  },
});

export const ontologyHash = defineCommand({
  meta: { summary: "the ontology pin (the hash every pass records) and the harvest pin", tier: "read", mutating: false },
  contract: defineContract({
    key: "ontology-hash",
    args: z.object({}),
    argv: {},
    data: z.object({ pin: z.string(), harvest: z.string(), terms: z.number() }),
  }),
  async run(ctx) {
    const o = openOntology(openChain(ctx));
    const pin = await ontologyPin(o);
    return { data: { pin, harvest: harvestPin(pin), terms: o.terms.size } };
  },
  text(d, io) {
    io.out(`${d.pin}  (${d.terms} terms; harvest pin ${d.harvest})\n`);
  },
});

export const ontologyLint = defineCommand({
  meta: {
    summary: "ontology-level lints: refines resolve, single-valued predicates, concept maps name select lines",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "ontology-lint",
    args: z.object({}),
    argv: {},
    data: z.object({ findings: z.array(z.object({ term: z.string(), code: z.string(), msg: z.string() })) }),
  }),
  run(ctx) {
    const o = openOntology(openChain(ctx));
    const findings = lintOntology(o);
    return { data: { findings }, exitCode: findings.length ? 1 : 0 };
  },
  text(d, io) {
    if (!d.findings.length) io.out("ok\n");
    for (const f of d.findings) io.out(`${f.code.padEnd(18)} ${f.term.padEnd(22)} ${f.msg}\n`);
  },
});
