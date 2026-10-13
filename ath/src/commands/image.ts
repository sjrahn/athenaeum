// image.ts — `ath image words <blake3>`: tesseract's proposal for a raster, as claim lines a pass may stage (never a
// derivation; see D-ocr).
import { readFileSync } from "node:fs";
import { defineContract, z } from "../../contracts/index.ts";
import { openChain, openOntology, requireBlake3 } from "../engine/context.ts";
import { loadArtifact } from "../engine/corpus/derive.ts";
import { ocrWords, proposalLines } from "../engine/ops/image/words.ts";
import { defineCommand } from "../kit/define.ts";
import { AthError } from "../kit/errors.ts";

export const imageWords = defineCommand({
  meta: {
    summary: "image.words@1: tesseract's word boxes over a raster as proposal lines (label scopes with text readings) to stage on a pass",
    tier: "read",
    mutating: false,
    examples: ["ath image words <blake3> > proposal.jsonl", "ath image words <blake3> --json"],
    help: "A raster declares no derivation, so this is a proposal: a pass stages what it accepts (ath claims append), and L7 lists every image reading for inspection. Needs tesseract on PATH.",
  },
  contract: defineContract({
    key: "image-words",
    args: z.object({ subject: z.string(), term: z.string().default("label") }),
    argv: {
      positionals: [{ name: "subject", required: true }],
      flags: { term: { type: "string", help: "the term each OCR line manifests (default label)" } },
    },
    data: z.object({
      subject: z.string(),
      engine: z.string(),
      width: z.number(),
      height: z.number(),
      lines: z.array(z.object({ bbox: z.array(z.number()), text: z.string(), conf: z.number() })),
      proposal: z.array(z.record(z.string(), z.unknown())),
    }),
  }),
  async run(ctx, a) {
    const chain = openChain(ctx);
    const o = openOntology(chain);
    const art = await loadArtifact(chain, o, requireBlake3(a.subject), { bytes: false });
    if (!art.bytesPath) throw new AthError("NOT_FOUND", `${art.blake3}: bytes are not resident in this chain`);
    if (!art.mime.startsWith("image/")) throw new AthError("USAGE", `${art.blake3} is ${art.mime}, not a raster`);
    const res = ocrWords(new Uint8Array(readFileSync(art.bytesPath)), art.mime);
    return {
      data: {
        subject: art.blake3,
        engine: res.engine,
        width: res.width,
        height: res.height,
        lines: res.lines.map((l) => ({
          bbox: [...l.bbox],
          text: l.text,
          conf: Math.round((l.words.reduce((s, w) => s + w.conf, 0) / l.words.length) * 10) / 10,
        })),
        proposal: proposalLines(res, a.term),
      },
    };
  },
  text(d, io) {
    for (const l of d.proposal) io.out(`${JSON.stringify(l)}\n`);
  },
});
