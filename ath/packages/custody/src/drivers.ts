// drivers.ts — how a store is reached (spec §18.3): `capabilities`; `inventory()` — what is present, with sizes; `has`;
// `get`; `put`; `remove`; `stat` — used and free space where it can tell. A managed store's driver puts under a
// temporary name and renames once the hash is verified. `local` is a directory on this host; `rclone` is any backend
// rclone reaches. An observed tree is read by path and inventoried through the scanner's published manifest (§18.5).
import { Database } from "bun:sqlite";
import { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, statfsSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { AthError } from "@ath/kit/errors.ts";
import { fsyncDir, writeTemp } from "@ath/kit/fs.ts";
import { blake3Hex } from "@ath/kit/hash.ts";
import type { Tree } from "./local.ts";
import type { Access, StoreDecl } from "./stores.ts";

export interface Present {
  tree: Tree;
  hash: string;
  size: number;
}

export interface ObservedFile {
  path: string;
  hash: string;
  size: number;
  mtime: string;
  birth: string | null;
  generation: number;
}

/** What an observed tree's published manifest says of itself: the scanner and host that wrote it, and when each
 * generation finished. */
export interface ManifestInfo {
  scanner: string;
  host: string | null;
  root: string;
  generation: number;
  finished: Map<number, string>;
}

export interface Driver {
  decl: StoreDecl;
  capabilities: string[];
  inventory(): Promise<Present[]>;
  has(tree: Tree, hash: string): Promise<boolean>;
  get(tree: Tree, hash: string): Promise<Uint8Array | null>;
  put(tree: Tree, hash: string, bytes: Uint8Array): Promise<void>;
  remove(tree: Tree, hash: string): Promise<void>;
  stat(): Promise<{ used?: number; free?: number }>;
  /** An observed tree's files, from the scanner's manifest. */
  observed?(): ObservedFile[];
  /** An observed tree's root on this host, for links. */
  root?: string;
  manifest?(): ManifestInfo | null;
}

const TREES: Tree[] = ["artifacts", "testimony"];

export function localDriver(decl: StoreDecl, root: string): Driver {
  if (decl.role === "observed") return observedDriver(decl, root);
  const path = (t: Tree, h: string) => join(root, t, h.slice(0, 2), h);
  return {
    decl,
    capabilities: ["inventory", "get", "put", "remove", "stat"],
    async inventory() {
      const out: Present[] = [];
      for (const t of TREES) {
        const dir = join(root, t);
        if (!existsSync(dir)) continue;
        for (const shard of readdirSync(dir))
          for (const h of readdirSync(join(dir, shard)))
            if (/^[0-9a-f]{64}$/.test(h)) out.push({ tree: t, hash: h, size: statSync(join(dir, shard, h)).size });
      }
      return out;
    },
    has: async (t, h) => existsSync(path(t, h)),
    async get(t, h) {
      const p = path(t, h);
      return existsSync(p) ? new Uint8Array(readFileSync(p)) : null;
    },
    async put(t, h, bytes) {
      const p = path(t, h);
      if (existsSync(p)) return;
      if ((await blake3Hex(bytes)) !== h) throw new AthError("CONFLICT", `bytes hash otherwise than ${h}`);
      const tmp = writeTemp(p, bytes, 0o444);
      if ((await blake3Hex(new Uint8Array(readFileSync(tmp)))) !== h) {
        rmSync(tmp, { force: true });
        throw new AthError("EXTERNAL", `the copy of ${h} in ${decl.name} did not verify as written`);
      }
      mkdirSync(dirname(p), { recursive: true });
      renameSync(tmp, p);
      fsyncDir(dirname(p));
    },
    remove: async (t, h) => rmSync(path(t, h), { force: true }),
    async stat() {
      try {
        const s = statfsSync(root);
        return { free: s.bavail * s.bsize, used: (s.blocks - s.bfree) * s.bsize };
      } catch {
        return {};
      }
    },
  };
}

/** An observed tree: its files keep their own paths; the scanner's `manifest.sqlite` says what each hashes to. */
export function observedDriver(decl: StoreDecl, root: string): Driver {
  const manifest = join(root, ".athenaeum", "manifest.sqlite");
  // the manifest is the scanner's own versioned contract (§18.5.1): a schema this reader does not know fails closed
  const open = () => {
    const db = new Database(manifest, { readonly: true, safeIntegers: true });
    const v = Number(db.query<{ user_version: bigint }, []>("PRAGMA user_version").get()?.user_version ?? 0);
    if (v !== 2 && v !== 3) {
      db.close();
      throw new AthError("CONFIG", `${manifest}: manifest schema ${v}; this reader knows 2 and 3`);
    }
    return db;
  };
  const info = (): ManifestInfo | null => {
    if (!existsSync(manifest)) return null;
    const db = open();
    try {
      const meta = new Map(
        db
          .query<{ key: string; value: string }, []>("SELECT key, value FROM meta")
          .all()
          .map((r) => [r.key, r.value]),
      );
      const gens = db
        .query<{ generation: bigint; finished_at: string | null; scanner: string }, []>(
          "SELECT generation, finished_at, scanner FROM generations ORDER BY generation",
        )
        .all();
      const done = gens.filter((g) => g.finished_at !== null);
      const second = (iso: string) => `${iso.slice(0, 19)}Z`;
      return {
        scanner: done.at(-1)?.scanner ?? meta.get("scanner") ?? "unknown",
        host: meta.get("host") ?? null,
        root: meta.get("root") ?? root,
        generation: Number(done.at(-1)?.generation ?? 0n),
        finished: new Map(done.map((g) => [Number(g.generation), second(g.finished_at!)])),
      };
    } finally {
      db.close();
    }
  };
  const files = (): ObservedFile[] => {
    if (!existsSync(manifest)) return [];
    const db = open();
    try {
      const rows = db
        .query<{ path: string; blake3: string; size: bigint; mtime_ns: bigint; btime_ns: bigint | null; generation: bigint }, []>(
          "SELECT p.path, i.blake3, i.size, i.mtime_ns, i.btime_ns, i.generation FROM paths p JOIN identities i ON i.dev = p.dev AND i.ino = p.ino ORDER BY p.path",
        )
        .all();
      const iso = (ns: bigint) => `${new Date(Number(ns / 1000000n)).toISOString().slice(0, 19)}Z`;
      return rows.map((r) => ({
        path: r.path,
        hash: r.blake3,
        size: Number(r.size),
        mtime: iso(r.mtime_ns),
        birth: r.btime_ns === null ? null : iso(r.btime_ns),
        generation: Number(r.generation),
      }));
    } finally {
      db.close();
    }
  };
  return {
    decl,
    root,
    capabilities: ["inventory", "get", "stat"],
    inventory: async () => files().map((f) => ({ tree: "artifacts" as Tree, hash: f.hash, size: f.size })),
    has: async (t, h) => t === "artifacts" && files().some((f) => f.hash === h),
    async get(t, h) {
      if (t !== "artifacts") return null;
      for (const f of files().filter((x) => x.hash === h)) {
        const p = join(root, f.path);
        if (!existsSync(p)) continue;
        const b = new Uint8Array(readFileSync(p));
        if ((await blake3Hex(b)) === h) return b;
      }
      return null;
    },
    put: async () => {
      throw new AthError("CONFLICT", `${decl.name} is an observed tree: custody reads it and never writes it`);
    },
    remove: async () => {
      throw new AthError("CONFLICT", `${decl.name} is an observed tree: custody never removes from it`);
    },
    stat: async () => ({}),
    observed: files,
    manifest: info,
  };
}

/** rclone: every backend it reaches. The remote root holds `artifacts/` and `testimony/` as the local store does. */
export function rcloneDriver(decl: StoreDecl, remote: string, bin = "rclone"): Driver {
  const run = (args: string[], stdin?: Uint8Array) => {
    const exe = Bun.which(bin, { PATH: process.env.PATH ?? "" });
    if (!exe) throw new AthError("EXTERNAL", `${bin} is not on PATH; ${decl.name} is reached through it`);
    const r = Bun.spawnSync([exe, ...args], {
      stdin: stdin ? new Blob([stdin as unknown as ArrayBuffer]) : undefined,
      stdout: "pipe",
      stderr: "pipe",
      env: process.env,
    });
    return { ok: r.exitCode === 0, code: r.exitCode, out: new Uint8Array(r.stdout), err: r.stderr.toString().trim() };
  };
  const at = (t: Tree, h: string) => `${remote.replace(/\/$/, "")}/${t}/${h.slice(0, 2)}/${h}`;
  return {
    decl,
    capabilities: ["inventory", "get", "put", "remove", "stat"],
    async inventory() {
      const out: Present[] = [];
      for (const t of TREES) {
        const r = run(["lsjson", "-R", "--files-only", `${remote.replace(/\/$/, "")}/${t}`]);
        // rclone exits 3 for a directory that is not there: an empty tree; anything else is a store not answering,
        // which an inventory must not mistake for a store that lost everything
        if (r.code === 3) continue;
        if (!r.ok) throw new AthError("EXTERNAL", `rclone lsjson in ${decl.name}: ${r.err}`);
        for (const e of JSON.parse(new TextDecoder().decode(r.out) || "[]") as { Name: string; Size: number }[])
          if (/^[0-9a-f]{64}$/.test(e.Name)) out.push({ tree: t, hash: e.Name, size: e.Size });
      }
      return out;
    },
    async has(t, h) {
      const r = run(["lsjson", at(t, h)]);
      return r.ok && r.out.length > 2;
    },
    async get(t, h) {
      const r = run(["cat", at(t, h)]);
      return r.ok && r.out.length ? r.out : null;
    },
    async put(t, h, bytes) {
      if ((await blake3Hex(bytes)) !== h) throw new AthError("CONFLICT", `bytes hash otherwise than ${h}`);
      const tmp = `${at(t, h)}.${process.pid}.tmp`;
      const w = run(["rcat", tmp], bytes);
      if (!w.ok) throw new AthError("EXTERNAL", `rclone rcat into ${decl.name}: ${w.err}`);
      const back = run(["cat", tmp]);
      if (!back.ok || (await blake3Hex(back.out)) !== h) {
        run(["deletefile", tmp]);
        throw new AthError("EXTERNAL", `the copy of ${h} in ${decl.name} did not verify as written`);
      }
      const mv = run(["moveto", tmp, at(t, h)]);
      if (!mv.ok) throw new AthError("EXTERNAL", `rclone moveto in ${decl.name}: ${mv.err}`);
    },
    async remove(t, h) {
      const r = run(["deletefile", at(t, h)]);
      if (!r.ok) throw new AthError("EXTERNAL", `rclone deletefile in ${decl.name}: ${r.err}`);
    },
    async stat() {
      const r = run(["about", "--json", remote]);
      if (!r.ok) return {};
      const j = JSON.parse(new TextDecoder().decode(r.out)) as { used?: number; free?: number };
      return { ...(j.used !== undefined ? { used: j.used } : {}), ...(j.free !== undefined ? { free: j.free } : {}) };
    },
  };
}

/** A store's driver on this host, or null when the access file says nothing of it (the store is unavailable here). A
 * store declaring client encryption is never reached by this tool, which does not encrypt: it writes no plaintext
 * there. */
export function driverFor(decl: StoreDecl, access: Access | undefined): Driver | null {
  if (!access || decl.encryption === "client") return null;
  if (decl.driver === "local") return access.path ? localDriver(decl, access.path) : null;
  return access.remote ? rcloneDriver(decl, access.remote) : null;
}
