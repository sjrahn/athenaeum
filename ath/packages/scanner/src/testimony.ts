// testimony.ts — what the scanner observed of one file, as testimony in the contract's shape (spec §18.5.2, §9.4): the
// file's hash as `subject`, the scanner as `producer`, the host and the path under `source`, and beside them the size,
// mtime, birth time and generation it saw. A function of the published manifest's row, so the same observation always
// yields the same bytes and the same hash; it enters an instance only when the file is ingested.
import { Database } from "bun:sqlite";
import { hostname } from "node:os";
import { join } from "node:path";

export interface Observation {
  hash: string;
  host: string;
  /** The scanned root on the host, absolute. */
  root: string;
  /** The file's path, relative to the root. */
  path: string;
  size: number;
  mtime: string;
  birth: string | null;
  generation: number;
  scanner: string;
  /** When the generation that observed it finished. */
  at: string;
}

const q = (s: string) => JSON.stringify(s);

export function fileTestimony(o: Observation): string {
  return [
    `subject: b3:${o.hash}`,
    "producer:",
    "  tool: ath-scan",
    `  version: ${q(o.scanner)}`,
    `  at: ${q(o.at)}`,
    `  host: ${q(o.host)}`,
    "source:",
    `  host: ${q(o.host)}`,
    `  path: ${q(`${o.root.replace(/\/$/, "")}/${o.path}`)}`,
    "observed:",
    `  size: ${o.size}`,
    `  mtime: ${q(o.mtime)}`,
    `  birth: ${o.birth === null ? "null" : q(o.birth)}`,
    `  generation: ${o.generation}`,
    "",
  ].join("\n");
}

const second = (ns: bigint) => `${new Date(Number(ns / 1000000n)).toISOString().slice(0, 19)}Z`;

/** The observation of `path` in a published manifest, or null when the manifest lists no such path. */
export function observationOf(manifestDir: string, path: string): Observation | null {
  const db = new Database(join(manifestDir, "manifest.sqlite"), { readonly: true, safeIntegers: true });
  try {
    const meta = new Map(
      db
        .query<{ key: string; value: string }, []>("SELECT key, value FROM meta")
        .all()
        .map((r) => [r.key, r.value]),
    );
    const row = db
      .query<{ blake3: string; size: bigint; mtime_ns: bigint; btime_ns: bigint | null; generation: bigint }, [string]>(
        "SELECT i.blake3, i.size, i.mtime_ns, i.btime_ns, i.generation FROM paths p JOIN identities i ON i.dev = p.dev AND i.ino = p.ino WHERE p.path = ?",
      )
      .get(path);
    if (!row) return null;
    const gen = db
      .query<{ finished_at: string | null; scanner: string }, [bigint]>("SELECT finished_at, scanner FROM generations WHERE generation = ?")
      .get(row.generation);
    return {
      hash: row.blake3,
      host: meta.get("host") ?? hostname(),
      root: meta.get("root") ?? "",
      path,
      size: Number(row.size),
      mtime: second(row.mtime_ns),
      birth: row.btime_ns === null ? null : second(row.btime_ns),
      generation: Number(row.generation),
      scanner: gen?.scanner ?? meta.get("scanner") ?? "unknown",
      at: gen?.finished_at ? `${gen.finished_at.slice(0, 19)}Z` : `${new Date(0).toISOString().slice(0, 19)}Z`,
    };
  } finally {
    db.close();
  }
}
