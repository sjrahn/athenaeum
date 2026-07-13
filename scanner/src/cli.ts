#!/usr/bin/env bun
// ath-scan — the residence scanner CLI. (Binary name provisional; owner renames at taste.)
// Maintains an on-share blake3 "presented manifest" so corpus tooling can treat a large
// read-only share as a self-describing content-addressed residence without walking or
// hashing it over the wire. See README.md and MANIFEST-SCHEMA.md.

import { parseArgs } from "node:util";
import { resolve, join, sep } from "node:path";
import { stat } from "node:fs/promises";
import { MANIFEST_DIRNAME, SCANNER_VERSION, SCHEMA_VERSION } from "./schema.ts";
import { blake3Factory } from "./hasher.ts";
import { Logger, type LogLevel } from "./log.ts";
import { scan, compact, formatSummary, DEFAULT_CONCURRENCY } from "./scanner.ts";
import { benchmark } from "./bench.ts";

const HELP = `ath-scan ${SCANNER_VERSION} — residence scanner (manifest schema v${SCHEMA_VERSION})

USAGE
  ath-scan <root> [options]           incremental scan (first run on a root = cold full pass)
  ath-scan <root> --bench             benchmark hash vs read throughput; write no manifest
  ath-scan <root> --compact           fold the journal into a fresh snapshot

OPTIONS
  --full                 force a re-hash of every file (ignore the stat cache)
  --scrub <N>            re-hash N random files as a bit-rot check (mismatch => exit 2)
  --concurrency <K>      files hashed in parallel (default ${DEFAULT_CONCURRENCY}; spinning rust peaks at 2-4)
  --manifest-dir <path>  manifest location (default <root>/${MANIFEST_DIRNAME}); use when the
                         share is read-only to the scanner user
  --bench                benchmark only
  --compact              compact only
  --json                 emit the run summary / bench result as JSON on stdout
  --quiet | --verbose    log level
  --version | --help

EXIT CODES
  0 ok   1 usage/error   2 scrub found corruption`;

function die(msg: string): never {
  process.stderr.write("error: " + msg + "\n");
  process.exit(1);
}

function parseIntArg(name: string, raw: string | undefined, dflt: number): number {
  if (raw === undefined) return dflt;
  const n = Number(raw);
  if (!Number.isInteger(n) || n < 0) die(`--${name} must be a non-negative integer (got "${raw}")`);
  return n;
}

async function main(): Promise<number> {
  let parsed;
  try {
    parsed = parseArgs({
      args: process.argv.slice(2),
      allowPositionals: true,
      options: {
        full: { type: "boolean", default: false },
        scrub: { type: "string" },
        concurrency: { type: "string" },
        bench: { type: "boolean", default: false },
        compact: { type: "boolean", default: false },
        "manifest-dir": { type: "string" },
        json: { type: "boolean", default: false },
        quiet: { type: "boolean", default: false },
        verbose: { type: "boolean", default: false },
        help: { type: "boolean", default: false },
        version: { type: "boolean", default: false },
      },
    });
  } catch (e) {
    die((e as Error).message);
  }
  const { values, positionals } = parsed;

  if (values.help) {
    process.stdout.write(HELP + "\n");
    return 0;
  }
  if (values.version) {
    process.stdout.write(`ath-scan ${SCANNER_VERSION} (manifest schema v${SCHEMA_VERSION})\n`);
    return 0;
  }

  const rootArg = positionals[0];
  if (!rootArg) die("a <root> path is required (see --help)");
  const root = resolve(rootArg);
  try {
    const st = await stat(root);
    if (!st.isDirectory()) die(`root is not a directory: ${root}`);
  } catch {
    die(`root does not exist or is unreadable: ${root}`);
  }

  const level: LogLevel = values.quiet ? "quiet" : values.verbose ? "verbose" : "normal";
  const log = new Logger(level);
  const manifestDir = values["manifest-dir"] ? resolve(values["manifest-dir"]) : join(root, MANIFEST_DIRNAME);
  const factory = blake3Factory;

  if (values.bench) {
    const excludeAbs = manifestDir === root || manifestDir.startsWith(root + sep) ? manifestDir : null;
    const res = await benchmark(root, excludeAbs, factory, log);
    if (values.json) process.stdout.write(JSON.stringify(res) + "\n");
    return 0;
  }

  if (values.compact) {
    await compact(root, manifestDir, log);
    return 0;
  }

  const concurrency = parseIntArg("concurrency", values.concurrency, DEFAULT_CONCURRENCY);
  const scrub = parseIntArg("scrub", values.scrub, 0);

  const summary = await scan({
    root,
    manifestDir,
    factory,
    log,
    concurrency,
    full: values.full,
    scrub,
  });

  if (values.json) process.stdout.write(JSON.stringify(summary) + "\n");
  else process.stdout.write(formatSummary(summary, root) + "\n");

  return summary.corrupt > 0 ? 2 : 0;
}

main()
  .then((code) => process.exit(code))
  .catch((e) => {
    process.stderr.write("fatal: " + (e?.stack ?? String(e)) + "\n");
    process.exit(1);
  });
