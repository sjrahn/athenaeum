// The manifest: contract v2. Two SQLite databases under `.athenaeum/`: `state.sqlite` (this
// class's private working state, WAL mode) and `manifest.sqlite` (a checkpointed copy,
// unveiled atomically at the end of every successful generation — the only file remote
// readers open). Replacing v1's JSONL journal/snapshot — which replayed entirely into two
// in-memory Maps on every open — with indexed on-disk lookups is the whole point: O(1) JS
// memory regardless of tree size, so a multi-million-file share root doesn't cost linear
// RAM just to resume a scan.
//
// Two transactions per run: the walk phase (path/skip/migration writes) commits once at the
// end of the walk — cheap to redo from a fresh stat-walk if lost, so it isn't sub-batched.
// The hash phase (identity writes, the expensive-to-redo work) commits in batches of at most
// `batchSize` files or `batchIntervalMs`, whichever comes first — a crash loses at most the
// last batch, never more.

import { Database } from "bun:sqlite";
import { open, copyFile, rename, rm, mkdir, stat } from "node:fs/promises";
import { join } from "node:path";
import {
  SCHEMA_VERSION,
  SCANNER_VERSION,
  STATE_FILENAME,
  MANIFEST_FILENAME,
  identityKey,
  type IdentityState,
  type PathState,
  type ScanMode,
  type ScanSummary,
} from "./schema.ts";
import type { Logger } from "./log.ts";

export const DEFAULT_IDENTITY_BATCH_SIZE = 64;
export const DEFAULT_IDENTITY_BATCH_INTERVAL_MS = 5000;

export interface ManifestOpenOptions {
  /** test/tuning hook: commit an identity batch after this many rows (default 64). */
  batchSize?: number;
  /** test/tuning hook: commit an identity batch after this many ms since the batch opened (default 5000). */
  batchIntervalMs?: number;
}

const DDL = `
PRAGMA user_version = ${SCHEMA_VERSION};
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE identities (
  dev INTEGER NOT NULL, ino INTEGER NOT NULL,
  size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
  blake3 TEXT NOT NULL, generation INTEGER NOT NULL,
  PRIMARY KEY (dev, ino)
) WITHOUT ROWID;
CREATE INDEX idx_identities_blake3 ON identities(blake3);
CREATE TABLE paths (
  path TEXT PRIMARY KEY, dev INTEGER NOT NULL, ino INTEGER NOT NULL,
  generation INTEGER NOT NULL
) WITHOUT ROWID;
CREATE INDEX idx_paths_identity ON paths(dev, ino);
CREATE TABLE generations (
  generation INTEGER PRIMARY KEY, mode TEXT NOT NULL, scanner TEXT NOT NULL,
  started_at TEXT NOT NULL, finished_at TEXT, summary_json TEXT
);
CREATE TABLE events (
  id INTEGER PRIMARY KEY, generation INTEGER NOT NULL, type TEXT NOT NULL,
  path TEXT NOT NULL, detail_json TEXT NOT NULL
);
`;

async function fsyncDir(dir: string): Promise<void> {
  // Best-effort: persist the rename in the directory entry. Not fatal if unsupported.
  try {
    const fh = await open(dir, "r");
    try {
      await fh.sync();
    } finally {
      await fh.close();
    }
  } catch {
    /* directory fsync unsupported on this platform/fs — tolerate */
  }
}

async function exists(p: string): Promise<boolean> {
  try {
    await stat(p);
    return true;
  } catch {
    return false;
  }
}

interface IdentityRow {
  size: bigint;
  mtimeNs: bigint;
  blake3: string;
  generation: bigint;
}
interface PathRow {
  dev: bigint;
  ino: bigint;
  generation: bigint;
}
interface ScrubRow {
  path: string;
  dev: bigint;
  ino: bigint;
  size: bigint;
  mtimeNs: bigint;
  blake3: string;
}

export class Manifest {
  generation: number;

  private txOpen = false;
  private batchCount = 0;
  private batchStart = 0;
  private readonly batchSize: number;
  private readonly batchIntervalMs: number;

  private readonly statePath: string;
  private readonly manifestPath: string;

  // prepared statements, compiled once and reused for the life of the connection
  private readonly selIdentity;
  private readonly selPath;
  private readonly insIdentity;
  private readonly insPath;
  // walk_seen is a TEMP TABLE, dropped and recreated by every beginWalk() (it must never leak
  // into the published manifest.sqlite, which is a byte-for-byte copy of state.sqlite's main
  // file — temp tables live in SQLite's separate temp database, never in the main file, which
  // is exactly why this is implemented as one). Its statements can't be compiled until the
  // table exists, so they're (re)prepared in beginWalk(), not here.
  private insWalkSeen!: ReturnType<Database["query"]>;
  private delPathsNotSeen!: ReturnType<Database["query"]>;
  private readonly insEvent;
  private readonly insGenOpen;
  private readonly updGenClose;
  private readonly delOrphanIdentities;
  private readonly countIdentities;
  private readonly countPaths;
  private readonly existsIdentities;
  private readonly existsPaths;
  private readonly maxGeneration;
  private readonly selScrubSample;
  private readonly dumpIdentitiesStmt;
  private readonly dumpPathsStmt;

  private constructor(
    private readonly db: Database,
    readonly dir: string,
    readonly root: string,
    private readonly log: Logger,
    opts: ManifestOpenOptions,
  ) {
    this.statePath = join(dir, STATE_FILENAME);
    this.manifestPath = join(dir, MANIFEST_FILENAME);
    this.batchSize = opts.batchSize ?? DEFAULT_IDENTITY_BATCH_SIZE;
    this.batchIntervalMs = opts.batchIntervalMs ?? DEFAULT_IDENTITY_BATCH_INTERVAL_MS;

    this.selIdentity = db.query<IdentityRow, [bigint, bigint]>(
      "SELECT size, mtime_ns as mtimeNs, blake3, generation FROM identities WHERE dev=? AND ino=?",
    );
    this.selPath = db.query<PathRow, [string]>("SELECT dev, ino, generation FROM paths WHERE path=?");
    this.insIdentity = db.query<never, [bigint, bigint, bigint, bigint, string, number]>(
      "INSERT OR REPLACE INTO identities (dev,ino,size,mtime_ns,blake3,generation) VALUES (?,?,?,?,?,?)",
    );
    this.insPath = db.query<never, [string, bigint, bigint, number]>(
      "INSERT OR REPLACE INTO paths (path,dev,ino,generation) VALUES (?,?,?,?)",
    );
    this.insEvent = db.query<never, [number, string, string, string]>(
      "INSERT INTO events (generation,type,path,detail_json) VALUES (?,?,?,?)",
    );
    this.insGenOpen = db.query<never, [number, string, string, string]>(
      "INSERT INTO generations (generation,mode,scanner,started_at,finished_at,summary_json) VALUES (?,?,?,?,NULL,NULL)",
    );
    this.updGenClose = db.query<never, [string, string, number]>(
      "UPDATE generations SET finished_at=?, summary_json=? WHERE generation=?",
    );
    this.delOrphanIdentities = db.query<never, []>(
      "DELETE FROM identities WHERE NOT EXISTS (SELECT 1 FROM paths p WHERE p.dev=identities.dev AND p.ino=identities.ino)",
    );
    this.countIdentities = db.query<{ c: bigint }, []>("SELECT COUNT(*) as c FROM identities");
    this.countPaths = db.query<{ c: bigint }, []>("SELECT COUNT(*) as c FROM paths");
    this.existsIdentities = db.query<{ e: bigint }, []>("SELECT EXISTS(SELECT 1 FROM identities) as e");
    this.existsPaths = db.query<{ e: bigint }, []>("SELECT EXISTS(SELECT 1 FROM paths) as e");
    this.maxGeneration = db.query<{ g: bigint }, []>("SELECT COALESCE(MAX(generation),0) as g FROM generations");
    this.selScrubSample = db.query<ScrubRow, [number]>(
      `SELECT p.path as path, i.dev as dev, i.ino as ino, i.size as size, i.mtime_ns as mtimeNs, i.blake3 as blake3
       FROM paths p JOIN identities i ON p.dev=i.dev AND p.ino=i.ino
       GROUP BY i.dev, i.ino
       ORDER BY RANDOM() LIMIT ?`,
    );
    this.dumpIdentitiesStmt = db.query<{ dev: bigint; ino: bigint; size: bigint; mtimeNs: bigint; blake3: string; generation: bigint }, []>(
      "SELECT dev, ino, size, mtime_ns as mtimeNs, blake3, generation FROM identities",
    );
    this.dumpPathsStmt = db.query<{ path: string; dev: bigint; ino: bigint; generation: bigint }, []>(
      "SELECT path, dev, ino, generation FROM paths",
    );

    this.generation = Number(this.maxGeneration.get()!.g);
  }

  /** Open (or initialize) `state.sqlite` at `manifestDir`. Cleans up any stale publish `.tmp`. */
  static async open(manifestDir: string, rootAbs: string, log: Logger, opts: ManifestOpenOptions = {}): Promise<Manifest> {
    await mkdir(manifestDir, { recursive: true });
    const statePath = join(manifestDir, STATE_FILENAME);
    const manifestTmpPath = join(manifestDir, MANIFEST_FILENAME) + ".tmp";
    await rm(manifestTmpPath, { force: true }).catch(() => {});

    const isNew = !(await exists(statePath));
    const db = new Database(statePath, { create: true, readwrite: true, safeIntegers: true });
    db.run("PRAGMA journal_mode = WAL");
    db.run("PRAGMA synchronous = NORMAL"); // WAL + NORMAL: safe against process kill (our resumability
    // story), not against OS/power loss since the last checkpoint — the standard, deliberate
    // tradeoff for a bulk-write workload; publish()'s explicit checkpoint+fsync is the durability
    // boundary that matters for readers.

    if (isNew) {
      db.run(DDL);
      const now = new Date().toISOString();
      const insMeta = db.query("INSERT INTO meta (key, value) VALUES (?,?)");
      insMeta.run("schema", String(SCHEMA_VERSION));
      insMeta.run("scanner", SCANNER_VERSION);
      insMeta.run("root", rootAbs);
      insMeta.run("created_at", now);
    } else {
      const uv = db.query<{ user_version: bigint }, []>("PRAGMA user_version").get();
      const found = uv ? Number(uv.user_version) : -1;
      if (found !== SCHEMA_VERSION) {
        db.close();
        throw new Error(
          `${statePath}: schema mismatch (found user_version=${found}, expected ${SCHEMA_VERSION}) — ` +
            `no migration path from v1 JSONL manifests; see MANIFEST-SCHEMA.md changelog`,
        );
      }
      const rootRow = db.query<{ value: string }, []>("SELECT value FROM meta WHERE key='root'").get();
      if (rootRow && rootRow.value !== rootAbs) {
        log.warn(`manifest root "${rootRow.value}" != requested "${rootAbs}"; paths are relative, proceeding`);
      }
    }

    return new Manifest(db, manifestDir, rootAbs, log, opts);
  }

  /** True iff neither an identity nor a path has ever been recorded (first run on this root). */
  isEmpty(): boolean {
    return Number(this.existsIdentities.get()!.e) === 0 && Number(this.existsPaths.get()!.e) === 0;
  }

  getIdentity(dev: bigint, ino: bigint): IdentityState | undefined {
    const row = this.selIdentity.get(dev, ino);
    if (!row) return undefined;
    return { dev, ino, size: row.size, mtimeNs: row.mtimeNs, blake3: row.blake3, generation: Number(row.generation) };
  }

  getPathIdentity(path: string): PathState | undefined {
    const row = this.selPath.get(path);
    if (!row) return undefined;
    return { dev: row.dev, ino: row.ino, generation: Number(row.generation) };
  }

  // ── walk phase: one transaction, committed once at the end of the walk ────────────────

  beginWalk(): void {
    this.db.run("DROP TABLE IF EXISTS temp.walk_seen");
    this.db.run("CREATE TEMP TABLE walk_seen (path TEXT PRIMARY KEY) WITHOUT ROWID");
    // (re)prepared each call: the temp table above didn't exist until just now, and gets
    // dropped and recreated on every beginWalk(), so these can't be compiled once at
    // construction time the way the main-schema statements are.
    this.insWalkSeen = this.db.query<never, [string]>("INSERT OR IGNORE INTO walk_seen (path) VALUES (?)");
    this.delPathsNotSeen = this.db.query<never, []>("DELETE FROM paths WHERE path NOT IN (SELECT path FROM walk_seen)");
    this.db.run("BEGIN");
    this.txOpen = true;
  }

  /** Record that `path` was observed this walk (drives deletion reconciliation). File entries only. */
  markSeen(path: string): void {
    this.insWalkSeen.run(path);
  }

  putPath(path: string, dev: bigint, ino: bigint, generation: number): void {
    this.insPath.run(path, dev, ino, generation);
  }

  putSkip(path: string, reason: string, generation: number): void {
    this.insEvent.run(generation, "skip", path, JSON.stringify({ reason }));
  }

  /** Inode-migration heuristic: carry a known blake3 onto a new (dev,ino) at an unchanged (size,mtimeNs). */
  putMigratedIdentity(dev: bigint, ino: bigint, size: bigint, mtimeNs: bigint, blake3: string, generation: number): void {
    this.insIdentity.run(dev, ino, size, mtimeNs, blake3, generation);
  }

  /** Drop path rows not seen this walk. Must run inside the open walk transaction, before commitWalk(). */
  reconcileDeletions(): number {
    return this.delPathsNotSeen.run().changes;
  }

  commitWalk(): void {
    this.db.run("COMMIT");
    this.txOpen = false;
    this.db.run("DROP TABLE IF EXISTS temp.walk_seen");
  }

  // ── hash phase: batched transactions (durability window: batchSize rows or batchIntervalMs) ──

  putIdentity(dev: bigint, ino: bigint, size: bigint, mtimeNs: bigint, blake3: string, generation: number): void {
    if (!this.txOpen) {
      this.db.run("BEGIN");
      this.txOpen = true;
      this.batchCount = 0;
      this.batchStart = performance.now();
    }
    this.insIdentity.run(dev, ino, size, mtimeNs, blake3, generation);
    this.batchCount++;
    if (this.batchCount >= this.batchSize || performance.now() - this.batchStart >= this.batchIntervalMs) {
      this.flushBatch();
    }
  }

  /** Commit whatever's pending in the current identity batch, if any. */
  flushBatch(): void {
    if (this.txOpen) {
      this.db.run("COMMIT");
      this.txOpen = false;
    }
  }

  // ── generation bookkeeping ──────────────────────────────────────────────────────────

  genOpen(mode: ScanMode, generation: number): void {
    this.insGenOpen.run(generation, mode, SCANNER_VERSION, new Date().toISOString());
    if (generation > this.generation) this.generation = generation;
  }

  genClose(summary: ScanSummary): void {
    this.updGenClose.run(new Date().toISOString(), JSON.stringify(summary), summary.generation);
  }

  // ── scrub ────────────────────────────────────────────────────────────────────────────

  /** Up to `n` random (identity, representative live path) pairs, picked in SQL — no full-tree JS load. */
  scrubSample(n: number): ScrubRow[] {
    return this.selScrubSample.all(n);
  }

  putScrubCorrupt(id: { dev: bigint; ino: bigint; size: bigint; mtimeNs: bigint; blake3: string }, path: string, actual: string, generation: number): void {
    const detail = {
      expected: id.blake3,
      actual,
      size: id.size.toString(),
      mtime_ns: id.mtimeNs.toString(),
      detected_at: new Date().toISOString(),
    };
    this.insEvent.run(generation, "scrub-corrupt", path, JSON.stringify(detail));
  }

  // ── compaction ──────────────────────────────────────────────────────────────────────

  /** Drop orphaned identities (zero referencing paths) and VACUUM. Publish is the caller's job. */
  compact(generation: number): { identities: number; paths: number; orphansDropped: number } {
    this.flushBatch(); // defensive: no-op unless called mid-batch
    if (generation > this.generation) this.generation = generation;
    const orphansDropped = this.delOrphanIdentities.run().changes;
    this.db.run("VACUUM");
    return {
      identities: Number(this.countIdentities.get()!.c),
      paths: Number(this.countPaths.get()!.c),
      orphansDropped,
    };
  }

  // ── publish: checkpoint + atomic copy-then-rename ──────────────────────────────────────

  /**
   * Unveil the current state as the published manifest: WAL-checkpoint (TRUNCATE) so
   * `state.sqlite`'s main file is self-contained, copy its bytes to `manifest.sqlite.tmp`,
   * fsync, rename over `manifest.sqlite`, fsync the directory (best-effort). Call only after
   * a successful `genClose` — an interrupted run must never publish partial work.
   */
  async publish(): Promise<void> {
    this.db.run("PRAGMA wal_checkpoint(TRUNCATE)");
    const tmp = this.manifestPath + ".tmp";
    await copyFile(this.statePath, tmp);
    const fh = await open(tmp, "r+");
    try {
      await fh.sync();
    } finally {
      await fh.close();
    }
    await rename(tmp, this.manifestPath);
    await fsyncDir(this.dir);
  }

  // ── test/inspection only — never on the hot path; materializes full state into memory ──

  dumpIdentities(): Map<string, IdentityState> {
    const m = new Map<string, IdentityState>();
    for (const r of this.dumpIdentitiesStmt.all()) {
      m.set(identityKey(r.dev, r.ino), { dev: r.dev, ino: r.ino, size: r.size, mtimeNs: r.mtimeNs, blake3: r.blake3, generation: Number(r.generation) });
    }
    return m;
  }

  dumpPaths(): Map<string, PathState> {
    const m = new Map<string, PathState>();
    for (const r of this.dumpPathsStmt.all()) {
      m.set(r.path, { dev: r.dev, ino: r.ino, generation: Number(r.generation) });
    }
    return m;
  }

  // ── lifecycle ───────────────────────────────────────────────────────────────────────

  /** Roll back any open (uncommitted) transaction — this is what makes a simulated/real
   * process kill lose at most the in-flight batch — then close the connection. */
  async close(): Promise<void> {
    if (this.txOpen) {
      try {
        this.db.run("ROLLBACK");
      } catch {
        /* nothing to roll back / connection already unusable */
      }
      this.txOpen = false;
    }
    this.db.close();
  }
}
