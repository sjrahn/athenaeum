// The streaming hasher: a minimal two-method interface (update / digest) with a hash-wasm
// BLAKE3 implementation, PLUS an optional native b3sum leaf-swap for large files. Measured on
// the real deployment host (12900H): hash-wasm does ~58.77 MiB/s in-memory while the disk
// read path does ~159 MiB/s — the pipeline is hash-BOUND, not disk-bound as originally
// assumed, so a >=1MiB file pays real wall-clock for staying on WASM. `NativeHasher` is the
// leaf-swap this file's interface was always meant to support: spawn a real (rayon,
// multi-core) b3sum binary and let it read + hash the file itself. WASM remains the default
// and the only path for small files (spawn overhead isn't worth it below the threshold) and
// for hosts with no b3sum available — see `discoverNativeHasher`.

import { createBLAKE3, type IHasher } from "hash-wasm";
import { access, rm, writeFile } from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import type { Logger } from "./log.ts";

export interface Hasher {
  /** Feed a chunk. hash-wasm copies into WASM memory synchronously, so the caller may reuse the buffer. */
  update(chunk: Uint8Array): void;
  /** Finalize and return the lowercase hex digest. Single-use; discard after calling. */
  digest(): string;
}

export interface HasherFactory {
  readonly name: string;
  /** A fresh, initialized hasher for one file. */
  create(): Promise<Hasher>;
}

/** BLAKE3-256 via hash-wasm, in-process. */
export const blake3Factory: HasherFactory = {
  name: "hash-wasm/blake3",
  async create(): Promise<Hasher> {
    const h: IHasher = await createBLAKE3();
    h.init();
    return {
      update: (chunk) => h.update(chunk),
      digest: () => h.digest("hex"),
    };
  },
};

/**
 * Wraps a factory to count how many hashers it hands out — i.e. how many files were
 * actually hashed. Tests assert this stays at zero across renames and hardlink discovery.
 */
export function countingFactory(inner: HasherFactory): HasherFactory & { readonly count: number } {
  let count = 0;
  return {
    name: inner.name,
    get count() {
      return count;
    },
    async create() {
      count++;
      return inner.create();
    },
  };
}

// ── native b3sum: discovery, verification, and the whole-file hasher ─────────────────────

export interface NativeHasher {
  readonly name: string;
  readonly path: string;
  /** Hash a whole file by path. b3sum reads the file itself — there is no chunked-read loop
   * on this path, unlike the WASM `Hasher`'s update()/digest(). */
  hashFile(abspath: string): Promise<string>; // lowercase 64-hex digest
}

async function isExecutable(p: string): Promise<boolean> {
  try {
    await access(p, fsConstants.X_OK);
    return true;
  } catch {
    return false;
  }
}

async function runVersionCheck(path: string): Promise<boolean> {
  try {
    // env explicit: Bun.spawn does NOT read live process.env changes unless told to — it
    // snapshots at Bun's own startup otherwise. Without this, a real deployment's PATH/env is
    // still fine (nothing changes it at runtime), but it silently breaks anything that DOES
    // mutate process.env before spawning (this fixture-based test suite's failure injection).
    const proc = Bun.spawn([path, "--version"], { stdout: "ignore", stderr: "ignore", env: process.env });
    return (await proc.exited) === 0;
  } catch {
    return false;
  }
}

async function runB3sum(path: string, abspath: string): Promise<string> {
  const proc = Bun.spawn([path, "--no-names", abspath], { stdout: "pipe", stderr: "pipe", env: process.env });
  // stdout and stderr must both be drained concurrently with `exited`, in the same
  // Promise.all: b3sum writes to a pipe with a bounded OS buffer, so any invocation that
  // emits more than that on stderr (a warning per unreadable file, a verbose build) blocks
  // on write until something reads it. Waiting on `exited` first — or reading stderr only
  // after checking the exit code — leaves that read until after the process is already
  // stuck, deadlocking the pool worker forever. Draining unconditionally (success path
  // included) also releases the stderr stream/fd promptly instead of leaving it for GC.
  const [stdout, stderr, exitCode] = await Promise.all([
    new Response(proc.stdout).text(),
    new Response(proc.stderr).text(),
    proc.exited,
  ]);
  if (exitCode !== 0) {
    throw new Error(`b3sum exited ${exitCode}: ${stderr.trim() || "(no stderr)"}`);
  }
  const digest = stdout.trim().toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(digest)) {
    throw new Error(`b3sum produced unexpected output: ${JSON.stringify(stdout.slice(0, 200))}`);
  }
  return digest;
}

function makeNativeHasher(path: string): NativeHasher {
  return { name: `native/b3sum(${path})`, path, hashFile: (abspath) => runB3sum(path, abspath) };
}

/** A `b3sum` binary sitting beside the running executable (works for both `bun run
 * src/cli.ts` — dirname is the source tree — and the compiled single-file binary, where
 * dirname is wherever the operator dropped it — see README's b3sum deployment note). */
async function findB3sumBesideExecutable(): Promise<string | null> {
  const candidate = join(dirname(process.execPath), "b3sum");
  return (await isExecutable(candidate)) ? candidate : null;
}

const VERIFY_VECTOR = new TextEncoder().encode("ath-scan b3sum verification vector");

/**
 * Discover and verify a usable b3sum binary. Discovery order: `explicitPath` (--b3sum) wins;
 * else a file named `b3sum` beside the running executable; else `b3sum` on PATH; else none
 * (returns null — callers fall back to WASM-only hashing, logged once at info level).
 *
 * A found binary is verified once: `--version` must exit 0, and it must reproduce the WASM
 * implementation's BLAKE3 digest of a small known vector (written to a temp file, since
 * b3sum reads files, not stdin bytes here). Either check failing refuses the binary with a
 * warning and falls back to WASM — this never throws; a bad/missing/wrong b3sum degrades
 * gracefully rather than aborting the run.
 */
export async function discoverNativeHasher(explicitPath: string | undefined, log: Logger): Promise<NativeHasher | null> {
  const candidate = explicitPath ?? (await findB3sumBesideExecutable()) ?? Bun.which("b3sum");
  if (!candidate) {
    log.info("no b3sum binary found (checked --b3sum, alongside the executable, PATH) — hashing via WASM only");
    return null;
  }

  if (!(await runVersionCheck(candidate))) {
    log.warn(`b3sum at ${candidate} failed verification (\`--version\` didn't exit 0) — falling back to WASM`);
    return null;
  }

  const expected = await (async () => {
    const h = await blake3Factory.create();
    h.update(VERIFY_VECTOR);
    return h.digest();
  })();
  const tmp = join(tmpdir(), `ath-scan-b3sum-verify-${process.pid}-${Date.now()}`);
  const hasher = makeNativeHasher(candidate);
  try {
    await writeFile(tmp, VERIFY_VECTOR);
    const actual = await hasher.hashFile(tmp);
    if (actual !== expected) {
      log.warn(`b3sum at ${candidate} failed verification (digest mismatch on a known vector) — falling back to WASM`);
      return null;
    }
  } catch (e) {
    log.warn(`b3sum at ${candidate} failed verification (${(e as Error).message}) — falling back to WASM`);
    return null;
  } finally {
    await rm(tmp, { force: true }).catch(() => {});
  }

  log.info(`native b3sum verified at ${candidate}`);
  return hasher;
}
