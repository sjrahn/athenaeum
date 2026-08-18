// The presented-manifest schema — the cross-language contract between the TypeScript
// scanner (writer) and the Python corpus tooling (reader). See MANIFEST-SCHEMA.md for the
// prose specification; this file is its executable form (the SQL DDL lives in manifest.ts,
// next to the code that creates it, but SCHEMA_VERSION here is the single source of truth).
// Bump SCHEMA_VERSION on any incompatible change and record the migration in
// MANIFEST-SCHEMA.md.

import pkg from "../package.json" with { type: "json" };

export const SCHEMA_VERSION = 3;
export const SCANNER_VERSION: string = pkg.version;

export const MANIFEST_DIRNAME = ".athenaeum";
/** The scanner's private working state. WAL mode. Remote readers must never open this. */
export const STATE_FILENAME = "state.sqlite";
/** The published manifest: a checkpointed copy of state.sqlite, unveiled atomically. */
export const MANIFEST_FILENAME = "manifest.sqlite";

export type ScanMode = "cold" | "incremental" | "scrub" | "compact" | "bench";

/**
 * Default basename deny-list for filesystem-metadata junk — a CURATED POSITIVE list,
 * deliberately NOT "skip every hidden dotfile" (many dotfiles, e.g. `.config`, are wanted
 * content). Motivating incident: macOS AppleDouble `._*` sidecars indexed off an unRAID share
 * are permanently unreachable over SMB (Samba vetoes `._*`), producing rows that can never
 * resolve. A trailing `*` means "prefix match" (see `matchesIgnorePattern` in walk.ts); every
 * other entry is an exact basename match. A matched file is skipped; a matched directory is
 * pruned (its subtree is never entered). `._*` deliberately also catches `.__*` lock-style
 * names, matching Samba's own veto behavior. This is the scanner's half of a two-language
 * shared list — `tools/src/corpus/locationindex.py`'s `_DEFAULT_IGNORE_PATTERNS` is the
 * sibling copy and must be kept in sync by hand; there's no single build step spanning both
 * languages.
 */
export const DEFAULT_IGNORE_PATTERNS: readonly string[] = [
  ".DS_Store",
  "._*",
  ".AppleDouble",
  ".AppleDesktop",
  ".TemporaryItems",
  ".Trashes",
  ".Spotlight-V100",
  ".fseventsd",
  ".DocumentRevisions-V100",
  "Thumbs.db",
  "desktop.ini",
  "@eaDir",
  ".@__thumb",
];

/**
 * Content-identity state, one row per live `(dev, ino)`. Mirrors the `identities` table.
 * The four filesystem-identity numerics are native SQLite INTEGERs (int64) — mtime_ns
 * (~1.7e18) fits comfortably under 2^63, so schema v2 drops the decimal-string encoding
 * v1 needed to survive JSON's float-precision ceiling.
 *
 * v3 (catalog metadata — spec/corpus.md §12.1.1 *(25)*) adds four nullable columns: three
 * universal stat facts refreshed by the walk when they drift (ctimeNs, btimeNs, mode), plus
 * an advisory mimeClaim sniffed from the leading bytes once per new identity. All four are
 * `null` on a row that hasn't been touched by v3 code yet (a pre-v3 row surviving the v2->v3
 * migration, or a v2 seed source) until the walk's backfill/refresh pass catches it up.
 */
export interface IdentityState {
  dev: bigint;
  ino: bigint;
  size: bigint;
  mtimeNs: bigint;
  blake3: string; // 64-hex lowercase (BLAKE3-256)
  generation: number;
  ctimeNs: bigint | null; // stat ctime, ns
  btimeNs: bigint | null; // stat birth time, ns; null where the fs doesn't report one (raw 0n)
  mode: bigint | null; // stat st_mode
  mimeClaim: string | null; // advisory, sniffed from the leading bytes — see sniff.ts
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
  hashed: number; // files hashed this run (new content-versions) — WASM + native combined
  hashedNative: number; // subset of `hashed` that went through the native b3sum path (informational addition; see MANIFEST-SCHEMA.md changelog)
  moved: number; // path rows added referencing a PRE-EXISTING identity (rename / new hardlink; zero re-hash)
  migrated: number; // path rows carried onto a NEW (dev,ino) at an unchanged (size,mtimeNs); zero re-hash
  seeded: number; // identity rows adopted from another manifest this run (nested-child auto-seed or --seed-from)
  deleted: number; // path rows removed
  skipped: number; // files logged-and-skipped
  ignored: number; // files and pruned dirs skipped by the ignore-pattern deny-list this walk
  scrubbed: number; // files re-hashed by the scrub sampler
  corrupt: number; // scrub mismatches at a stable stat tuple
  sniffed: number; // mime_claim values written this run (new-identity hash-time sniffs + walk-time backfill sniffs of pre-existing NULL claims); carried-forward claims (inode migration) don't count
  bytesHashed: string; // decimal-string bigint — this is a JSON blob field (summary_json), not a
  // SQL column, so it keeps the v1 encoding: JSON numbers are still IEEE-754 doubles regardless
  // of what the SQL schema stores.
  elapsedMs: number;
}

/** In-run dedup key for hardlinked identities queued for hashing at most once per pass. */
export const identityKey = (dev: bigint, ino: bigint): string => `${dev}:${ino}`;
