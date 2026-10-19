// vocab.ts — `ath vocab list|show|rules|pin|check` and `ath vocab add|edit|remove` (spec §19.5, §11): the forms,
// shapes, kinds and properties as loaded across the chain; a term's lines; a scope's effective rules; the two pins;
// the vocabulary check (§17.4). Writing the vocabulary is the owner's, confirmed at a terminal, and runs the check
// first: a write that would leave a finding is refused. An extension writes its own files and never at an identity
// its base holds.
import { existsSync, readFileSync, rmSync } from "node:fs";
import { relative } from "node:path";
import { defineContract, z } from "@ath/contracts";
import { entityNames } from "@ath/engine/instance/instance.ts";
import { vocabularyCheck } from "@ath/engine/vocab/check.ts";
import { loadVocabulary, one, termFile } from "@ath/engine/vocab/load.ts";
import { effectiveRules } from "@ath/engine/vocab/rules.ts";
import { pin, serializeTerm, termIdentity, VOCABS, type Vocab } from "@ath/engine/vocab/terms.ts";
import { parseLines } from "@ath/kit/canonical.ts";
import { defineCommand } from "@ath/kit/define.ts";
import { AthError } from "@ath/kit/errors.ts";
import { writeAtomic } from "@ath/kit/fs.ts";
import { instanceOf } from "./context.ts";

const vocabArg = z.enum(["forms", "shapes", "kinds", "properties"]);
const finding = z.object({ vocab: z.string(), term: z.string(), problem: z.string() });

export const vocabList = defineCommand({
  meta: { summary: "the forms, shapes, kinds and properties, each with its definition", tier: "read", mutating: false },
  contract: defineContract({
    key: "vocab-list",
    args: z.object({ vocabulary: vocabArg.optional() }),
    argv: { positionals: [{ name: "vocabulary", help: "forms, shapes, kinds or properties (default: all)" }] },
    data: z.object({
      terms: z.array(
        z.object({
          vocab: z.string(),
          name: z.string(),
          definition: z.string().nullable(),
          refines: z.string().nullable(),
          lines: z.number(),
        }),
      ),
    }),
  }),
  run(ctx, a) {
    const { vocab } = loadVocabulary(instanceOf(ctx));
    const terms = (a.vocabulary ? [a.vocabulary] : VOCABS).flatMap((v) =>
      [...vocab[v].entries()]
        .sort(([x], [y]) => (x < y ? -1 : 1))
        .map(([name, ls]) => ({
          vocab: v,
          name,
          definition: (one(ls, "definition") as string) ?? null,
          refines: (one(ls, "refines") as string) ?? null,
          lines: ls.length,
        })),
    );
    return { data: { terms } };
  },
  text(d, io) {
    let last = "";
    for (const t of d.terms) {
      if (t.vocab !== last) io.out(`${t.vocab}\n`);
      last = t.vocab;
      io.out(`  ${t.name.padEnd(24)} ${t.refines ? `< ${t.refines}  ` : ""}${t.definition ?? ""}\n`);
    }
  },
});

export const vocabShow = defineCommand({
  meta: { summary: "a term's lines across the chain, sorted by identity", tier: "read", mutating: false },
  contract: defineContract({
    key: "vocab-show",
    args: z.object({ vocabulary: vocabArg, term: z.string() }),
    argv: {
      positionals: [
        { name: "vocabulary", required: true },
        { name: "term", required: true },
      ],
    },
    data: z.object({
      vocab: z.string(),
      term: z.string(),
      lines: z.array(z.object({ line: z.record(z.string(), z.unknown()), instance: z.string() })),
    }),
  }),
  run(ctx, a) {
    const lv = loadVocabulary(instanceOf(ctx));
    const ls = lv.vocab[a.vocabulary].get(a.term);
    if (!ls) throw new AthError("NOT_FOUND", `${a.vocabulary} has no term ${a.term}`);
    const h = lv.holders[a.vocabulary].get(a.term)!;
    return {
      data: {
        vocab: a.vocabulary,
        term: a.term,
        lines: parseLines(serializeTerm(ls), a.term).map((l) => ({ line: l, instance: h.get(termIdentity(l)) ?? "?" })),
      },
    };
  },
  text: (d, io) => {
    for (const l of d.lines) io.out(`${JSON.stringify(l.line)}  (${l.instance})\n`);
  },
});

export const vocabRules = defineCommand({
  meta: { summary: "the effective rules of a scope of the forms given, under a shape", tier: "read", mutating: false },
  contract: defineContract({
    key: "vocab-rules",
    args: z.object({ forms: z.array(z.string()).min(1), shape: z.string().optional() }),
    argv: {
      positionals: [{ name: "forms", variadic: true, required: true }],
      flags: { shape: { type: "string", help: "the artifact's shape, for its surface lines" } },
    },
    data: z.record(z.string(), z.unknown()),
  }),
  run(ctx, a) {
    const { vocab } = loadVocabulary(instanceOf(ctx));
    for (const f of a.forms) if (!vocab.forms.has(f)) throw new AthError("NOT_FOUND", `${f} is not a form`);
    return { data: effectiveRules(vocab, a.forms, [], a.shape ?? null) as unknown as Record<string, unknown> };
  },
  text: (d, io) => io.out(`${JSON.stringify(d, null, 2)}\n`),
});

export const vocabPin = defineCommand({
  meta: { summary: "the two pins: the corpus's forms and shapes, the graph's kinds and properties (§11.8)", tier: "read", mutating: false },
  contract: defineContract({ key: "vocab-pin", args: z.object({}), argv: {}, data: z.object({ corpus: z.string(), graph: z.string() }) }),
  async run(ctx) {
    const { vocab } = loadVocabulary(instanceOf(ctx));
    return { data: { corpus: await pin(vocab, "corpus"), graph: await pin(vocab, "graph") } };
  },
  text: (d, io) => io.out(`corpus ${d.corpus}\ngraph  ${d.graph}\n`),
});

export const vocabCheck = defineCommand({
  meta: { summary: "the vocabulary check (§17.4)", tier: "read", mutating: false },
  contract: defineContract({ key: "vocab-check", args: z.object({}), argv: {}, data: z.object({ findings: z.array(finding) }) }),
  run(ctx) {
    const inst = instanceOf(ctx);
    const findings = vocabularyCheck(loadVocabulary(inst), inst.config.name, entityNames(inst));
    return { data: { findings }, exitCode: findings.length ? 1 : 0 };
  },
  text(d, io) {
    for (const f of d.findings) io.out(`${f.vocab}/${f.term}: ${f.problem}\n`);
    if (!d.findings.length) io.out("the vocabulary checks clean\n");
  },
});

// ── writing the vocabulary ──────────────────────────────────────────────────────────────────────────────────────────

function parseLineArgs(xs: readonly string[]): Record<string, unknown>[] {
  return xs.map((x, i) => {
    let v: unknown;
    try {
      v = JSON.parse(x);
    } catch (e) {
      throw new AthError("USAGE", `line ${i + 1} is not JSON: ${(e as Error).message}`);
    }
    if (!v || typeof v !== "object" || Array.isArray(v) || typeof (v as { pred?: unknown }).pred !== "string" || !("val" in (v as object)))
      throw new AthError("USAGE", `line ${i + 1} is {"pred": …, "val": …}`);
    const keys = Object.keys(v as object);
    if (keys.some((k) => k !== "pred" && k !== "val"))
      throw new AthError("USAGE", `line ${i + 1}: a term line carries pred and val only (§6.1.2)`);
    return v as Record<string, unknown>;
  });
}

const write = (mode: "add" | "edit" | "remove") =>
  defineCommand({
    meta: {
      summary:
        mode === "add"
          ? "add a term, or lines to one; the vocabulary check runs first"
          : mode === "edit"
            ? "replace a term's lines at their identities; the check runs first"
            : "remove a term's lines, or the term; the check runs first",
      tier: "admin",
      mutating: true,
      locks: ["repository"],
      examples: [`ath vocab ${mode} forms heading '{"pred":"reads","val":"text"}'`],
    },
    contract: defineContract({
      key: `vocab-${mode}`,
      args: z.object({ vocabulary: vocabArg, term: z.string(), lines: z.array(z.string()).default([]) }),
      argv: {
        positionals: [
          { name: "vocabulary", required: true },
          { name: "term", required: true },
          { name: "lines", variadic: true, help: '{"pred":…,"val":…} each' },
        ],
      },
      data: z.object({ file: z.string(), lines: z.number(), removed: z.boolean() }),
    }),
    run(ctx, a) {
      const inst = instanceOf(ctx);
      const v = a.vocabulary as Vocab;
      const given = parseLineArgs(a.lines);
      if (mode !== "remove" && !given.length) throw new AthError("USAGE", `vocab ${mode} needs at least one line`);
      const path = termFile(inst, v, a.term);
      const own = existsSync(path) ? parseLines(readFileSync(path, "utf8"), relative(inst.root, path)) : [];
      const before = loadVocabulary(inst);
      if (mode === "edit" && !before.vocab[v].has(a.term)) throw new AthError("NOT_FOUND", `${v} has no term ${a.term}`);
      const ids = new Set(given.map(termIdentity));
      let next: Record<string, unknown>[];
      if (mode === "add") {
        const clash = given.find((l) => before.vocab[v].get(a.term)?.some((x) => termIdentity(x) === termIdentity(l)));
        if (clash) throw new AthError("CONFLICT", `${a.term} already has a line at ${termIdentity(clash).split("\u0000")[0]}; edit it`);
        next = [...own, ...given];
      } else if (mode === "edit") next = [...own.filter((l) => !ids.has(termIdentity(l))), ...given];
      else next = given.length ? own.filter((l) => !ids.has(termIdentity(l))) : [];
      // an extension writes nothing at an identity its base holds
      const baseHeld = before.holders[v].get(a.term);
      for (const l of given) {
        const holder = baseHeld?.get(termIdentity(l));
        if (holder && holder !== inst.config.name)
          throw new AthError(
            "CONFLICT",
            `${a.term}: ${termIdentity(l).split("\u0000")[0]} is the base ${holder}'s; an extension disagrees by demand on its base`,
          );
      }
      // the check runs over the vocabulary as it would be
      const after = loadVocabulary(inst);
      const merged = [...(before.vocab[v].get(a.term) ?? []).filter((l) => !own.some((o) => termIdentity(o) === termIdentity(l))), ...next];
      if (merged.length) after.vocab[v].set(a.term, merged);
      else after.vocab[v].delete(a.term);
      const findings = vocabularyCheck(after, inst.config.name).filter(
        (f) => !vocabularyCheck(before, inst.config.name).some((g) => g.term === f.term && g.problem === f.problem),
      );
      if (findings.length)
        throw new AthError(
          "CONFLICT",
          `the vocabulary check refuses it:\n${findings.map((f) => `  ${f.vocab}/${f.term}: ${f.problem}`).join("\n")}`,
          { findings },
        );
      if (next.length) writeAtomic(path, serializeTerm(next));
      else rmSync(path, { force: true });
      return { data: { file: relative(inst.root, path), lines: next.length, removed: !next.length } };
    },
    text: (d, io) => io.out(`${d.removed ? "removed" : "wrote"} ${d.file}${d.removed ? "" : ` (${d.lines} lines)`}\n`),
  });

export const vocabAdd = write("add");
export const vocabEdit = write("edit");
export const vocabRemove = write("remove");
