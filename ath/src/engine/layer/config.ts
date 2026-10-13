// config.ts — athenaeum.yaml under the successor contract (spec §2): a layer is a directory with the three trees, and
// an extension names its foundation. The chain is loaded bottom-up; the top layer is the only one written.
import { existsSync, readFileSync } from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { z } from "../../../contracts/index.ts";
import { AthError } from "../../kit/errors.ts";
import { CONFIG_FILE } from "../../kit/root.ts";

export const LayerConfig = z
  .object({
    name: z.string().min(1),
    /** `foundation` is public by construction; an `extension` carries its tier. */
    layer: z.enum(["foundation", "extension"]),
    /** The foundation this layer extends: a path (relative to this file) — pinned by commit later. */
    extends: z.string().optional(),
    /** The tier an extension's lines carry (absent on a foundation). */
    tier: z.string().optional(),
    /** Named audiences and the tiers each is granted (spec §12). */
    audiences: z.record(z.string(), z.array(z.string())).optional(),
    successor: z.literal(true),
  })
  .strict();
export type LayerConfig = z.infer<typeof LayerConfig>;

export interface Layer {
  root: string;
  config: LayerConfig;
  /** 0 = the bottom foundation. */
  depth: number;
}

export interface Chain {
  /** Bottom-up: foundation first, the written layer last. */
  layers: Layer[];
  top: Layer;
}

export const TREE_DIRS = { ontology: "ontology", corpus: "corpus", ledger: "ledger" } as const;

export function readConfig(root: string): LayerConfig {
  const p = join(root, CONFIG_FILE);
  if (!existsSync(p)) throw new AthError("CONFIG", `${p}: not found`);
  let raw: unknown;
  try {
    raw = Bun.YAML.parse(readFileSync(p, "utf8"));
  } catch (e) {
    throw new AthError("CONFIG", `${p}: ${(e as Error).message}`);
  }
  const r = LayerConfig.safeParse(raw);
  if (!r.success) {
    const why = r.error.issues.map((i) => `${i.path.map(String).join(".") || "(root)"}: ${i.message}`).join("; ");
    throw new AthError("CONFIG", `${p}: ${why} (a v52 instance is not a successor layer; see spec/successor.md §2)`);
  }
  if (r.data.layer === "extension" && !r.data.extends) throw new AthError("CONFIG", `${p}: an extension names what it extends`);
  if (r.data.layer === "foundation" && r.data.extends) throw new AthError("CONFIG", `${p}: a foundation extends nothing`);
  return r.data;
}

/** Load the chain from the top layer down; refuses cycles and missing foundations. */
export function loadChain(topRoot: string): Chain {
  const seen = new Set<string>();
  const ordered: Layer[] = [];
  let root = resolve(topRoot);
  for (;;) {
    if (seen.has(root)) throw new AthError("CONFIG", `layer chain cycles at ${root}`);
    seen.add(root);
    const config = readConfig(root);
    ordered.push({ root, config, depth: 0 });
    if (!config.extends) break;
    root = isAbsolute(config.extends) ? config.extends : resolve(dirname(join(root, CONFIG_FILE)), config.extends);
    if (!existsSync(root)) throw new AthError("CONFIG", `foundation not found: ${root} (named by ${ordered[ordered.length - 1]!.root})`);
  }
  ordered.reverse();
  ordered.forEach((l, i) => {
    l.depth = i;
  });
  return { layers: ordered, top: ordered[ordered.length - 1]! };
}

export function serializeConfig(c: LayerConfig): string {
  const lines = [
    "# athenaeum.yaml — this layer (spec/successor.md §2). TRACKED.",
    "#",
    "# A layer holds three trees of sorted JSONL claim files: ontology/ (terms), corpus/",
    "# (artifact subjects by blake3), ledger/ (concept subjects by slug). An extension",
    "# reads its foundation's trees and never writes them; a foundation is public.",
    `successor: true`,
    `name: ${JSON.stringify(c.name)}`,
    `layer: ${c.layer}`,
  ];
  if (c.extends) lines.push(`extends: ${JSON.stringify(c.extends)}`);
  if (c.tier) lines.push(`tier: ${c.tier}`);
  if (c.audiences) {
    lines.push("audiences:");
    for (const [k, v] of Object.entries(c.audiences)) lines.push(`  ${k}: [${v.join(", ")}]`);
  }
  return `${lines.join("\n")}\n`;
}
