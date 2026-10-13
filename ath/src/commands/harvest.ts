// harvest.ts — `ath harvest <blake3>`: the ontology's concept lines minted into the ledger for one artifact.
import { defineContract, z } from "../../contracts/index.ts";
import { openChain, openOntology, requireBlake3 } from "../engine/context.ts";
import { loadArtifact } from "../engine/corpus/derive.ts";
import { harvestArtifact, requireRoot, writeHarvest } from "../engine/ledger/harvest.ts";
import { ontologyPin } from "../engine/ontology/hash.ts";
import { defineCommand } from "../kit/define.ts";

export const harvest = defineCommand({
  meta: {
    summary: "mint concepts and claims from the term's concept lines over one artifact; evidence accrues on repeat",
    tier: "write",
    mutating: true,
    locks: ["ledger"],
    examples: ["ath harvest dd0a7844…", "ath harvest 1409369e… --dry-run", "ath harvest 1409369e… --term product"],
  },
  contract: defineContract({
    key: "harvest",
    args: z.object({ subject: z.string(), dryRun: z.boolean().default(false), term: z.string().optional() }),
    argv: {
      positionals: [{ name: "subject", required: true }],
      flags: { dryRun: { type: "boolean" }, term: { type: "string", help: "only concepts of this term" } },
    },
    data: z.object({
      subject: z.string(),
      by: z.string(),
      concepts: z.number(),
      claims: z.number(),
      entries: z.number(),
      written: z.array(z.string()),
      skipped: z.array(z.string()),
      dryRun: z.boolean(),
    }),
  }),
  async run(ctx, a) {
    const chain = openChain(ctx);
    const o = openOntology(chain);
    const art = await loadArtifact(chain, o, requireBlake3(a.subject));
    requireRoot(art);
    const pin = await ontologyPin(o);
    const { files, report } = harvestArtifact(art, pin, { onlyTerm: a.term });
    if (!a.dryRun) writeHarvest(chain, files, report);
    else report.skipped.push(...files.keys());
    ctx.events.emit({
      kind: "harvest.done",
      level: "info",
      msg: `${report.concepts} concepts, ${report.claims} claims, ${report.entries} entries${a.dryRun ? " (dry run)" : ""}`,
    });
    return { data: { subject: art.blake3, by: `harvest:${art.root}@${pin.slice(3, 9)}`, ...report, dryRun: a.dryRun } };
  },
  text(d, io) {
    io.out(
      `${d.concepts} concepts · ${d.claims} claims · ${d.entries} entries${d.dryRun ? " (dry run, nothing written)" : ` · ${d.written.length} files written, ${d.skipped.length} unchanged`}\n`,
    );
    for (const s of d.written.slice(0, 20)) io.out(`  + ${s}\n`);
    if (d.written.length > 20) io.out(`  … ${d.written.length - 20} more\n`);
  },
});
