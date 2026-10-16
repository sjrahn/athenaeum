#!/usr/bin/env bun
// seed.ts — seed testdata/instance (a gitignored foundation layer) from testdata/exemplars.yaml: for each entry,
// locate the artifact's bytes (testdata/regression/<file> for a `regression` entry, placed by hand; the committed
// testdata/synthetic/<file> for a `synthetic` one; or, with --from, a source instance's corpus/artifacts/<ab>/<blake3>.*)
// and `ath ingest` them; a container's members become subjects on their own. Idempotent.
//
//   bun testdata/seed.ts [--from SOURCE_INSTANCE_ROOT]
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { parseArgs } from "node:util";

const HERE = dirname(Bun.fileURLToPath(import.meta.url));
const INSTANCE = join(HERE, "instance");
const ATH = join(HERE, "..", "ath", "src", "main.ts");

const { values } = parseArgs({ options: { from: { type: "string" } } });
const from = values.from ?? process.env.ATHENAEUM_ROOT;

interface Entry {
  file: string;
  blake3: string;
  mime: string;
  root: string;
  shape: string;
  note?: string;
  source: "regression" | "synthetic";
}

const manifest = Bun.YAML.parse(readFileSync(join(HERE, "exemplars.yaml"), "utf8")) as Entry[];

function ath(args: string[]): { code: number; out: string; err: string } {
  const r = Bun.spawnSync(["bun", ATH, "--root", INSTANCE, ...args], { env: { ...process.env, ATH_ACTOR: "seed" }, stdout: "pipe", stderr: "pipe" });
  return { code: r.exitCode, out: r.stdout.toString(), err: r.stderr.toString() };
}

/** Where the entry's bytes are: the placed/committed file, else the source instance's artifact by blake3. */
function locate(e: Entry): string | null {
  const local = join(HERE, e.source === "synthetic" ? "synthetic" : "regression", e.file);
  if (existsSync(local)) return local;
  if (!from) return null;
  const dir = join(from, "corpus", "artifacts", e.blake3.slice(0, 2));
  if (!existsSync(dir)) return null;
  const f = readdirSync(dir).find((n) => n.startsWith(e.blake3));
  return f ? join(dir, f) : null;
}

if (!existsSync(join(INSTANCE, "athenaeum.yaml"))) {
  mkdirSync(INSTANCE, { recursive: true });
  const r = ath(["layer", "init", INSTANCE, "--name", "testdata"]);
  if (r.code !== 0) throw new Error(`layer init failed: ${r.err}`);
  // the regression ontology is the foundation's (path.join drops a trailing "/.", so cp -r would nest the directory)
  cpSync(join(HERE, "ontology"), join(INSTANCE, "ontology"), { recursive: true });
  if (!existsSync(join(INSTANCE, "ontology", "html.claims.jsonl"))) throw new Error("the ontology did not copy");
}

let seeded = 0;
let skipped = 0;
let missing = 0;
for (const e of manifest) {
  if (existsSync(join(INSTANCE, "corpus", `${e.blake3}.claims.jsonl`))) {
    skipped++;
    continue;
  }
  const path = locate(e);
  if (!path) {
    console.error(`missing bytes for ${e.mime} ${e.blake3.slice(0, 12)}… (${e.source}/${e.file}${e.source === "regression" ? ", or --from" : ""})`);
    missing++;
    continue;
  }
  const r = ath(["ingest", path, "--origin", e.source === "synthetic" ? "synthetic" : "source-instance", "--via", "upload"]);
  if (r.code !== 0) {
    console.error(`ingest failed for ${e.blake3.slice(0, 12)}…: ${r.err.trim()}`);
    missing++;
    continue;
  }
  seeded++;
  console.log(`+ ${e.mime.padEnd(28)} ${e.blake3.slice(0, 12)}… → ${e.root}${e.note ? `  (${e.shape})` : ""}`);
}
console.log(`${seeded} seeded, ${skipped} already present, ${missing} missing`);
process.exitCode = missing ? 1 : 0;
