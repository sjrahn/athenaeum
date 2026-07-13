// The manifest: the on-share state. A compacted snapshot (base) plus an append-only jsonl
// journal (deltas). Load = replay snapshot then journal into two in-memory maps. Appends
// buffer and fsync at file granularity so a killed cold pass resumes without re-hashing
// completed work. Compaction folds journal into a fresh snapshot, temp-then-rename atomic,
// dropping orphaned identities (zero paths) on the way.

import { open, readFile, rename, mkdir, stat, type FileHandle } from "node:fs/promises";
import { join } from "node:path";
import {
  SCHEMA_VERSION,
  SCANNER_VERSION,
  JOURNAL_FILENAME,
  SNAPSHOT_FILENAME,
  b2s,
  s2b,
  identityKey,
  type ManifestRow,
  type IdentityRow,
  type PathRow,
  type ScanMode,
  type ScanSummary,
} from "./schema.ts";
import type { Logger } from "./log.ts";

export interface IdentityState {
  dev: bigint;
  ino: bigint;
  size: bigint;
  mtimeNs: bigint;
  blake3: string;
  generation: number;
}

export interface PathState {
  dev: bigint;
  ino: bigint;
  generation: number;
}

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

export class Manifest {
  readonly identities = new Map<string, IdentityState>();
  readonly paths = new Map<string, PathState>();
  generation = 0;
  root: string;

  private buffer: string[] = [];
  private flushChain: Promise<void> = Promise.resolve();

  private constructor(
    readonly dir: string,
    root: string,
    private journalFh: FileHandle,
    private readonly log: Logger,
  ) {
    this.root = root;
  }

  private get journalPath(): string {
    return join(this.dir, JOURNAL_FILENAME);
  }
  private get snapshotPath(): string {
    return join(this.dir, SNAPSHOT_FILENAME);
  }

  /** Load (or initialize) the manifest at `manifestDir` for `rootAbs`, journal opened for append. */
  static async open(manifestDir: string, rootAbs: string, log: Logger): Promise<Manifest> {
    await mkdir(manifestDir, { recursive: true });
    const snapshotPath = join(manifestDir, SNAPSHOT_FILENAME);
    const journalPath = join(manifestDir, JOURNAL_FILENAME);

    // Temporary handle; replaced once we can build the instance.
    const mfState = {
      identities: new Map<string, IdentityState>(),
      paths: new Map<string, PathState>(),
      generation: 0,
      root: rootAbs,
    };

    const applyLine = (line: string, source: string): void => {
      const trimmed = line.trim();
      if (trimmed === "") return;
      let row: ManifestRow;
      try {
        row = JSON.parse(trimmed) as ManifestRow;
      } catch {
        // Tolerate a truncated final line from an interrupted append; skip and move on.
        log.warn(`${source}: unparseable manifest line skipped (${trimmed.length} bytes)`);
        return;
      }
      Manifest.applyRowInto(mfState, row, log);
    };

    if (await exists(snapshotPath)) {
      const text = await readFile(snapshotPath, "utf8");
      for (const line of text.split("\n")) applyLine(line, "snapshot");
    }
    if (await exists(journalPath)) {
      const text = await readFile(journalPath, "utf8");
      for (const line of text.split("\n")) applyLine(line, "journal");
    }

    if (mfState.root !== rootAbs) {
      log.warn(`manifest root "${mfState.root}" != requested "${rootAbs}"; paths are relative, proceeding`);
    }

    const journalExisted = await exists(journalPath);
    const journalFh = await open(journalPath, "a");
    const mf = new Manifest(manifestDir, rootAbs, journalFh, log);
    mf.identities.clear();
    for (const [k, v] of mfState.identities) mf.identities.set(k, v);
    for (const [k, v] of mfState.paths) mf.paths.set(k, v);
    mf.generation = mfState.generation;

    if (!journalExisted || (await stat(journalPath)).size === 0) {
      mf.buffer.push(mf.line({
        type: "header",
        schema: SCHEMA_VERSION,
        scanner: SCANNER_VERSION,
        root: rootAbs,
        kind: "journal",
        generation: mf.generation,
        createdAt: new Date().toISOString(),
      }));
      await mf.flush();
    }
    return mf;
  }

  // ── state application (load + append share this) ──────────────────────────────

  private static applyRowInto(
    s: { identities: Map<string, IdentityState>; paths: Map<string, PathState>; generation: number; root: string },
    row: ManifestRow,
    _log: Logger,
  ): void {
    if ("generation" in row && typeof row.generation === "number") {
      if (row.generation > s.generation) s.generation = row.generation;
    }
    switch (row.type) {
      case "header":
        if (row.root) s.root = row.root;
        break;
      case "identity": {
        const dev = s2b(row.dev);
        const ino = s2b(row.ino);
        s.identities.set(identityKey(dev, ino), {
          dev,
          ino,
          size: s2b(row.size),
          mtimeNs: s2b(row.mtimeNs),
          blake3: row.blake3,
          generation: row.generation,
        });
        break;
      }
      case "path":
        s.paths.set(row.path, { dev: s2b(row.dev), ino: s2b(row.ino), generation: row.generation });
        break;
      case "path-delete":
        s.paths.delete(row.path);
        break;
      // gen-open, gen-close, scrub-corrupt, skip carry no persistent map state
    }
  }

  private applyRow(row: ManifestRow): void {
    Manifest.applyRowInto(this, row, this.log);
  }

  // ── append helpers (mutate state + buffer the line) ───────────────────────────

  private line(row: ManifestRow): string {
    return JSON.stringify(row) + "\n";
  }

  private append(row: ManifestRow): void {
    this.applyRow(row);
    this.buffer.push(this.line(row));
  }

  genOpen(mode: ScanMode, generation: number): void {
    this.append({ type: "gen-open", generation, mode, scanner: SCANNER_VERSION, startedAt: new Date().toISOString() });
  }

  genClose(summary: ScanSummary): void {
    this.append({ type: "gen-close", generation: summary.generation, finishedAt: new Date().toISOString(), summary });
  }

  putIdentity(dev: bigint, ino: bigint, size: bigint, mtimeNs: bigint, blake3: string, generation: number): void {
    this.append({ type: "identity", dev: b2s(dev), ino: b2s(ino), size: b2s(size), mtimeNs: b2s(mtimeNs), blake3, generation });
  }

  putPath(path: string, dev: bigint, ino: bigint, generation: number): void {
    this.append({ type: "path", path, dev: b2s(dev), ino: b2s(ino), generation });
  }

  deletePath(path: string, generation: number): void {
    this.append({ type: "path-delete", path, generation });
  }

  putSkip(path: string, reason: string, generation: number): void {
    this.append({ type: "skip", path, reason, generation });
  }

  putScrubCorrupt(id: IdentityState, path: string, actual: string, generation: number): void {
    this.append({
      type: "scrub-corrupt",
      path,
      dev: b2s(id.dev),
      ino: b2s(id.ino),
      size: b2s(id.size),
      mtimeNs: b2s(id.mtimeNs),
      expected: id.blake3,
      actual,
      generation,
      detectedAt: new Date().toISOString(),
    });
  }

  // ── durability ────────────────────────────────────────────────────────────────

  flush(): Promise<void> {
    this.flushChain = this.flushChain.then(() => this.doFlush());
    return this.flushChain;
  }

  private async doFlush(): Promise<void> {
    if (this.buffer.length === 0) return;
    const data = this.buffer.join("");
    this.buffer = [];
    await this.journalFh.write(data);
    await this.journalFh.sync();
  }

  async close(): Promise<void> {
    await this.flush();
    await this.journalFh.close();
  }

  // ── compaction ──────────────────────────────────────────────────────────────

  /**
   * Fold the journal into a fresh snapshot at `generation`, drop orphaned identities
   * (referenced by zero live paths), and reset the journal. Snapshot is written and renamed
   * before the journal is reset, so a crash mid-compaction leaves a complete snapshot and a
   * still-valid (idempotently-replayable) journal.
   */
  async compact(generation: number): Promise<{ identities: number; paths: number; orphansDropped: number }> {
    await this.flush();
    if (generation > this.generation) this.generation = generation;

    const referenced = new Set<string>();
    for (const p of this.paths.values()) referenced.add(identityKey(p.dev, p.ino));

    const lines: string[] = [];
    lines.push(this.line({
      type: "header",
      schema: SCHEMA_VERSION,
      scanner: SCANNER_VERSION,
      root: this.root,
      kind: "snapshot",
      generation,
      createdAt: new Date().toISOString(),
    }));

    let orphansDropped = 0;
    let idCount = 0;
    for (const [key, id] of this.identities) {
      if (!referenced.has(key)) {
        orphansDropped++;
        this.identities.delete(key);
        continue;
      }
      idCount++;
      const row: IdentityRow = {
        type: "identity",
        dev: b2s(id.dev),
        ino: b2s(id.ino),
        size: b2s(id.size),
        mtimeNs: b2s(id.mtimeNs),
        blake3: id.blake3,
        generation: id.generation,
      };
      lines.push(this.line(row));
    }

    let pathCount = 0;
    for (const [path, p] of this.paths) {
      pathCount++;
      const row: PathRow = { type: "path", path, dev: b2s(p.dev), ino: b2s(p.ino), generation: p.generation };
      lines.push(this.line(row));
    }

    // 1) snapshot: temp -> fsync -> rename
    await this.writeAtomic(this.snapshotPath, lines.join(""));

    // 2) reset journal: fresh header only, temp -> fsync -> rename, then reopen for append
    const header = this.line({
      type: "header",
      schema: SCHEMA_VERSION,
      scanner: SCANNER_VERSION,
      root: this.root,
      kind: "journal",
      generation,
      createdAt: new Date().toISOString(),
    });
    await this.journalFh.close();
    await this.writeAtomic(this.journalPath, header);
    this.journalFh = await open(this.journalPath, "a");

    return { identities: idCount, paths: pathCount, orphansDropped };
  }

  private async writeAtomic(path: string, data: string): Promise<void> {
    const tmp = path + ".tmp";
    const fh = await open(tmp, "w");
    try {
      await fh.write(data);
      await fh.sync();
    } finally {
      await fh.close();
    }
    await rename(tmp, path);
    await fsyncDir(this.dir);
  }
}
