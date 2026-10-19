// export.ts — `ath export markdown <subject>` and `ath export graph [<subject>]` (spec §15): the markdown proxy with the
// provenance chain beside it, and the graph projection as N-Quads — every term and entity line, every reading, scope
// and pass of a record, and never a ruling.

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { defineContract, z } from "@ath/contracts";
import { proxy } from "@ath/engine/export/markdown.ts";
import { entityQuads, type Quad, quadText, recordQuads, termQuads } from "@ath/engine/export/nquads.ts";
import { Parses } from "@ath/engine/formats/index.ts";
import { isEntityName, ownEntity } from "@ath/engine/graph/entity.ts";
import { accepted, rulingsOf } from "@ath/engine/graph/rulings.ts";
import { chain, containersIndex, holdings, ownEntities, ownRecords, recordView, resolvePrefix } from "@ath/engine/instance/instance.ts";
import { passOf } from "@ath/engine/pass/coverage.ts";
import { unreadUnits } from "@ath/engine/pass/reading-check.ts";
import { provenance } from "@ath/engine/testimony/testimony.ts";
import { termFile } from "@ath/engine/vocab/load.ts";
import { VOCABS } from "@ath/engine/vocab/terms.ts";
import { parseLines } from "@ath/kit/canonical.ts";
import { defineCommand } from "@ath/kit/define.ts";
import { AthError } from "@ath/kit/errors.ts";
import { resolver } from "./artifacts.ts";
import { custodyIndex, instanceOf, localStore } from "./context.ts";
import { viewer } from "./view.ts";

export const exportMarkdown = defineCommand({
  meta: {
    summary: "the markdown proxy of a record, its header and remainder, and its provenance beside it",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "export-markdown",
    args: z.object({ subject: z.string() }),
    argv: { positionals: [{ name: "subject", required: true }] },
    data: z.object({ hash: z.string(), markdown: z.string(), provenance: z.unknown() }),
  }),
  async run(ctx, a) {
    const inst = instanceOf(ctx);
    const index = custodyIndex(ctx);
    try {
      const res = resolver(inst, localStore(ctx), index);
      const vw = viewer(inst, res.resolve);
      const hash = resolvePrefix(a.subject, new Set([...holdings(inst).keys(), ...vw.containers.keys()]));
      const view = await vw.view(hash);
      if (!view.record) throw new AthError("NOT_FOUND", `${hash} has no record to export`);
      const acc = [...accepted(rulingsOf(inst))].filter((k) => k.startsWith(`${hash}|`)).map((k) => k.split("|")[1]!);
      let remainder: { units?: number; characters?: [number, number] } = {};
      const bytes = (await res.resolve(hash)).bytes;
      if (view.format.class === "rendered")
        remainder = {
          units: (
            await unreadUnits(
              view.record,
              view.format,
              new Parses(bytes),
              view.chrome.map((c) => c.at),
            )
          ).length,
        };
      const markdown = proxy({ hash, record: view.record, vocab: vw.vocab.vocab, accepted: acc, chrome: view.chrome, remainder });
      const containers = containersIndex(inst);
      const chainOf = provenance(
        hash,
        (h) => recordView(inst, h)?.record ?? null,
        (h) => containers.get(h) ?? [],
      );
      return { data: { hash, markdown, provenance: chainOf } };
    } finally {
      index.close();
    }
  },
  text(d, io) {
    io.out(d.markdown);
    io.out(`\n## Provenance\n\n\`\`\`json\n${JSON.stringify(d.provenance, null, 2)}\n\`\`\`\n`);
  },
});

export const exportGraph = defineCommand({
  meta: {
    summary: "the graph projection as N-Quads: terms, entities, and records' readings, scopes and passes; never rulings",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "export-graph",
    args: z.object({ subject: z.string().optional() }),
    argv: { positionals: [{ name: "subject", help: "one entity or artifact (default: the whole chain)" }] },
    data: z.object({ nquads: z.string(), statements: z.number() }),
  }),
  run(ctx, a) {
    const inst = instanceOf(ctx);
    const quads: Quad[] = [];
    const want = a.subject ? (isEntityName(a.subject) ? a.subject : resolvePrefix(a.subject, holdings(inst).keys())) : null;
    for (const x of chain(inst)) {
      if (!want)
        for (const v of VOCABS) {
          const dir = dirname(termFile(x, v, "x"));
          if (!existsSync(dir)) continue;
          for (const f of readdirSync(dir).sort()) {
            if (!f.endsWith(".jsonl")) continue;
            quads.push(...termQuads(v, f.slice(0, -6), parseLines(readFileSync(join(dir, f), "utf8"), f)));
          }
        }
      for (const n of ownEntities(x)) if (!want || want === n) quads.push(...entityQuads(n, x.config.id, ownEntity(x, n) ?? []));
      for (const h of ownRecords(x)) {
        if (want && want !== h) continue;
        const r = recordView(inst, h)?.record;
        if (r && (r.readings || r.scopes || r.passes)) quads.push(...recordQuads(h, x.config.id, r, (w) => passOf(r, w)));
      }
    }
    const nquads = quads.map(quadText).join("\n") + (quads.length ? "\n" : "");
    return { data: { nquads, statements: quads.length } };
  },
  text: (d, io) => io.out(d.nquads),
});
