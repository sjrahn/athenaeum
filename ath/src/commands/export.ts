// export.ts — `ath export markdown <blake3>` (the proxy, a derivation) and `ath export nquads` (the RDF projection).
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { defineContract, z } from "../../contracts/index.ts";
import { openChain, openOntology, requireBlake3 } from "../engine/context.ts";
import { loadArtifact } from "../engine/corpus/derive.ts";
import { exportMarkdown } from "../engine/export/markdown.ts";
import { toNQuads } from "../engine/export/nquads.ts";
import { listSubjects, readSubject, unionView } from "../engine/layer/store.ts";
import { ontologyPin } from "../engine/ontology/hash.ts";
import { toJson } from "../engine/ontology/load.ts";
import { defineCommand } from "../kit/define.ts";
import { AthError } from "../kit/errors.ts";

export const exportMarkdownCmd = defineCommand({
  meta: {
    summary: "the markdown proxy of one artifact: the tree walked in ord through each term's render rule, every block addressed",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "export-markdown",
    args: z.object({ subject: z.string(), out: z.string().optional() }),
    argv: { positionals: [{ name: "subject", required: true }], flags: { out: { type: "string", metavar: "FILE" } } },
    data: z.object({ subject: z.string(), markdown: z.string(), out: z.string().nullable() }),
  }),
  async run(ctx, a) {
    const chain = openChain(ctx);
    const o = openOntology(chain);
    const art = await loadArtifact(chain, o, requireBlake3(a.subject));
    const inspected = unionView("corpus", readSubject(chain, "corpus", art.blake3, true)).map((l) => l.line);
    const md = exportMarkdown(art, { inspected, pin: await ontologyPin(o) });
    let out: string | null = null;
    if (a.out) {
      out = resolve(ctx.cwd, a.out);
      writeFileSync(out, md);
    }
    return { data: { subject: art.blake3, markdown: md, out } };
  },
  text(d, io) {
    io.out(d.out ? `${d.markdown.length} chars → ${d.out}\n` : d.markdown);
  },
});

export const exportNquads = defineCommand({
  meta: {
    summary: "the RDF projection: every line of the chain (or one subject) as an N-Quad with its attestation as the graph",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "export-nquads",
    args: z.object({ subject: z.string().optional(), plane: z.enum(["public", "owner"]).default("public"), out: z.string().optional() }),
    argv: {
      positionals: [{ name: "subject" }],
      flags: {
        plane: { type: "string", help: "public (the foundation) · owner (the whole chain)" },
        out: { type: "string", metavar: "FILE" },
      },
    },
    data: z.object({ quads: z.number(), out: z.string().nullable(), text: z.string().nullable() }),
  }),
  run(ctx, a) {
    const chain = openChain(ctx);
    const o = openOntology(chain);
    if (a.plane === "owner" && ctx.caller.profile !== "owner") throw new AthError("DENIED", "the owner plane needs the owner profile");
    const layers = a.plane === "owner" ? chain.layers : chain.layers.filter((l) => l.config.layer === "foundation");
    const parts: string[] = [];
    const emit = (tree: "corpus" | "ledger" | "ontology", id: string) => {
      const lines = readSubject(chain, tree, id)
        .filter((l) => layers.includes(l.layer))
        .map((l) => l.line);
      if (lines.length) parts.push(toNQuads(tree, id, lines));
    };
    if (a.subject) {
      const id = a.subject.replace(/^corpus:\/\//, "").split("?")[0]!;
      emit(/^[0-9a-f]{64}$/.test(id) ? "corpus" : o.terms.has(id) ? "ontology" : "ledger", id);
    } else {
      for (const t of [...o.terms.keys()].sort())
        parts.push(toNQuads("ontology", t, (o.terms.get(t) ?? []).filter((l) => layers.includes(l.layer)).map(toJson)));
      for (const id of listSubjects(chain, "corpus")) emit("corpus", id);
      for (const id of listSubjects(chain, "ledger")) emit("ledger", id);
    }
    const text = parts.join("");
    const quads = text.split("\n").filter(Boolean).length;
    if (a.out) {
      writeFileSync(resolve(ctx.cwd, a.out), text);
      return { data: { quads, out: resolve(ctx.cwd, a.out), text: null } };
    }
    return { data: { quads, out: null, text } };
  },
  text(d, io) {
    io.out(d.out ? `${d.quads} quads → ${d.out}\n` : (d.text ?? ""));
  },
});
