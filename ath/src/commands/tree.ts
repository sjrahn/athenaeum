// tree.ts — `ath tree <blake3>` (the scope table in ord, stored and derived marked) and `ath tree at <blake3> <query>`
// (a positional or designated address → the intrinsic one).
import { defineContract, z } from "../../contracts/index.ts";
import { openChain, openOntology, requireBlake3 } from "../engine/context.ts";
import { resolveQuery } from "../engine/corpus/addressing.ts";
import { derivedLines, loadArtifact } from "../engine/corpus/derive.ts";
import { defineCommand } from "../kit/define.ts";

const scopeRow = z.object({
  at: z.string(),
  depth: z.number(),
  ord: z.number().nullable(),
  terms: z.array(z.string()),
  fields: z.record(z.string(), z.unknown()),
  derived: z.boolean(),
  reading: z.string().nullable(),
  preview: z.string().nullable(),
});

const treeData = z.object({
  subject: z.string(),
  root: z.string().nullable(),
  tree: z.string().nullable(),
  scopes: z.array(scopeRow),
  unreachable: z.array(z.string()),
  lines: z.array(z.record(z.string(), z.unknown())).optional(),
});

export const tree = defineCommand({
  meta: {
    summary: "the tree in ord: every scope with its terms, fields, placement and reading (derived or stored)",
    tier: "read",
    mutating: false,
    examples: ["ath tree dd0a7844…", "ath --json tree dd0a7844… --stored"],
  },
  contract: defineContract({
    key: "tree",
    args: z.object({
      subject: z.string(),
      stored: z.boolean().default(false),
      derived: z.boolean().default(false),
      depth: z.number().int().optional(),
      lines: z.boolean().default(false),
    }),
    argv: {
      positionals: [{ name: "subject", required: true }],
      flags: {
        stored: { type: "boolean", help: "only scopes a stored line sits at" },
        derived: { type: "boolean", help: "only derived scopes" },
        depth: { type: "number", help: "stop below this depth" },
        lines: { type: "boolean", help: "print the derived lines as they would be written" },
      },
    },
    data: treeData,
  }),
  run(ctx, a) {
    const chain = openChain(ctx);
    const o = openOntology(chain);
    const art = loadArtifact(chain, o, requireBlake3(a.subject));
    const depthOf = new Map<string, number>();
    const rows: z.infer<typeof scopeRow>[] = [];
    for (const s of art.table.walk()) {
      const depth = s.parent ? (depthOf.get(s.parent) ?? 0) + 1 : 0;
      depthOf.set(s.at, depth);
      if (a.depth !== undefined && depth > a.depth) continue;
      if (a.stored && s.derived) continue;
      if (a.derived && !s.derived) continue;
      const r = s.readings[0];
      const body = r ? (typeof r.body === "string" ? r.body : JSON.stringify(r.body)) : null;
      rows.push({
        at: s.at,
        depth,
        ord: s.ord,
        terms: s.terms,
        fields: s.fields,
        derived: s.derived,
        reading: r ? r.rev : null,
        preview: body ? body.slice(0, 80) : null,
      });
    }
    const data: z.infer<typeof treeData> = {
      subject: art.blake3,
      root: art.root,
      tree: art.tree,
      scopes: rows,
      unreachable: art.table.unreachable().map((s) => s.at),
    };
    if (a.lines) data.lines = [...art.table.scopes.values()].flatMap((s) => derivedLines(s));
    return { data };
  },
  text(d, io) {
    io.out(`corpus://${d.subject}  root ${d.root ?? "(none)"}  tree ${d.tree ?? "(none)"}\n`);
    for (const s of d.scopes) {
      const f = Object.keys(s.fields).length ? ` ${JSON.stringify(s.fields)}` : "";
      io.out(
        `${"  ".repeat(s.depth)}${s.derived ? "·" : "*"} ${s.terms.join("+") || "?"}${f}  ${s.at}${s.preview ? `  “${s.preview.replace(/\n/g, " ")}”` : ""}\n`,
      );
    }
    if (d.unreachable.length) io.out(`axis scopes (not in the walk): ${d.unreachable.length}\n`);
    for (const l of d.lines ?? []) io.out(`${JSON.stringify(l)}\n`);
  },
});

export const treeAt = defineCommand({
  meta: {
    summary: "resolve a positional (0/3/1) or designated (sec=5&para=6, post=4, col=Currency) address to its intrinsic at",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "tree-at",
    args: z.object({ subject: z.string(), query: z.string() }),
    argv: {
      positionals: [
        { name: "subject", required: true },
        { name: "query", required: true },
      ],
    },
    data: z.object({ subject: z.string(), query: z.string(), at: z.string(), terms: z.array(z.string()) }),
  }),
  run(ctx, a) {
    const chain = openChain(ctx);
    const o = openOntology(chain);
    const art = loadArtifact(chain, o, requireBlake3(a.subject));
    const at = resolveQuery(o, art.table, a.query);
    return { data: { subject: art.blake3, query: a.query, at, terms: art.table.get(at)?.terms ?? [] } };
  },
  text(d, io) {
    io.out(`${d.at}  (${d.terms.join("+")})\n`);
  },
});
