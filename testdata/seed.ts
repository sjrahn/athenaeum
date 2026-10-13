#!/usr/bin/env bun
// seed.ts — seed testdata/instance (a gitignored foundation layer) from testdata/exemplars.yaml: for each entry,
// locate the artifact's bytes (a source instance's corpus/artifacts/<ab>/<blake3>.* with --from, or the committed
// testdata/synthetic/<file>) and `ath ingest` them; a container's members become subjects on their own. Idempotent.
//
//   bun testdata/seed.ts [--from SOURCE_INSTANCE_ROOT]
import { existsSync, mkdirSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { parseArgs } from "node:util";

const HERE = dirname(Bun.fileURLToPath(import.meta.url));
const INSTANCE = join(HERE, "instance");
const ATH = join(HERE, "..", "ath", "src", "main.ts");

const { values } = parseArgs({ options: { from: { type: "string" } } });
const from = values.from ?? process.env.ATHENAEUM_ROOT;

interface Entry {
  blake3: string;
  mime: string;
  shape: string;
  note?: string;
  source: "direct" | "promoted" | "synthetic";
  file?: string;
  via?: { container: string; address: string };
}

const manifest = Bun.YAML.parse(readFileSync(join(HERE, "exemplars.yaml"), "utf8")) as Entry[];

function ath(args: string[]): { code: number; out: string; err: string } {
  const r = Bun.spawnSync(["bun", ATH, "--root", INSTANCE, ...args], { env: { ...process.env, ATH_ACTOR: "seed" }, stdout: "pipe", stderr: "pipe" });
  return { code: r.exitCode, out: r.stdout.toString(), err: r.stderr.toString() };
}

function sourceBytes(blake3: string): string | null {
  if (!from) return null;
  const dir = join(from, "corpus", "artifacts", blake3.slice(0, 2));
  if (!existsSync(dir)) return null;
  const f = readdirSync(dir).find((n) => n.startsWith(blake3));
  return f ? join(dir, f) : null;
}

if (!existsSync(join(INSTANCE, "athenaeum.yaml"))) {
  mkdirSync(INSTANCE, { recursive: true });
  const r = ath(["layer", "init", INSTANCE, "--name", "testdata"]);
  if (r.code !== 0) throw new Error(`layer init failed: ${r.err}`);
  // the regression ontology is the foundation's
  const r2 = Bun.spawnSync(["cp", "-r", join(HERE, "ontology", "."), join(INSTANCE, "ontology")]);
  if (r2.exitCode !== 0) throw new Error("could not copy the ontology");
}

let seeded = 0;
let skipped = 0;
let missing = 0;
for (const e of manifest) {
  const id = e.source === "promoted" ? e.via!.container : e.blake3;
  if (existsSync(join(INSTANCE, "corpus", `${id}.claims.jsonl`))) {
    skipped++;
    continue;
  }
  const path = e.source === "synthetic" ? resolve(HERE, e.file!) : sourceBytes(id);
  if (!path || !existsSync(path)) {
    console.error(`missing bytes for ${e.mime} ${id.slice(0, 12)}… (${e.source === "synthetic" ? e.file : "needs --from"})`);
    missing++;
    continue;
  }
  const r = ath(["ingest", path, "--origin", e.source === "synthetic" ? "synthetic" : "source-instance", "--via", "upload"]);
  if (r.code !== 0) {
    console.error(`ingest failed for ${id.slice(0, 12)}…: ${r.err.trim()}`);
    missing++;
    continue;
  }
  seeded++;
  console.log(`+ ${e.mime.padEnd(28)} ${id.slice(0, 12)}…${e.note ? `  ${e.note}` : ""}`);
}
console.log(`${seeded} seeded, ${skipped} already present, ${missing} missing`);
process.exitCode = missing ? 1 : 0;
