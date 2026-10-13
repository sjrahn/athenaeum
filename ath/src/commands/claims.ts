// claims.ts — `ath claims show|sort`: a subject's lines across the chain; the canonical rewrite.
import { defineContract, z } from "../../contracts/index.ts";
import { openChain } from "../engine/context.ts";
import { sortSubject } from "../engine/corpus/file.ts";
import { listSubjects, readSubject, type SubjectKind, unionView } from "../engine/layer/store.ts";
import { defineCommand } from "../kit/define.ts";
import { AthError } from "../kit/errors.ts";

const KINDS = ["corpus", "ledger", "ontology"] as const;

/** A subject id names its tree: a blake3 is corpus, else a ledger slug unless `--kind` says ontology. */
export function kindOf(id: string, kind?: string): SubjectKind {
  if (kind) {
    if (!KINDS.includes(kind as never)) throw new AthError("USAGE", `--kind must be one of ${KINDS.join(", ")}`);
    return kind as SubjectKind;
  }
  return /^[0-9a-f]{64}$/.test(id) ? "corpus" : "ledger";
}

export const claimsShow = defineCommand({
  meta: {
    summary: "a subject's lines in the chain (union view), each marked with its layer; --owner for the owner file",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "claims-show",
    args: z.object({
      subject: z.string(),
      kind: z.string().optional(),
      predicate: z.string().optional(),
      at: z.string().optional(),
      owner: z.boolean().default(false),
    }),
    argv: {
      positionals: [{ name: "subject", required: true, help: "a blake3 (corpus), a slug (ledger), or a term with --kind ontology" }],
      flags: {
        kind: { type: "string", help: "corpus · ledger · ontology" },
        predicate: { type: "string", help: "only this predicate" },
        at: { type: "string", help: "only lines at this address (corpus)" },
        owner: { type: "boolean", help: "the owner file (<blake3>.owner.jsonl)" },
      },
    },
    data: z.object({
      subject: z.string(),
      kind: z.string(),
      lines: z.array(z.object({ layer: z.string(), line: z.record(z.string(), z.unknown()) })),
    }),
  }),
  run(ctx, a) {
    const chain = openChain(ctx);
    const id = a.subject.replace(/^corpus:\/\//, "").split("?")[0]!;
    const kind = kindOf(id, a.kind);
    let lines = unionView(kind, readSubject(chain, kind, id, a.owner));
    if (!lines.length) throw new AthError("NOT_FOUND", `${id}: no ${kind} subject in the chain`);
    if (a.predicate) lines = lines.filter((l) => l.line.predicate === a.predicate);
    if (a.at) lines = lines.filter((l) => l.line.at === a.at);
    return { data: { subject: id, kind, lines: lines.map((l) => ({ layer: l.layer.config.name, line: l.line })) } };
  },
  text(d, io) {
    for (const l of d.lines) io.out(`${JSON.stringify(l.line)}\n`);
  },
});

export const claimsSort = defineCommand({
  meta: {
    summary: "rewrite a subject's file (or every file with --all) in canonical order; idempotent",
    tier: "write",
    mutating: true,
    locks: ["corpus", "ledger"],
  },
  contract: defineContract({
    key: "claims-sort",
    args: z.object({ subjects: z.array(z.string()).default([]), all: z.boolean().default(false), kind: z.string().optional() }),
    argv: {
      positionals: [{ name: "subjects", variadic: true }],
      flags: { all: { type: "boolean", help: "every corpus and ledger subject in the top layer" }, kind: { type: "string" } },
    },
    data: z.object({ files: z.array(z.object({ path: z.string(), changed: z.boolean() })) }),
  }),
  run(ctx, a) {
    const chain = openChain(ctx);
    const targets: { kind: SubjectKind; id: string }[] = [];
    if (a.all) for (const kind of ["corpus", "ledger"] as const) for (const id of listSubjects(chain, kind)) targets.push({ kind, id });
    else for (const s of a.subjects) targets.push({ kind: kindOf(s, a.kind), id: s });
    if (!targets.length) throw new AthError("USAGE", "name subjects or pass --all");
    const files = targets.map((t) => sortSubject(chain, t.kind, t.id));
    return { data: { files } };
  },
  text(d, io) {
    for (const f of d.files) io.out(`${f.changed ? "~" : "="} ${f.path}\n`);
  },
});
