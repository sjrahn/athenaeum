// pass.ts — `ath pass open|list|sign|abandon` and `ath claims append`: a pass stages lines on an artifact and signs
// them in once the lints are clean (spec §10.1, D-staging).
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { defineContract, z } from "../../contracts/index.ts";
import { openChain, openOntology, requireBlake3 } from "../engine/context.ts";
import { loadArtifact } from "../engine/corpus/derive.ts";
import { abandonPass, commitPass, listPasses, openPass, readPass, stageLines, storedWithStaged } from "../engine/corpus/pass.ts";
import { subjectPath } from "../engine/layer/store.ts";
import { lintArtifact } from "../engine/lint/index.ts";
import { blocking } from "../engine/lint/report.ts";
import { sortLines } from "../engine/model/line.ts";
import { ontologyPin } from "../engine/ontology/hash.ts";
import { defineCommand } from "../kit/define.ts";
import { AthError } from "../kit/errors.ts";
import { writeAtomic } from "../lib/fs.ts";
import { parseJsonl, serializeJsonl } from "../lib/jsonl.ts";

export const passOpen = defineCommand({
  meta: {
    summary: "open a pass on an artifact: a staging file pinned to the current ontology; lines accumulate until signed",
    tier: "write",
    mutating: true,
    examples: ["ath pass open 404d090f… --by claude-opus-4-8 --verify claude-sonnet-5_3"],
  },
  contract: defineContract({
    key: "pass-open",
    args: z.object({ subject: z.string(), by: z.string(), verify: z.string(), note: z.string().optional(), with: z.string().optional() }),
    argv: {
      positionals: [{ name: "subject", required: true }],
      flags: {
        by: { type: "string", help: "the author" },
        verify: { type: "string", help: "the verifier (never the author)" },
        note: { type: "string" },
        with: { type: "string", help: "the container's pass this member pass rides with" },
      },
    },
    data: z.object({ subject: z.string(), id: z.string(), path: z.string(), ontology: z.string() }),
  }),
  async run(ctx, a) {
    if (a.by === a.verify) throw new AthError("CONFLICT", "a pass has one author and one verifier; they differ");
    const chain = openChain(ctx);
    const pin = await ontologyPin(openOntology(chain));
    const p = openPass(chain, requireBlake3(a.subject), {
      by: a.by,
      verify: a.verify,
      ontology: pin,
      date: ctx.clock.iso().slice(0, 10),
      note: a.note,
      with: a.with,
    });
    return { data: { subject: p.blake3, id: p.id, path: p.path, ontology: pin } };
  },
  text(d, io) {
    io.out(`${d.id} open on ${d.subject.slice(0, 12)}… pinned ${d.ontology}\n${d.path}\n`);
  },
});

export const passList = defineCommand({
  meta: { summary: "the open (staged) and signed passes on an artifact", tier: "read", mutating: false },
  contract: defineContract({
    key: "pass-list",
    args: z.object({ subject: z.string() }),
    argv: { positionals: [{ name: "subject", required: true }] },
    data: z.object({
      open: z.array(z.object({ id: z.string(), lines: z.number(), by: z.string(), verify: z.string(), ontology: z.string() })),
      signed: z.array(z.object({ id: z.string(), by: z.string(), verify: z.string(), ontology: z.string(), date: z.string() })),
    }),
  }),
  async run(ctx, a) {
    const chain = openChain(ctx);
    const id = requireBlake3(a.subject);
    const open = listPasses(chain, id).map((p) => ({
      id: p.id,
      lines: p.lines.length,
      by: String((p.pass.value as { by: string }).by),
      verify: String((p.pass.value as { verify: string }).verify),
      ontology: String((p.pass.value as { ontology: string }).ontology),
    }));
    const art = await loadArtifact(chain, openOntology(chain), id, { bytes: false });
    const signed = [...art.passes.values()].map((l) => {
      const v = l.value as { id: string; by: string; verify: string; ontology: string; date: string };
      return { id: v.id, by: v.by, verify: v.verify, ontology: v.ontology, date: v.date };
    });
    return { data: { open, signed } };
  },
  text(d, io) {
    for (const p of d.signed) io.out(`signed ${p.id}  ${p.by} / ${p.verify}  ${p.ontology}  ${p.date}\n`);
    for (const p of d.open) io.out(`open   ${p.id}  ${p.by} / ${p.verify}  ${p.ontology}  ${p.lines} staged lines\n`);
    if (!d.signed.length && !d.open.length) io.out("no passes\n");
  },
});

const finding = z.object({ code: z.string(), severity: z.string(), at: z.string().optional(), msg: z.string() });

export const passSign = defineCommand({
  meta: {
    summary: "lint the stored ∪ staged tree; on no blocking finding merge the staged lines into the claim file (corrections with lineage)",
    tier: "write",
    mutating: true,
    locks: ["corpus"],
    examples: ["ath pass sign 404d090f… p1 --walked"],
  },
  contract: defineContract({
    key: "pass-sign",
    args: z.object({ subject: z.string(), id: z.string(), walked: z.boolean().default(false) }),
    argv: {
      positionals: [
        { name: "subject", required: true },
        { name: "id", required: true },
      ],
      flags: { walked: { type: "boolean", help: "also write the walked line: structure over whole is complete" } },
    },
    data: z.object({
      subject: z.string(),
      id: z.string(),
      signed: z.boolean(),
      findings: z.array(finding),
      added: z.number(),
      corrected: z.number(),
      unchanged: z.number(),
    }),
  }),
  async run(ctx, a) {
    const chain = openChain(ctx);
    const o = openOntology(chain);
    const id = requireBlake3(a.subject);
    const p = readPass(chain, id, a.id);
    // lint stored ∪ staged by writing a scratch view: the artifact loader reads the chain, so stage into a temp copy of the top file
    const path = subjectPath(chain.top, "corpus", id);
    const original = readFileSync(path, "utf8");
    const merged = storedWithStaged(chain, id, p);
    if (a.walked) merged.push({ at: "whole", predicate: "walked", pass: a.id });
    writeAtomic(path, serializeJsonl(sortLines("corpus", merged)));
    let findings: { code: string; severity: string; at?: string; msg: string }[];
    try {
      const art = await loadArtifact(chain, o, id);
      findings = lintArtifact(art, await ontologyPin(o)).map((f) => ({ code: f.code, severity: f.severity, at: f.at, msg: f.msg }));
    } finally {
      writeAtomic(path, original);
    }
    const blockers = blocking(findings.map((f) => ({ ...f, subject: id, severity: f.severity as "block" })));
    if (blockers.length)
      return { data: { subject: id, id: a.id, signed: false, findings, added: 0, corrected: 0, unchanged: 0 }, exitCode: 1 };
    const r = commitPass(chain, id, a.id, { date: ctx.clock.iso().slice(0, 10), walked: a.walked });
    ctx.events.emit({
      kind: "pass.signed",
      level: "info",
      msg: `${a.id} signed: ${r.added} added, ${r.corrected} corrected, ${r.unchanged} unchanged`,
    });
    return { data: { subject: id, id: a.id, signed: true, findings, ...r } };
  },
  text(d, io) {
    for (const f of d.findings)
      io.out(
        `${f.severity === "block" ? "E" : f.severity === "soft" ? "W" : "I"} ${f.code.padEnd(10)} ${(f.at ?? "").padEnd(44)} ${f.msg}\n`,
      );
    io.out(
      d.signed
        ? `${d.id} signed: ${d.added} added, ${d.corrected} corrected, ${d.unchanged} unchanged\n`
        : `${d.id} not signed: ${d.findings.filter((f) => f.severity === "block").length} blocking finding(s)\n`,
    );
  },
});

export const passAbandon = defineCommand({
  meta: { summary: "drop an open pass and its staged lines", tier: "write", mutating: true },
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
  run(ctx, a) {
    const chain = openChain(ctx);
    const id = requireBlake3(a.subject);
    abandonPass(chain, id, a.id);
    return { data: { subject: id, id: a.id } };
  },
  text(d, io) {
    io.out(`${d.id} abandoned\n`);
  },
});

export const claimsAppend = defineCommand({
  meta: {
    summary:
      "stage lines on an open pass (from a file or stdin); revs are stamped or checked; a repeated identity replaces the earlier staged line",
    tier: "write",
    mutating: true,
    examples: [
      "ath claims append 404d090f… --pass p1 --from testdata/passes/404d090f….p1.jsonl",
      "cat lines.jsonl | ath claims append 404d090f… --pass p1 --from -",
    ],
  },
  contract: defineContract({
    key: "claims-append",
    args: z.object({ subject: z.string(), pass: z.string(), from: z.string() }),
    argv: {
      positionals: [{ name: "subject", required: true }],
      flags: {
        pass: { type: "string", help: "the open pass id" },
        from: { type: "string", metavar: "FILE|-", help: "JSONL lines; - for stdin" },
      },
    },
    data: z.object({ subject: z.string(), pass: z.string(), staged: z.number(), replaced: z.number() }),
  }),
  async run(ctx, a) {
    const chain = openChain(ctx);
    const id = requireBlake3(a.subject);
    const text = a.from === "-" ? await Bun.stdin.text() : readFileSync(resolve(ctx.cwd, a.from), "utf8");
    const lines = parseJsonl(text, a.from);
    const r = await stageLines(chain, id, a.pass, lines);
    return { data: { subject: id, pass: a.pass, staged: r.staged, replaced: r.replaced } };
  },
  text(d, io) {
    io.out(`${d.staged} lines staged on ${d.pass}${d.replaced ? ` (${d.replaced} replaced earlier staged lines)` : ""}\n`);
  },
});
