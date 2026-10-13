// lint.ts — `ath lint [<subject>…|--all]`: G1–G3, per-file and per-term lints over artifacts; G4 and the ledger
// file lints over concepts. A blocking finding is a verdict (exit 1).
import { defineContract, z } from "../../contracts/index.ts";
import { openChain, openOntology } from "../engine/context.ts";
import { loadArtifact } from "../engine/corpus/derive.ts";
import { listSubjects } from "../engine/layer/store.ts";
import { lintArtifact } from "../engine/lint/index.ts";
import { blocking, type Finding } from "../engine/lint/report.ts";
import { ontologyPin } from "../engine/ontology/hash.ts";
import { verifyLedger } from "../engine/verify.ts";
import { defineCommand } from "../kit/define.ts";
import { AthError } from "../kit/errors.ts";
import { kindOf } from "./claims.ts";

const finding = z.object({
  code: z.string(),
  severity: z.enum(["block", "soft", "list"]),
  subject: z.string(),
  at: z.string().optional(),
  msg: z.string(),
});

export const lint = defineCommand({
  meta: {
    summary: "lints: G1 unit · G2 tree · G3 cover · G4 cite, per file, per term; blocking findings exit 1",
    tier: "read",
    mutating: false,
    examples: ["ath lint dd0a7844…", "ath lint --all", "ath lint cdm-tool-03 --generic"],
  },
  contract: defineContract({
    key: "lint",
    args: z.object({
      subjects: z.array(z.string()).default([]),
      all: z.boolean().default(false),
      generic: z.boolean().default(false),
      file: z.boolean().default(false),
      term: z.boolean().default(false),
    }),
    argv: {
      positionals: [{ name: "subjects", variadic: true, help: "blake3s (artifacts) and slugs (concepts)" }],
      flags: { all: { type: "boolean" }, generic: { type: "boolean" }, file: { type: "boolean" }, term: { type: "boolean" } },
    },
    data: z.object({ findings: z.array(finding), blocking: z.number(), checked: z.number() }),
  }),
  async run(ctx, a) {
    const chain = openChain(ctx);
    const o = openOntology(chain);
    const pin = await ontologyPin(o);
    const artifacts: string[] = [];
    const concepts: string[] = [];
    if (a.all) {
      artifacts.push(...listSubjects(chain, "corpus"));
      concepts.push(...listSubjects(chain, "ledger"));
    } else for (const s of a.subjects) (kindOf(s) === "corpus" ? artifacts : concepts).push(s.replace(/^corpus:\/\//, "").split("?")[0]!);
    if (!artifacts.length && !concepts.length) throw new AthError("USAGE", "name subjects or pass --all");
    const findings: Finding[] = [];
    for (const id of artifacts)
      findings.push(...lintArtifact(loadArtifact(chain, o, id), pin, { generic: a.generic, file: a.file, term: a.term }));
    if (concepts.length && (!a.generic && !a.file && !a.term ? true : a.generic || a.file)) {
      const r = verifyLedger(chain, o, concepts);
      for (const c of r.concepts) findings.push(...c.findings);
    }
    return {
      data: { findings, blocking: blocking(findings).length, checked: artifacts.length + concepts.length },
      exitCode: blocking(findings).length ? 1 : 0,
    };
  },
  text(d, io) {
    for (const f of d.findings)
      io.out(
        `${f.severity === "block" ? "E" : f.severity === "soft" ? "W" : "I"} ${f.code.padEnd(10)} ${f.subject.slice(0, 16).padEnd(16)} ${(f.at ?? "").padEnd(44)} ${f.msg}\n`,
      );
    io.out(`${d.checked} subject${d.checked === 1 ? "" : "s"}: ${d.blocking} blocking, ${d.findings.length - d.blocking} other\n`);
  },
});
