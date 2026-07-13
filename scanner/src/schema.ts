// The presented-manifest schema — the cross-language contract between the TypeScript
// scanner (writer) and the Python corpus tooling (reader). See MANIFEST-SCHEMA.md for the
// prose specification; this file is its executable form. Bump SCHEMA_VERSION on any
// incompatible change and record the migration in MANIFEST-SCHEMA.md.

import pkg from "../package.json" with { type: "json" };

export const SCHEMA_VERSION = 1;
export const SCANNER_VERSION: string = pkg.version;

export const MANIFEST_DIRNAME = ".athenaeum";
export const JOURNAL_FILENAME = "manifest.jsonl";
export const SNAPSHOT_FILENAME = "snapshot.jsonl";

export type ScanMode = "cold" | "incremental" | "scrub" | "compact" | "bench";

// ── Row types ──────────────────────────────────────────────────────────────────
//
// Every manifest file is JSON Lines: one JSON object per line, each with a "type" tag.
// The four filesystem-identity numerics (dev, ino, size, mtimeNs) are serialized as
// DECIMAL STRINGS, never JSON numbers: mtimeNs (nanoseconds since epoch) exceeds 2^53 and
// would silently lose precision as an IEEE-754 double. Readers MUST parse them as
// arbitrary-precision integers (Python int, JS BigInt).

/** First row of every file (journal or snapshot). Written once at file creation. */
export interface HeaderRow {
  type: "header";
  schema: number; // SCHEMA_VERSION
  scanner: string; // scanner version that created the file
  root: string; // absolute path of the scanned root
  kind: "journal" | "snapshot";
  generation: number; // generation counter at file creation
  createdAt: string; // ISO-8601 UTC
}

/** Opens a generation (one scan run or compaction). Journal only. */
export interface GenOpenRow {
  type: "gen-open";
  generation: number;
  mode: ScanMode;
  scanner: string;
  startedAt: string; // ISO-8601 UTC
}

/** Closes a generation with its summary. Journal only. */
export interface GenCloseRow {
  type: "gen-close";
  generation: number;
  finishedAt: string; // ISO-8601 UTC
  summary: ScanSummary;
}

/**
 * A content-identity row. Key: (dev, ino). Value: (size, mtimeNs) -> blake3.
 * One live row per inode; a content change (new size/mtimeNs) replaces the prior row.
 * Hardlinks share one identity row (same dev,ino) referenced by multiple path rows.
 */
export interface IdentityRow {
  type: "identity";
  dev: string; // decimal-string bigint
  ino: string; // decimal-string bigint
  size: string; // decimal-string bigint (bytes)
  mtimeNs: string; // decimal-string bigint (ns since epoch)
  blake3: string; // 64-hex lowercase (BLAKE3-256)
  generation: number; // generation that produced this content-version
}

/** A path -> identity mapping. Path is POSIX-relative to the scanned root. */
export interface PathRow {
  type: "path";
  path: string; // POSIX, relative to root
  dev: string; // identity key it references
  ino: string;
  generation: number; // generation that last wrote this mapping
}

/** A path removed since the last generation. */
export interface PathDeleteRow {
  type: "path-delete";
  path: string;
  generation: number;
}

/**
 * A scrub found a content mismatch at a STABLE stat tuple — probable bit-rot or silent
 * mutation. Emitted loudly; the run exits nonzero. Never auto-corrects the identity row.
 */
export interface ScrubCorruptRow {
  type: "scrub-corrupt";
  path: string;
  dev: string;
  ino: string;
  size: string;
  mtimeNs: string;
  expected: string; // blake3 stored in the identity row
  actual: string; // blake3 recomputed during scrub
  generation: number;
  detectedAt: string; // ISO-8601 UTC
}

/** A file the scanner could not index (unreadable, special file). Log-and-skip audit trail. */
export interface SkipRow {
  type: "skip";
  path: string; // POSIX relative
  reason: string; // e.g. "eacces", "special-file", "eio"
  generation: number;
}

export type ManifestRow =
  | HeaderRow
  | GenOpenRow
  | GenCloseRow
  | IdentityRow
  | PathRow
  | PathDeleteRow
  | ScrubCorruptRow
  | SkipRow;

/** Per-generation counts, embedded in the gen-close row and printed at run end. */
export interface ScanSummary {
  mode: ScanMode;
  generation: number;
  filesSeen: number; // regular files walked
  hashed: number; // files hashed this run (new content-versions)
  moved: number; // path rows added referencing a PRE-EXISTING identity (rename / new hardlink; zero re-hash)
  deleted: number; // path rows removed
  skipped: number; // files logged-and-skipped
  scrubbed: number; // files re-hashed by the scrub sampler
  corrupt: number; // scrub mismatches at a stable stat tuple
  bytesHashed: string; // decimal-string bigint
  elapsedMs: number;
}

// ── bigint <-> decimal-string helpers ───────────────────────────────────────────

export const b2s = (b: bigint): string => b.toString();
export const s2b = (s: string): bigint => BigInt(s);

/** Identity table key. Two hardlinked paths produce the same key. */
export const identityKey = (dev: bigint, ino: bigint): string => `${dev}:${ino}`;
