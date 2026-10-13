// resolve.ts — `ath resolve <corpus://…?at[&aspect]>`: the bytes at an address, the derivation surface, or the stored
// reading; to stdout or a file.
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { defineContract, z } from "../../contracts/index.ts";
import { openChain, openOntology } from "../engine/context.ts";
import { loadArtifact } from "../engine/corpus/derive.ts";
import { bytesAt, derivationAt } from "../engine/corpus/resolve.ts";
import { parseAnchor } from "../engine/model/evidence.ts";
import { defineCommand } from "../kit/define.ts";
import { AthError } from "../kit/errors.ts";

export const resolveCmd = defineCommand({
  meta: {
    summary: "what is at an address: the bytes (--bytes), the derivation surface (default), or the stored reading (--reading)",
    tier: "read",
    mutating: false,
    examples: [
      "ath resolve 'corpus://dd0a…?bytes=518950,518985'",
      "ath resolve 'corpus://1409…?row=3&col=10'",
      "ath resolve corpus://404d… --bytes --out tool03.pdf",
    ],
  },
  contract: defineContract({
    key: "resolve",
    args: z.object({
      anchor: z.string(),
      bytes: z.boolean().default(false),
      reading: z.boolean().default(false),
      out: z.string().optional(),
    }),
    argv: {
      positionals: [{ name: "anchor", required: true, help: "corpus://<blake3>?<at>[&text|&cells|&tex]" }],
      flags: { bytes: { type: "boolean" }, reading: { type: "boolean" }, out: { type: "string", metavar: "FILE" } },
    },
    data: z.object({
      anchor: z.string(),
      kind: z.string(),
      source: z.string(),
      length: z.number(),
      text: z.string().nullable(),
      out: z.string().nullable(),
    }),
  }),
  run(ctx, a) {
    const chain = openChain(ctx);
    const o = openOntology(chain);
    const anchor = a.anchor.startsWith("corpus://") ? a.anchor : `corpus://${a.anchor}`;
    const an = parseAnchor(anchor.includes("?") ? anchor : `${anchor}?whole`);
    const art = loadArtifact(chain, o, an.blake3);
    if (a.bytes) {
      const b = bytesAt(art, an.at);
      if (a.out) {
        writeFileSync(resolve(ctx.cwd, a.out), b);
        return { data: { anchor, kind: "bytes", source: art.bytesPath ?? "", length: b.length, text: null, out: resolve(ctx.cwd, a.out) } };
      }
      return {
        data: { anchor, kind: "bytes", source: art.bytesPath ?? "", length: b.length, text: new TextDecoder().decode(b), out: null },
      };
    }
    if (a.reading) {
      const s = art.table.get(an.at);
      const r = s?.readings.find((x) => x.stored && (!an.aspect || x.aspect === an.aspect));
      if (!r) throw new AthError("NOT_FOUND", `no stored reading at ${an.at}${an.aspect ? ` under ${an.aspect}` : ""}`);
      const text = typeof r.body === "string" ? r.body : JSON.stringify(r.body);
      return { data: { anchor, kind: "reading", source: r.rev, length: text.length, text, out: null } };
    }
    const d = derivationAt(art, an.at, an.aspect);
    if (!d) throw new AthError("NOT_FOUND", `no derivation surface at ${an.at} (${art.mime})`);
    return { data: { anchor, kind: "derivation", source: d.source, length: d.text.length, text: d.text, out: null } };
  },
  text(d, io) {
    if (d.out) io.out(`${d.length} bytes → ${d.out}\n`);
    else io.out(`${d.text ?? ""}\n`);
  },
});
