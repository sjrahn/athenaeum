// layer.ts — `ath layer init|show|check`: make a layer, see the chain, check it.
import { existsSync, mkdirSync, readdirSync, writeFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { defineContract, z } from "../../contracts/index.ts";
import ledgerPassBrief from "../../templates/agents/ledger-pass.md" with { type: "file" };
import passAuthorBrief from "../../templates/agents/pass-author.md" with { type: "file" };
import claudeTemplate from "../../templates/CLAUDE.md" with { type: "file" };
import { openChain } from "../engine/context.ts";
import { type LayerConfig, loadChain, readConfig, serializeConfig, TREE_DIRS } from "../engine/layer/config.ts";
import { listSubjects, readSubject } from "../engine/layer/store.ts";
import { ontologyPin } from "../engine/ontology/hash.ts";
import { lintOntology } from "../engine/ontology/lint.ts";
import { loadOntology } from "../engine/ontology/load.ts";
import { defineCommand } from "../kit/define.ts";
import { AthError } from "../kit/errors.ts";
import { CONFIG_FILE } from "../kit/root.ts";

const GITIGNORE = `# ath's private state (history, locks, pass staging) and the byte store: never tracked
/.ath/
/corpus/bytes/
`;

export const layerInit = defineCommand({
  meta: {
    summary: "make a layer: athenaeum.yaml, ontology/ corpus/ ledger/, .ath/ (a foundation, or an extension of one)",
    tier: "write",
    mutating: true,
    examples: ["ath layer init ./foundation --name public", "ath layer init ./mine --name mine --extends ../foundation --tier private"],
  },
  contract: defineContract({
    key: "layer-init",
    args: z.object({
      path: z.string(),
      name: z.string().optional(),
      extends: z.string().optional(),
      tier: z.string().optional(),
      noAgents: z.boolean().default(false),
    }),
    argv: {
      positionals: [{ name: "path", required: true, help: "the directory to make (created if missing)" }],
      flags: {
        name: { type: "string", help: "display name (default: the directory's name)" },
        extends: { type: "string", metavar: "PATH", help: "the foundation this layer extends; absent → a foundation" },
        tier: { type: "string", help: "the tier an extension's lines carry (default private)" },
        noAgents: { type: "boolean", help: "skip CLAUDE.md and the .claude/agents briefs" },
      },
    },
    data: z.object({ root: z.string(), layer: z.string(), extends: z.string().nullable(), created: z.array(z.string()) }),
  }),
  async run(ctx, a) {
    const root = resolve(ctx.cwd, a.path);
    const cfgPath = join(root, CONFIG_FILE);
    if (existsSync(cfgPath)) throw new AthError("CONFLICT", `${cfgPath} already exists`);
    const config: LayerConfig = { successor: true, name: a.name ?? root.split("/").pop()!, layer: a.extends ? "extension" : "foundation" };
    if (a.extends) {
      const f = resolve(ctx.cwd, a.extends);
      readConfig(f); // must be a layer
      config.extends = relative(root, f) || ".";
      config.tier = a.tier ?? "private";
    } else if (a.tier) throw new AthError("USAGE", "a foundation has no tier: it is public by construction");
    const created: string[] = [];
    mkdirSync(root, { recursive: true });
    for (const d of Object.values(TREE_DIRS)) {
      mkdirSync(join(root, d), { recursive: true });
      created.push(`${d}/`);
    }
    mkdirSync(join(root, ".ath"), { recursive: true });
    writeFileSync(cfgPath, serializeConfig(config));
    created.push(CONFIG_FILE);
    const gi = join(root, ".gitignore");
    if (!existsSync(gi)) {
      writeFileSync(gi, GITIGNORE);
      created.push(".gitignore");
    }
    if (!a.noAgents) {
      const brief = join(root, "CLAUDE.md");
      if (!existsSync(brief)) {
        writeFileSync(brief, (await Bun.file(claudeTemplate).text()).replaceAll("{name}", config.name));
        created.push("CLAUDE.md");
      }
      const agents = join(root, ".claude", "agents");
      mkdirSync(agents, { recursive: true });
      for (const [file, src] of [
        ["pass-author.md", passAuthorBrief],
        ["ledger-pass.md", ledgerPassBrief],
      ] as const) {
        const dst = join(agents, file);
        if (existsSync(dst)) continue;
        writeFileSync(dst, await Bun.file(src).text());
        created.push(`.claude/agents/${file}`);
      }
    }
    loadChain(root); // the chain must resolve
    return { data: { root, layer: config.layer, extends: config.extends ?? null, created } };
  },
  text(d, io) {
    io.out(`${d.layer} at ${d.root}${d.extends ? ` extending ${d.extends}` : ""}\n`);
    for (const c of d.created) io.out(`  + ${c}\n`);
  },
});

const layerRow = z.object({
  root: z.string(),
  name: z.string(),
  layer: z.string(),
  tier: z.string().nullable(),
  terms: z.number(),
  artifacts: z.number(),
  concepts: z.number(),
});

export const layerShow = defineCommand({
  meta: { summary: "the chain bottom-up: each layer's root, kind, tier and counts; the ontology pin", tier: "read", mutating: false },
  contract: defineContract({
    key: "layer-show",
    args: z.object({}),
    argv: {},
    data: z.object({ layers: z.array(layerRow), ontology: z.string() }),
  }),
  async run(ctx) {
    const chain = openChain(ctx);
    const layers = chain.layers.map((l) => {
      const count = (d: string, suffix: string) =>
        existsSync(join(l.root, d)) ? readdirSync(join(l.root, d)).filter((f) => f.endsWith(suffix) && !f.startsWith("lineage")).length : 0;
      return {
        root: l.root,
        name: l.config.name,
        layer: l.config.layer,
        tier: l.config.tier ?? null,
        terms: count(TREE_DIRS.ontology, ".claims.jsonl"),
        artifacts: count(TREE_DIRS.corpus, ".claims.jsonl"),
        concepts: count(TREE_DIRS.ledger, ".claims.jsonl"),
      };
    });
    const pin = await ontologyPin(loadOntology(chain));
    return { data: { layers, ontology: pin } };
  },
  text(d, io) {
    for (const l of d.layers)
      io.out(
        `${l.layer.padEnd(10)} ${l.name.padEnd(16)} ${l.tier ?? "public"}  terms ${l.terms}  artifacts ${l.artifacts}  concepts ${l.concepts}  ${l.root}\n`,
      );
    io.out(`ontology   ${d.ontology}\n`);
  },
});

export const layerCheck = defineCommand({
  meta: {
    summary: "config sanity: the chain resolves, the ontology loads and lints, every subject file parses",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "layer-check",
    args: z.object({}),
    argv: {},
    data: z.object({ ok: z.boolean(), problems: z.array(z.string()) }),
  }),
  run(ctx) {
    const problems: string[] = [];
    const chain = openChain(ctx);
    try {
      const o = loadOntology(chain);
      for (const f of lintOntology(o)) problems.push(`ontology ${f.term}: ${f.code} ${f.msg}`);
    } catch (e) {
      problems.push((e as Error).message);
    }
    for (const kind of ["corpus", "ledger"] as const) {
      for (const id of listSubjects(chain, kind)) {
        try {
          readSubject(chain, kind, id);
        } catch (e) {
          problems.push((e as Error).message);
        }
      }
    }
    return { data: { ok: problems.length === 0, problems }, exitCode: problems.length ? 1 : 0 };
  },
  text(d, io) {
    if (d.ok) io.out("ok\n");
    for (const p of d.problems) io.out(`${p}\n`);
  },
});
