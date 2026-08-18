// Catalog metadata: contract v3 (spec/corpus.md §12.1.1 *(25)*). The v2->v3 in-place
// migration, stat-fact capture/refresh at hash and walk time, the mime_claim sniff (both hash
// paths) and its walk-time backfill for pre-existing NULL rows, and a v2 seed source still
// being accepted (NULL catalog columns). See MANIFEST-SCHEMA.md's v3 section for the contract
// this exercises, and sniff.test.ts for the sniffer's own pure-function coverage.

import { test, expect, afterAll } from "bun:test";
import { Database } from "bun:sqlite";
import { join } from "node:path";
import { mkdir, chmod, stat } from "node:fs/promises";
import { Manifest } from "../src/manifest.ts";
import { identityKey, MANIFEST_DIRNAME, STATE_FILENAME, SCHEMA_VERSION } from "../src/schema.ts";
import { toBtimeNs } from "../src/scanner.ts";
import { tmpTree, put, runScan, loadState, quietLog, cleanupAll } from "./fixtures.ts";

afterAll(cleanupAll);

const MT = 1_700_000_000;
const FIXTURES = join(import.meta.dir, "fixtures");
const GOOD_B3SUM = join(FIXTURES, "fake-b3sum-good.ts");

// ── toBtimeNs (scanner.ts): the null-when-unsupported mapping ───────────────────────────

test("toBtimeNs: raw 0n (fs reports no birth time) maps to null; any other value passes through unchanged", () => {
  expect(toBtimeNs(0n)).toBeNull();
  expect(toBtimeNs(1n)).toBe(1n);
  expect(toBtimeNs(1_700_000_000_123_456_789n)).toBe(1_700_000_000_123_456_789n);
});

// ── v2 -> v3 migration ────────────────────────────────────────────────────────────────────

const V2_DDL = `
PRAGMA user_version = 2;
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

test("v2 -> v3 migration: columns added, user_version bumped, old rows keep their data with NULL catalog columns", async () => {
  const root = await tmpTree();
  const manifestDir = join(root, MANIFEST_DIRNAME);
  await mkdir(manifestDir, { recursive: true });
  const statePath = join(manifestDir, STATE_FILENAME);

  const build = new Database(statePath, { create: true });
  build.run(V2_DDL);
  const now = new Date().toISOString();
  const insMeta = build.query<never, [string, string]>("INSERT INTO meta (key, value) VALUES (?,?)");
  insMeta.run("schema", "2");
  insMeta.run("scanner", "0.2.3");
  insMeta.run("root", root);
  insMeta.run("created_at", now);
  build
    .query<never, [number, number, number, number, string, number]>("INSERT INTO identities (dev,ino,size,mtime_ns,blake3,generation) VALUES (?,?,?,?,?,?)")
    .run(1, 2, 5, MT, "a".repeat(64), 1);
  build.query<never, [string, number, number, number]>("INSERT INTO paths (path,dev,ino,generation) VALUES (?,?,?,?)").run("old.txt", 1, 2, 1);
  build
    .query<never, [number, string, string, string, string, string]>(
      "INSERT INTO generations (generation,mode,scanner,started_at,finished_at,summary_json) VALUES (?,?,?,?,?,?)",
    )
    .run(1, "cold", "0.2.3", now, now, "{}");
  build.close();

  const mf = await Manifest.open(manifestDir, root, quietLog);
  const identities = mf.dumpIdentities();
  await mf.close();

  const id = identities.get(identityKey(1n, 2n))!;
  expect(id).toBeDefined();
  expect(id.size).toBe(5n); // old row's original data survives the migration untouched
  expect(id.mtimeNs).toBe(BigInt(MT));
  expect(id.blake3).toBe("a".repeat(64));
  expect(id.generation).toBe(1);
  expect(id.ctimeNs).toBeNull();
  expect(id.btimeNs).toBeNull();
  expect(id.mode).toBeNull();
  expect(id.mimeClaim).toBeNull();

  const check = new Database(statePath, { readonly: true });
  try {
    const uv = check.query<{ user_version: number }, []>("PRAGMA user_version").get()!;
    expect(Number(uv.user_version)).toBe(SCHEMA_VERSION);
    const cols = check.query<{ name: string }, []>("PRAGMA table_info(identities)").all().map((r) => r.name);
    for (const c of ["ctime_ns", "btime_ns", "mode", "mime_claim"]) expect(cols.includes(c)).toBe(true);
    const schemaMeta = check.query<{ value: string }, []>("SELECT value FROM meta WHERE key='schema'").get()!;
    expect(schemaMeta.value).toBe(String(SCHEMA_VERSION));
  } finally {
    check.close();
  }
});

// ── new identity: stat facts + mime_claim written at hash time ─────────────────────────────

test("a new identity carries stat facts and an accurate mime_claim at hash time (WASM path)", async () => {
  const root = await tmpTree();
  const PNG_HEADER = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3, 4]);
  const abs = await put(root, "img.png", PNG_HEADER, MT);
  const PDF_HEADER = Buffer.from("%PDF-1.4\nsome content\n");
  await put(root, "doc.pdf", PDF_HEADER, MT);

  const { summary } = await runScan(root);
  expect(summary.sniffed).toBe(2);

  const { identities, paths } = await loadState(join(root, MANIFEST_DIRNAME), root);

  const pngRef = paths.get("img.png")!;
  const pngId = identities.get(identityKey(pngRef.dev, pngRef.ino))!;
  expect(pngId.mimeClaim).toBe("image/png");
  expect(pngId.ctimeNs).not.toBeNull();
  expect(pngId.mode).not.toBeNull();
  const st = await stat(abs, { bigint: true });
  expect(pngId.mode).toBe(st.mode); // round-trips the real stat mode

  const pdfRef = paths.get("doc.pdf")!;
  const pdfId = identities.get(identityKey(pdfRef.dev, pdfRef.ino))!;
  expect(pdfId.mimeClaim).toBe("application/pdf");
});

test("an unrecognized binary yields a null mime_claim and isn't counted in `sniffed`", async () => {
  const root = await tmpTree();
  await put(root, "blob.bin", Buffer.from([0xde, 0xad, 0xbe, 0xef, 0x80, 0x81, 0x82]), MT);

  const { summary } = await runScan(root);
  expect(summary.sniffed).toBe(0);

  const { identities, paths } = await loadState(join(root, MANIFEST_DIRNAME), root);
  const ref = paths.get("blob.bin")!;
  expect(identities.get(identityKey(ref.dev, ref.ino))!.mimeClaim).toBeNull();
});

// ── chmod: mode refreshed with zero re-hash ─────────────────────────────────────────────

test("chmod on an already-known identity refreshes mode (and ctime) with zero re-hash", async () => {
  const root = await tmpTree();
  const abs = await put(root, "a.txt", "stable content", MT);
  await runScan(root);

  const before = await loadState(join(root, MANIFEST_DIRNAME), root);
  const ref = before.paths.get("a.txt")!;
  const beforeId = before.identities.get(identityKey(ref.dev, ref.ino))!;

  await chmod(abs, 0o600);

  const { summary, hashCount } = await runScan(root);
  expect(hashCount).toBe(0); // chmod doesn't touch mtime -> content still known, no re-hash
  expect(summary.hashed).toBe(0);

  const after = await loadState(join(root, MANIFEST_DIRNAME), root);
  const afterId = after.identities.get(identityKey(ref.dev, ref.ino))!;
  expect(afterId.mode).not.toBeNull();
  expect(afterId.mode).not.toBe(beforeId.mode);
  expect(Number(afterId.mode!) & 0o777).toBe(0o600);
  expect(afterId.ctimeNs).not.toBeNull();
});

// ── backfill: pre-existing NULL mime_claim gets sniffed on the next walk ────────────────────

test("backfill: a known identity with NULL mime_claim gets sniffed on the next walk (no re-hash); `sniffed` counts it", async () => {
  const root = await tmpTree();
  const PNG_HEADER = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3, 4]);
  await put(root, "img.png", PNG_HEADER, MT);
  await runScan(root); // writes mime_claim = "image/png" already

  // Simulate a pre-v3 row (or a claim that previously came back null): clear it directly.
  const statePath = join(root, MANIFEST_DIRNAME, STATE_FILENAME);
  const db = new Database(statePath);
  db.run("UPDATE identities SET mime_claim = NULL");
  db.close();

  const { summary, hashCount } = await runScan(root);
  expect(hashCount).toBe(0); // backfill never re-hashes
  expect(summary.hashed).toBe(0);
  expect(summary.sniffed).toBe(1);

  const { identities, paths } = await loadState(join(root, MANIFEST_DIRNAME), root);
  const ref = paths.get("img.png")!;
  expect(identities.get(identityKey(ref.dev, ref.ino))!.mimeClaim).toBe("image/png");
});

// ── native (b3sum) path: separate bounded head-read still produces an accurate claim ────────

test("native-path sniffing: a file routed to native b3sum still gets an accurate mime_claim via its own head-read", async () => {
  const root = await tmpTree();
  const gzipLike = Buffer.concat([Buffer.from([0x1f, 0x8b, 0x08, 0]), Buffer.alloc(60, 0)]); // real gzip magic, well above a 10-byte threshold
  await put(root, "archive.gz", gzipLike, MT);

  const { summary, hashCount } = await runScan(root, { b3sumPath: GOOD_B3SUM, nativeThresholdBytes: 10 });
  expect(summary.hashedNative).toBe(1);
  expect(hashCount).toBe(0); // WASM factory never invoked for this file
  expect(summary.sniffed).toBe(1);

  const { identities, paths } = await loadState(join(root, MANIFEST_DIRNAME), root);
  const ref = paths.get("archive.gz")!;
  expect(identities.get(identityKey(ref.dev, ref.ino))!.mimeClaim).toBe("application/gzip");
});

// ── seeding: a v2 source is accepted, not hard-refused ──────────────────────────────────────

test("--seed-from accepts a v2 source manifest (not a hard refusal); imported identities carry NULL catalog columns", async () => {
  // Destination root has NO file matching the seeded content — deliberately, so the seeded
  // identity is never re-walked/re-touched at the destination (a real walked file's own
  // catalog columns get refreshed from NULL immediately, which is correct behavior but would
  // defeat this assertion — see the chmod/backfill tests above for that refresh path).
  const root = await tmpTree();
  const srcRoot = await tmpTree();
  await put(srcRoot, "x.txt", "xxx", MT);
  await runScan(srcRoot); // writes a v3 manifest

  const manifestSqlite = join(srcRoot, MANIFEST_DIRNAME, "manifest.sqlite");
  const db = new Database(manifestSqlite);
  db.run("PRAGMA user_version = 2"); // fabricate a v2 source (columns still physically present here,
  db.close(); // but seedFrom's v2 branch selects literal NULLs regardless — see manifest.ts)

  const src = await loadState(join(srcRoot, MANIFEST_DIRNAME), srcRoot);
  const srcRef = src.paths.get("x.txt")!;

  const { summary } = await runScan(root, { seedFrom: [manifestSqlite] });
  expect(summary.seeded).toBeGreaterThan(0);

  const { identities } = await loadState(join(root, MANIFEST_DIRNAME), root);
  const id = identities.get(identityKey(srcRef.dev, srcRef.ino))!;
  expect(id).toBeDefined();
  expect(id.ctimeNs).toBeNull();
  expect(id.btimeNs).toBeNull();
  expect(id.mode).toBeNull();
  expect(id.mimeClaim).toBeNull();
});

test("--seed-from still hard-errors on a genuine (non-2, non-current) schema mismatch", async () => {
  const root = await tmpTree();
  const badDir = await tmpTree();
  const badPath = join(badDir, "bad-manifest.sqlite");
  const db = new Database(badPath, { create: true });
  db.run("PRAGMA user_version = 99");
  db.close();

  await expect(runScan(root, { seedFrom: [badPath] })).rejects.toThrow();
});
