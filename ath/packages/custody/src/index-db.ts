// index-db.ts — the host's custody index (spec §18.4) at $XDG_STATE_HOME/athenaeum/index.sqlite, shared by every
// instance on the host: per store and BLAKE3 the state of a copy — `claimed` (an inventory says so), `verified` (hashed,
// with the instant) or `missing` — with its size and generation; per observed tree each path with its size and mtime;
// and from every receipt, the testimony it delivered, by hash and subject, so an instance's testimony is enumerable
// (§5.7). It is a belief about the stores, never a record: deleting it is always safe.
import { Database } from "bun:sqlite";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";

export type CopyState = "claimed" | "verified" | "missing";

export interface Copy {
  store: string;
  tree: "artifacts" | "testimony";
  hash: string;
  state: CopyState;
  size: number;
  verified_at: string | null;
  generation: number;
  /** For a hardlinked copy: the observed file it shares storage with, `<store id>:<path>`. */
  link?: string | null;
}

export interface ObservedRow {
  store: string;
  path: string;
  hash: string;
  size: number;
  mtime: string;
  generation: number;
  /** The managed store holding a copy made from this file, and how: `<store id> reflink|hardlink|copy`. */
  link: string | null;
}

export interface ReceiptRow {
  receipt: string;
  instance: string;
  artifact: string;
  name: string;
  received: string;
  actor: string;
  testimony: { hash: string; name: string }[];
}

const SCHEMA = `
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS copies (
  store TEXT NOT NULL, tree TEXT NOT NULL, hash TEXT NOT NULL, state TEXT NOT NULL, size INTEGER NOT NULL,
  verified_at TEXT, generation INTEGER NOT NULL DEFAULT 0, link TEXT, PRIMARY KEY (store, hash));
CREATE INDEX IF NOT EXISTS copies_hash ON copies (hash);
CREATE TABLE IF NOT EXISTS receipts (
  receipt TEXT PRIMARY KEY, instance TEXT NOT NULL, artifact TEXT NOT NULL, name TEXT NOT NULL, received TEXT NOT NULL,
  actor TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS receipts_artifact ON receipts (artifact);
CREATE INDEX IF NOT EXISTS receipts_instance ON receipts (instance);
CREATE TABLE IF NOT EXISTS delivered (
  receipt TEXT NOT NULL, testimony TEXT NOT NULL, name TEXT NOT NULL, subject TEXT NOT NULL, PRIMARY KEY (receipt, testimony));
CREATE INDEX IF NOT EXISTS delivered_testimony ON delivered (testimony);
CREATE INDEX IF NOT EXISTS copies_store ON copies (store);
CREATE TABLE IF NOT EXISTS observed (
  store TEXT NOT NULL, path TEXT NOT NULL, hash TEXT NOT NULL, size INTEGER NOT NULL, mtime TEXT NOT NULL,
  generation INTEGER NOT NULL, link TEXT, PRIMARY KEY (store, path));
CREATE INDEX IF NOT EXISTS observed_hash ON observed (hash);
`;

const VERSION = "2";
const TABLES = ["meta", "copies", "receipts", "delivered", "observed"];

export interface CustodyIndex {
  db: Database;
  putCopy(c: Copy): void;
  copies(hash: string): Copy[];
  /** Every copy the index believes a store holds. */
  copiesOn(store: string): Copy[];
  /** Every hash with a copy anywhere. */
  hashes(tree: "artifacts" | "testimony"): string[];
  /** The next inventory generation of a store. */
  nextGeneration(store: string): number;
  /** An observed tree's files as of one inventory: replaces what the index believed of the tree. */
  putObserved(store: string, rows: readonly Omit<ObservedRow, "store" | "link">[]): void;
  observed(where: { store?: string; hash?: string; path?: string }): ObservedRow[];
  setObservedLink(store: string, path: string, link: string): void;
  putReceipt(r: ReceiptRow): void;
  receipts(where: { artifact?: string; instance?: string }): ReceiptRow[];
  /** Every testimony the receipts of `instance` delivered (§5.7), with the receipts themselves. */
  testimonyOf(instance: string): { hash: string; subject: string; name: string; receipt: string }[];
  close(): void;
}

export function openIndex(path: string): CustodyIndex {
  mkdirSync(dirname(path), { recursive: true });
  const db = new Database(path, { create: true, strict: true });
  db.exec("PRAGMA journal_mode = WAL; PRAGMA busy_timeout = 5000;");
  // the index is a belief, always safe to delete (§18.4.2): one of another schema is dropped and re-inventoried
  const hasMeta = db.query<{ n: number }, []>("SELECT count(*) AS n FROM sqlite_master WHERE name = 'meta'").get()!.n > 0;
  const found = hasMeta ? db.query<{ value: string }, []>("SELECT value FROM meta WHERE key = 'schema'").get()?.value : undefined;
  if (hasMeta && found !== VERSION) for (const t of TABLES) db.exec(`DROP TABLE IF EXISTS ${t}`);
  db.exec(SCHEMA);
  db.run("INSERT OR IGNORE INTO meta (key, value) VALUES ('schema', ?)", [VERSION]);
  const delivered = (receipt: string) =>
    db
      .query<{ testimony: string; name: string }, [string]>("SELECT testimony, name FROM delivered WHERE receipt = ? ORDER BY rowid")
      .all(receipt);
  const rowOf = (r: Omit<ReceiptRow, "testimony">): ReceiptRow => ({
    ...r,
    testimony: delivered(r.receipt).map((d) => ({ hash: d.testimony, name: d.name })),
  });
  return {
    db,
    putCopy(c) {
      db.run(
        `INSERT INTO copies (store, tree, hash, state, size, verified_at, generation, link) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT (store, hash) DO UPDATE SET state = excluded.state, size = excluded.size,
           verified_at = COALESCE(excluded.verified_at, copies.verified_at), generation = excluded.generation,
           link = CASE WHEN excluded.state = 'missing' THEN NULL ELSE COALESCE(excluded.link, copies.link) END`,
        [c.store, c.tree, c.hash, c.state, c.size, c.verified_at, c.generation, c.link ?? null],
      );
    },
    copies: (hash) => db.query<Copy, [string]>("SELECT * FROM copies WHERE hash = ? ORDER BY store").all(hash),
    copiesOn: (store) => db.query<Copy, [string]>("SELECT * FROM copies WHERE store = ? ORDER BY hash").all(store),
    hashes: (tree) =>
      db
        .query<{ hash: string }, [string]>("SELECT DISTINCT hash FROM copies WHERE tree = ? AND state != 'missing' ORDER BY hash")
        .all(tree)
        .map((r) => r.hash),
    nextGeneration(store) {
      const key = `generation:${store}`;
      const n = Number(db.query<{ value: string }, [string]>("SELECT value FROM meta WHERE key = ?").get(key)?.value ?? 0) + 1;
      db.run("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", [key, String(n)]);
      return n;
    },
    putObserved(store, rows) {
      db.transaction(() => {
        const links = new Map(
          db
            .query<{ path: string; hash: string; link: string | null }, [string]>("SELECT path, hash, link FROM observed WHERE store = ?")
            .all(store)
            .map((r) => [r.path, r]),
        );
        db.run("DELETE FROM observed WHERE store = ?", [store]);
        for (const r of rows) {
          const was = links.get(r.path);
          db.run("INSERT INTO observed (store, path, hash, size, mtime, generation, link) VALUES (?, ?, ?, ?, ?, ?, ?)", [
            store,
            r.path,
            r.hash,
            r.size,
            r.mtime,
            r.generation,
            was && was.hash === r.hash ? was.link : null,
          ]);
        }
      })();
    },
    observed(where) {
      const clauses: string[] = [];
      const args: string[] = [];
      for (const k of ["store", "hash", "path"] as const)
        if (where[k] !== undefined) {
          clauses.push(`${k} = ?`);
          args.push(where[k]!);
        }
      return db
        .query<ObservedRow, string[]>(
          `SELECT * FROM observed${clauses.length ? ` WHERE ${clauses.join(" AND ")}` : ""} ORDER BY store, path`,
        )
        .all(...args);
    },
    setObservedLink: (store, path, link) => void db.run("UPDATE observed SET link = ? WHERE store = ? AND path = ?", [link, store, path]),
    putReceipt(r) {
      db.transaction(() => {
        db.run("INSERT OR IGNORE INTO receipts (receipt, instance, artifact, name, received, actor) VALUES (?, ?, ?, ?, ?, ?)", [
          r.receipt,
          r.instance,
          r.artifact,
          r.name,
          r.received,
          r.actor,
        ]);
        for (const t of r.testimony)
          db.run("INSERT OR IGNORE INTO delivered (receipt, testimony, name, subject) VALUES (?, ?, ?, ?)", [
            r.receipt,
            t.hash,
            t.name,
            r.artifact,
          ]);
      })();
    },
    receipts(where) {
      const clauses: string[] = [];
      const args: string[] = [];
      if (where.artifact) {
        clauses.push("artifact = ?");
        args.push(where.artifact);
      }
      if (where.instance) {
        clauses.push("instance = ?");
        args.push(where.instance);
      }
      const sql = `SELECT receipt, instance, artifact, name, received, actor FROM receipts${clauses.length ? ` WHERE ${clauses.join(" AND ")}` : ""} ORDER BY received, receipt`;
      return db
        .query<Omit<ReceiptRow, "testimony">, string[]>(sql)
        .all(...args)
        .map(rowOf);
    },
    testimonyOf: (instance) =>
      db
        .query<{ hash: string; subject: string; name: string; receipt: string }, [string]>(
          "SELECT d.testimony AS hash, d.subject, d.name, d.receipt FROM delivered d JOIN receipts r ON r.receipt = d.receipt WHERE r.instance = ? ORDER BY r.received, d.rowid",
        )
        .all(instance),
    close: () => db.close(),
  };
}
