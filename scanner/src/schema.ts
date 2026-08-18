// The presented-manifest schema — the cross-language contract between the TypeScript
// scanner (writer) and the Python corpus tooling (reader). See MANIFEST-SCHEMA.md for the
// prose specification; this file is its executable form (the SQL DDL lives in manifest.ts,
// next to the code that creates it, but SCHEMA_VERSION here is the single source of truth).
// Bump SCHEMA_VERSION on any incompatible change and record the migration in
// MANIFEST-SCHEMA.md.

import pkg from "../package.json" with { type: "json" };

export const SCHEMA_VERSION = 2;
export const SCANNER_VERSION: string = pkg.version;

export const MANIFEST_DIRNAME = ".athenaeum";
/** The scanner's private working state. WAL mode. Remote readers must never open this. */
export const STATE_FILENAME = "state.sqlite";
/** The published manifest: a checkpointed copy of state.sqlite, unveiled atomically. */
export const MANIFEST_FILENAME = "manifest.sqlite";

export type ScanMode = "cold" | "incremental" | "scrub" | "compact" | "bench";

/**
 * Content-identity state, one row per live `(dev, ino)`. Mirrors the `identities` table.
 * The four filesystem-identity numerics are native SQLite INTEGERs (int64) — mtime_ns
 * (~1.7e18) fits comfortably under 2^63, so schema v2 drops the decimal-string encoding
 * v1 needed to survive JSON's float-precision ceiling.
 */
export interface IdentityState {
  dev: bigint;
  ino: bigint;
  size: bigint;
  mtimeNs: bigint;
  blake3: string; // 64-hex lowercase (BLAKE3-256)
  generation: number;
}

/** A path → identity mapping. Mirrors the `paths` table. */
export interface PathState {
  dev: bigint;
  ino: bigint;
  generation: number;
}

/** Per-generation counts, embedded as `generations.summary_json` and printed at run end. */
export interface ScanSummary {
  mode: ScanMode;
  generation: number;
  filesSeen: number; // regular files walked
  hashed: number; // files hashed this run (new content-versions)
  moved: number; // path rows added referencing a PRE-EXISTING identity (rename / new hardlink; zero re-hash)
  migrated: number; // path rows carried onto a NEW (dev,ino) at an unchanged (size,mtimeNs); zero re-hash
  deleted: number; // path rows removed
  skipped: number; // files logged-and-skipped
  scrubbed: number; // files re-hashed by the scrub sampler
  corrupt: number; // scrub mismatches at a stable stat tuple
  bytesHashed: string; // decimal-string bigint — this is a JSON blob field (summary_json), not a
  // SQL column, so it keeps the v1 encoding: JSON numbers are still IEEE-754 doubles regardless
  // of what the SQL schema stores.
  elapsedMs: number;
}

/** In-run dedup key for hardlinked identities queued for hashing at most once per pass. */
export const identityKey = (dev: bigint, ino: bigint): string => `${dev}:${ino}`;
