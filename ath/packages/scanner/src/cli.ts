#!/usr/bin/env bun

// ath-scan — the residence scanner CLI. (Binary name provisional; owner renames at taste.)
// Maintains an on-share blake3 "presented manifest" so corpus tooling can treat a large
// read-only share as a self-describing content-addressed residence without walking or
// hashing it over the wire. See README.md and MANIFEST-SCHEMA.md.

import { constants as fsConstants } from "node:fs";
import { access, stat } from "node:fs/promises";
import { join, resolve, sep } from "node:path";
import { parseArgs } from "node:util";
import { benchmark } from "./bench.ts";
import { type BytePathResolver, createUnraidResolver } from "./bytepath.ts";
import { blake3Factory } from "./hasher.ts";
import { ScanBusy } from "./lock.ts";
import { Logger, type LogLevel } from "./log.ts";
import {
  compact,
  DEFAULT_CONCURRENCY,
  DEFAULT_MAX_DELETE,
  DEFAULT_NATIVE_CONCURRENCY,
  DEFAULT_NATIVE_THRESHOLD,
  DELETE_FLOOR,
  DeletionRefused,
  dryRun,
  formatSummary,
  publishPending,
  type ScanOptions,
  scan,
} from "./scanner.ts";
import { DEFAULT_IGNORE_PATTERNS, MANIFEST_DIRNAME, MANIFEST_FILENAME, SCANNER_VERSION, SCHEMA_VERSION } from "./schema.ts";
import { StatusFile } from "./status.ts";
import { fileTestimony, observationOf } from "./testimony.ts";
import { parseTargets } from "./walk.ts";

const HELP = `ath-scan ${SCANNER_VERSION} — residence scanner (manifest schema v${SCHEMA_VERSION})

USAGE
  ath-scan <root> [options]           incremental scan (first run on a root = cold full pass)
  ath-scan <root> --bench             benchmark hash vs read throughput; write no manifest
  ath-scan <root> --compact           drop orphaned identities, VACUUM, publish
  ath-scan <root> --paths-from <file|->  targeted update: only the listed paths (one per line,
                                      relative to the root; a directory as its subtree; a path
                                      gone deletes its rows and those under it)
  ath-scan <root> --dry-run [...]     report what the run would hash, move and delete; hash,
                                      write and publish nothing
  ath-scan <root> --publish           publish the generations the state finished since the
                                      last publish (runs made with --no-publish); else nothing
  ath-scan <root> --testimony <path>  print what the published manifest observed of one file, as testimony

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
  --exclude <glob>       a path relative to the root to leave out (repeatable): "downloads/"
                         prunes that directory, "**/incomplete/" one at any depth, "**/*.part"
                         such files anywhere; honoured by full and targeted runs alike
  --no-publish           record the generation in the state without publishing it
  --max-delete <pct>     refuse a generation deleting more than this share of the paths the
                         manifest held (default ${DEFAULT_MAX_DELETE * 100}%, once more than ${DELETE_FLOOR} paths); nothing is written
  --allow-deletions      let this run past the deletion limit
  --status-file <path>   keep the run's progress as JSON in <path>, rewritten every few seconds
                         (put it on a RAM filesystem, e.g. /var/log on unRAID)
  --bench                benchmark only
  --compact              compact only
  --json                 emit the run summary / bench result as JSON on stdout
  --quiet | --verbose    log level
  --version | --help

EXIT CODES
  0  ok (a dry run: the run would be accepted)
  1  usage or error
  2  the scrub found corruption (the generation is still recorded and published)
  3  the deletion limit refused the generation, nothing written (a dry run: would refuse)
  4  another scan holds this manifest; nothing done`;

function die(msg: string): never {
  process.stderr.write(`error: ${msg}\n`);
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
  let st: Awaited<ReturnType<typeof stat>>;
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

const OPTIONS = {
  full: { type: "boolean", default: false },
  scrub: { type: "string" },
  concurrency: { type: "string" },
  bench: { type: "boolean", default: false },
  compact: { type: "boolean", default: false },
  testimony: { type: "string" },
  "manifest-dir": { type: "string" },
  "seed-from": { type: "string", multiple: true },
  b3sum: { type: "string" },
  "native-threshold": { type: "string" },
  "native-concurrency": { type: "string" },
  "byte-path": { type: "string" },
  ignore: { type: "string", multiple: true },
  "no-default-ignores": { type: "boolean", default: false },
  exclude: { type: "string", multiple: true },
  "paths-from": { type: "string" },
  "dry-run": { type: "boolean", default: false },
  publish: { type: "boolean", default: false },
  "no-publish": { type: "boolean", default: false },
  "max-delete": { type: "string" },
  "allow-deletions": { type: "boolean", default: false },
  "status-file": { type: "string" },
  json: { type: "boolean", default: false },
  quiet: { type: "boolean", default: false },
  verbose: { type: "boolean", default: false },
  help: { type: "boolean", default: false },
  version: { type: "boolean", default: false },
} as const;

async function main(): Promise<number> {
  let parsed: ReturnType<typeof parseArgs<{ allowPositionals: true; options: typeof OPTIONS }>>;
  try {
    parsed = parseArgs({
      args: process.argv.slice(2),
      allowPositionals: true,
      options: OPTIONS,
    });
  } catch (e) {
    die((e as Error).message);
  }
  const { values, positionals } = parsed;

  if (values.help) {
    process.stdout.write(`${HELP}\n`);
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
    values["native-concurrency"] !== undefined
      ? parseIntArg("native-concurrency", values["native-concurrency"], DEFAULT_NATIVE_CONCURRENCY, 1)
      : undefined;

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
    if (values.json) process.stdout.write(`${JSON.stringify(res)}\n`);
    return 0;
  }

  if (values.compact) {
    await compact(root, manifestDir, log);
    return 0;
  }

  if (values.publish) {
    const gen = await publishPending(root, manifestDir, log);
    if (values.json) process.stdout.write(`${JSON.stringify({ published: gen })}\n`);
    else process.stdout.write(gen === null ? "nothing to publish\n" : `published generation ${gen}\n`);
    return 0;
  }

  if (values.testimony !== undefined) {
    const o = observationOf(manifestDir, values.testimony);
    if (!o) die(`the published manifest lists no path ${values.testimony}`);
    process.stdout.write(fileTestimony(o));
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

  let targets: string[] | undefined;
  if (values["paths-from"] !== undefined) {
    const from = values["paths-from"];
    let text: string;
    try {
      text = from === "-" ? await Bun.stdin.text() : await Bun.file(from).text();
    } catch (e) {
      die(`--paths-from ${from}: ${(e as Error).message}`);
    }
    try {
      targets = parseTargets(text);
    } catch (e) {
      die((e as Error).message);
    }
  }
  let maxDelete = DEFAULT_MAX_DELETE;
  if (values["max-delete"] !== undefined) {
    const pct = Number(values["max-delete"].replace(/%$/, ""));
    if (!Number.isFinite(pct) || pct < 0 || pct > 100) die(`--max-delete is a percentage from 0 to 100 (got "${values["max-delete"]}")`);
    maxDelete = pct / 100;
  }

  const status = values["status-file"] ? new StatusFile(resolve(values["status-file"]), { root }) : undefined;
  const opts: ScanOptions = {
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
    excludes: values.exclude,
    bytePathResolver,
    targets,
    publish: !values["no-publish"],
    maxDelete,
    allowDeletions: values["allow-deletions"],
    status,
  };

  try {
    if (values["dry-run"]) {
      const report = await dryRun(opts);
      if (values.json) process.stdout.write(`${JSON.stringify(report)}\n`);
      else
        process.stdout.write(
          `dry run — generation ${report.generation} (${report.mode}) of ${root}\n` +
            `  files seen    ${report.filesSeen}\n  to hash       ${report.toHash}  (${report.bytesToHash} bytes)\n` +
            `  moved         ${report.moved}\n  migrated      ${report.migrated}\n  seeded        ${report.seeded}\n` +
            `  deleted       ${report.deleted}  (${report.deletedPrior} of the ${report.prior} paths held)\n` +
            `  skipped       ${report.skipped}\n  ignored       ${report.ignored}\n` +
            `  verdict       ${report.refused ? "the deletion limit would refuse this run" : "would run"}\n`,
        );
      return report.refused ? 3 : 0;
    }
    const summary = await scan(opts);
    if (values.json) process.stdout.write(`${JSON.stringify(summary)}\n`);
    else process.stdout.write(`${formatSummary(summary, root, { bytePathActive: !!bytePathResolver })}\n`);
    return summary.corrupt > 0 ? 2 : 0;
  } catch (e) {
    if (e instanceof DeletionRefused) {
      if (values.json)
        process.stdout.write(`${JSON.stringify({ refused: "deletions", deleted: e.deleted, prior: e.prior, maxDelete: e.maxDelete })}\n`);
      process.stderr.write(`error: ${e.message}\n`);
      return 3;
    }
    throw e;
  }
}

// Guarded so tests can import resolveSeedFromArg/assertNoSeedFromWithFull without triggering
// a real run (import.meta.main is true only when Bun invoked this file directly).
if (import.meta.main) {
  main()
    .then((code) => process.exit(code))
    .catch((e) => {
      if (e instanceof ScanBusy) {
        process.stderr.write(`busy: ${e.message}\n`);
        process.exit(4);
      }
      process.stderr.write(`fatal: ${e?.stack ?? String(e)}\n`);
      process.exit(1);
    });
}
