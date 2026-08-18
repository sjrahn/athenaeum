#!/usr/bin/env bun
// ath-scan — the residence scanner CLI. (Binary name provisional; owner renames at taste.)
// Maintains an on-share blake3 "presented manifest" so corpus tooling can treat a large
// read-only share as a self-describing content-addressed residence without walking or
// hashing it over the wire. See README.md and MANIFEST-SCHEMA.md.

import { parseArgs } from "node:util";
import { resolve, join, sep } from "node:path";
import { stat, access } from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import { DEFAULT_IGNORE_PATTERNS, MANIFEST_DIRNAME, MANIFEST_FILENAME, SCANNER_VERSION, SCHEMA_VERSION } from "./schema.ts";
import { blake3Factory } from "./hasher.ts";
import { Logger, type LogLevel } from "./log.ts";
import { scan, compact, formatSummary, DEFAULT_CONCURRENCY, DEFAULT_NATIVE_THRESHOLD, DEFAULT_NATIVE_CONCURRENCY } from "./scanner.ts";
import { benchmark } from "./bench.ts";
import { createUnraidResolver, type BytePathResolver } from "./bytepath.ts";

const HELP = `ath-scan ${SCANNER_VERSION} — residence scanner (manifest schema v${SCHEMA_VERSION})

USAGE
  ath-scan <root> [options]           incremental scan (first run on a root = cold full pass)
  ath-scan <root> --bench             benchmark hash vs read throughput; write no manifest
  ath-scan <root> --compact           fold the journal into a fresh snapshot

OPTIONS
  --full                 force a re-hash of every file (ignore the stat cache AND all seeding —
                         trust nothing, verify everything)
  --scrub <N>            re-hash N random files as a bit-rot check (mismatch => exit 2)
  --concurrency <K>      files hashed in parallel (default ${DEFAULT_CONCURRENCY}; spinning rust peaks at 2-4)
  --manifest-dir <path>  manifest location (default <root>/${MANIFEST_DIRNAME}); use when the
                         share is read-only to the scanner user
  --seed-from <path>     adopt identities from another manifest.sqlite (a file path, or a
                         directory holding ${MANIFEST_DIRNAME}/${MANIFEST_FILENAME}) before scanning;
                         repeatable; errors with --full
  --b3sum <path>         native b3sum binary to use for large files (default: auto-discover
                         a file named "b3sum" beside this executable, then on PATH; WASM-only
                         if none is found or it fails verification)
  --native-threshold <bytes>  files at/above this size use native b3sum instead of in-process
                         WASM, when a b3sum is available (default ${DEFAULT_NATIVE_THRESHOLD})
  --native-concurrency <K>  concurrent native b3sum spawns (default ${DEFAULT_NATIVE_CONCURRENCY};
                         auto-scaled when --byte-path unraid is active and this flag is
                         omitted — see below); multi-disk arrays (e.g. unRAID) benefit from
                         4-8 since each hasher pins one spindle; b3sum is itself
                         CPU-multithreaded, so a pure-NVMe root rarely needs more than 2
  --byte-path <mode>     bypass a union-filesystem mount for hashing reads; only "unraid" is
                         accepted — reads via each file's system.LOCATION xattr-resolved
                         backing disk instead of /mnt/user, verified against the share-side
                         stat before every use; --native-concurrency auto-scales to the
                         number of distinct disks with queued work (min 2, max 8) unless set
                         explicitly; see README's "unRAID direct byte path" section
  --ignore <pattern>     extra basename to skip (repeatable); trailing "*" is a prefix match,
                         e.g. "foo*"; a default deny-list already covers filesystem-metadata
                         junk, matched dirs are pruned (never entered):
                         ${DEFAULT_IGNORE_PATTERNS.join(" ")}
  --no-default-ignores   drop the built-in deny-list above; --ignore patterns still apply
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

function parseIntArg(name: string, raw: string | undefined, dflt: number, min = 0): number {
  if (raw === undefined) return dflt;
  const n = Number(raw);
  if (!Number.isInteger(n) || n < min) {
    die(min > 0 ? `--${name} must be an integer >= ${min} (got "${raw}")` : `--${name} must be a non-negative integer (got "${raw}")`);
  }
  return n;
}

/**
 * Resolve one `--seed-from` argument to an absolute manifest.sqlite path. Accepts either a
 * manifest.sqlite file path directly, or a directory containing `${MANIFEST_DIRNAME}/${MANIFEST_FILENAME}`
 * (i.e. a scan root). Throws a plain Error (never calls die()/process.exit) so it's directly
 * unit-testable; main() is the only place that translates a thrown message into a die().
 */
export async function resolveSeedFromArg(raw: string): Promise<string> {
  const p = resolve(raw);
  let st;
  try {
    st = await stat(p);
  } catch {
    throw new Error(`--seed-from path does not exist: ${p}`);
  }
  if (st.isDirectory()) {
    const candidate = join(p, MANIFEST_DIRNAME, MANIFEST_FILENAME);
    try {
      await stat(candidate);
    } catch {
      throw new Error(`--seed-from directory has no ${MANIFEST_DIRNAME}/${MANIFEST_FILENAME}: ${p}`);
    }
    return candidate;
  }
  return p;
}

/** `--seed-from` + `--full` is a usage error: full means ignore every cache, including seeds. */
export function assertNoSeedFromWithFull(seedFrom: string[] | undefined, full: boolean): void {
  if (full && seedFrom && seedFrom.length > 0) {
    throw new Error("--full ignores every cache, including seeds");
  }
}

/**
 * Resolve `--b3sum <path>` to an absolute, executable path. An explicitly-named binary that
 * doesn't exist or isn't executable is a hard error (a typo'd flag should fail loudly, unlike
 * a verification failure at runtime — see discoverNativeHasher — which degrades to a WASM
 * fallback instead). Throws a plain Error so it's directly unit-testable, like resolveSeedFromArg.
 */
export async function resolveB3sumArg(raw: string): Promise<string> {
  const p = resolve(raw);
  try {
    await access(p, fsConstants.X_OK);
  } catch {
    throw new Error(`--b3sum path does not exist or is not executable: ${p}`);
  }
  return p;
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
        "seed-from": { type: "string", multiple: true },
        b3sum: { type: "string" },
        "native-threshold": { type: "string" },
        "native-concurrency": { type: "string" },
        "byte-path": { type: "string" },
        ignore: { type: "string", multiple: true },
        "no-default-ignores": { type: "boolean", default: false },
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

  let b3sumPath: string | undefined;
  if (values.b3sum) {
    try {
      b3sumPath = await resolveB3sumArg(values.b3sum);
    } catch (e) {
      die((e as Error).message);
    }
  }
  const nativeThresholdBytes = parseIntArg("native-threshold", values["native-threshold"], DEFAULT_NATIVE_THRESHOLD);
  // Left undefined (rather than defaulted here) when the flag wasn't given, so scan() can tell
  // "operator didn't ask for anything specific" apart from "operator asked for the default" —
  // that distinction is what lets --byte-path unraid auto-scale this instead of always 2.
  const nativeConcurrency =
    values["native-concurrency"] !== undefined ? parseIntArg("native-concurrency", values["native-concurrency"], DEFAULT_NATIVE_CONCURRENCY, 1) : undefined;

  let bytePathResolver: BytePathResolver | undefined;
  if (values["byte-path"] !== undefined) {
    if (values["byte-path"] !== "unraid") die(`--byte-path must be "unraid" (got "${values["byte-path"]}")`);
    try {
      bytePathResolver = createUnraidResolver(root);
    } catch (e) {
      die((e as Error).message);
    }
    log.info(`direct byte path: unraid`);
  }

  if (values.bench) {
    const excludeAbs = manifestDir === root || manifestDir.startsWith(root + sep) ? manifestDir : null;
    const res = await benchmark(root, excludeAbs, factory, log, { b3sumPath });
    if (values.json) process.stdout.write(JSON.stringify(res) + "\n");
    return 0;
  }

  if (values.compact) {
    await compact(root, manifestDir, log);
    return 0;
  }

  const concurrency = parseIntArg("concurrency", values.concurrency, DEFAULT_CONCURRENCY);
  const scrub = parseIntArg("scrub", values.scrub, 0);

  try {
    assertNoSeedFromWithFull(values["seed-from"], values.full);
  } catch (e) {
    die((e as Error).message);
  }
  const seedFrom: string[] = [];
  for (const raw of values["seed-from"] ?? []) {
    try {
      seedFrom.push(await resolveSeedFromArg(raw));
    } catch (e) {
      die((e as Error).message);
    }
  }

  const summary = await scan({
    root,
    manifestDir,
    factory,
    log,
    concurrency,
    full: values.full,
    scrub,
    seedFrom,
    b3sumPath,
    nativeThresholdBytes,
    nativeConcurrency,
    ignorePatterns: values.ignore,
    noDefaultIgnores: values["no-default-ignores"],
    bytePathResolver,
  });

  if (values.json) process.stdout.write(JSON.stringify(summary) + "\n");
  else process.stdout.write(formatSummary(summary, root, { bytePathActive: !!bytePathResolver }) + "\n");

  return summary.corrupt > 0 ? 2 : 0;
}

// Guarded so tests can import resolveSeedFromArg/assertNoSeedFromWithFull without triggering
// a real run (import.meta.main is true only when Bun invoked this file directly).
if (import.meta.main) {
  main()
    .then((code) => process.exit(code))
    .catch((e) => {
      process.stderr.write("fatal: " + (e?.stack ?? String(e)) + "\n");
      process.exit(1);
    });
}
