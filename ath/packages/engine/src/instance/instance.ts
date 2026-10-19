// instance.ts — an instance and the chain it builds on (spec §4): the instance pointed at, read from its working
// tree and the only one written; every base read at its pinned commit and no other, materialised from git into the
// host's cache (§5.6). A subject resolves in the instance first, then down the chain; a record is never overridden
// or split — an extension's record of a base's artifact holds only its own receipts and origins (§4.4).
import { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { AthError } from "@ath/kit/errors.ts";
import { writeAtomic } from "@ath/kit/fs.ts";
import { CONFIG_FILE } from "@ath/kit/root.ts";
import type { HostPaths } from "@ath/kit/xdg.ts";
import { emitRecord, loadRecord, type RecordDoc } from "../record/document.ts";
import { type InstanceConfig, parseConfig } from "./config.ts";

export interface Instance {
  /** Where its files are read from: the working tree for the instance pointed at, the cache for a base. */
  root: string;
  config: InstanceConfig;
  /** The instance this one extends, at its pinned commit. */
  base: Instance | null;
  /** True for every instance but the one pointed at: nothing writes to a base (§4.1). */
  readonly: boolean;
  /** The commit a base is read at. */
  commit?: string;
}

const run = (argv: string[], cwd?: string, stdin?: Uint8Array) => {
  if (!Bun.which(argv[0]!)) throw new AthError("CONFIG", `${argv[0]} is not on PATH; it is needed to read a base at its pinned commit`);
  const r = Bun.spawnSync(argv, {
    cwd,
    stdin: stdin ? new Blob([stdin as unknown as ArrayBuffer]) : undefined,
    stdout: "pipe",
    stderr: "pipe",
  });
  return { ok: r.exitCode === 0, out: new Uint8Array(r.stdout), err: r.stderr.toString().trim() };
};

/** The commit HEAD names in a base's repository. */
export function headCommit(path: string): string {
  const r = run(["git", "-C", path, "rev-parse", "HEAD"]);
  if (!r.ok) throw new AthError("CONFIG", `${path} is not a git repository with a commit: ${r.err}`);
  return new TextDecoder().decode(r.out).trim();
}

/** A base's tracked files at `commit`, materialised once under the host's cache (§5.6) and read from there. */
function materialise(host: HostPaths, path: string, commit: string, where: string): string {
  const show = run(["git", "-C", path, "show", `${commit}:${CONFIG_FILE}`]);
  if (!show.ok) throw new AthError("CONFIG", `${where}: the base at ${path} has no ${CONFIG_FILE} at commit ${commit} (${show.err})`);
  const cfg = parseConfig(new TextDecoder().decode(show.out), `${path}@${commit.slice(0, 12)}/${CONFIG_FILE}`);
  const dir = join(host.cache, "bases", cfg.id, commit);
  if (existsSync(join(dir, CONFIG_FILE))) return dir;
  const archive = run(["git", "-C", path, "archive", "--format=tar", commit]);
  if (!archive.ok) throw new AthError("CONFIG", `${where}: cannot read the base at ${path}@${commit}: ${archive.err}`);
  const tmp = `${dir}.${process.pid}.tmp`;
  rmSync(tmp, { recursive: true, force: true });
  mkdirSync(tmp, { recursive: true });
  const x = run(["tar", "-x", "-C", tmp], undefined, archive.out);
  if (!x.ok) throw new AthError("EXTERNAL", `tar could not unpack the base: ${x.err}`);
  mkdirSync(dirname(dir), { recursive: true });
  try {
    renameSync(tmp, dir);
  } catch {
    rmSync(tmp, { recursive: true, force: true }); // another process materialised it first
  }
  return dir;
}

/** Load the instance at `root` and its chain (§19.2.1). A cycle, a missing base or commit, or a bad file is CONFIG. */
export function openInstance(root: string, host: HostPaths): Instance {
  const seen: string[] = [];
  const load = (dir: string, readonly: boolean, commit?: string, origin?: string): Instance => {
    const file = join(dir, CONFIG_FILE);
    if (!existsSync(file)) throw new AthError("CONFIG", `no ${CONFIG_FILE} at ${dir}`);
    const config = parseConfig(readFileSync(file, "utf8"), file);
    if (seen.includes(config.id)) throw new AthError("CONFIG", `the chain of bases is a cycle: ${[...seen, config.id].join(" → ")}`);
    seen.push(config.id);
    let base: Instance | null = null;
    if (config.extends) {
      const from = origin ?? dir;
      const path = resolve(from, config.extends.path);
      if (!existsSync(path)) throw new AthError("CONFIG", `${file}: the base at ${config.extends.path} (${path}) is missing`);
      base = load(materialise(host, path, config.extends.commit, file), true, config.extends.commit, path);
    }
    return { root: dir, config, base, readonly, ...(commit ? { commit } : {}) };
  };
  return load(resolve(root), false);
}

/** The chain, the instance pointed at first. */
export function chain(i: Instance): Instance[] {
  const out: Instance[] = [];
  for (let x: Instance | null = i; x; x = x.base) out.push(x);
  return out;
}

// ── records ─────────────────────────────────────────────────────────────────────────────────────────────────────────

export const recordPath = (i: Instance, hash: string): string => {
  const n = i.config.shard.records;
  return join(i.root, "corpus", "records", ...(n ? [hash.slice(0, n)] : []), `${hash}.yaml`);
};

/** The record this instance itself holds for `hash`, or null. */
export function ownRecord(i: Instance, hash: string): RecordDoc | null {
  const p = recordPath(i, hash);
  return existsSync(p) ? loadRecord(readFileSync(p, "utf8"), relative(i.root, p)) : null;
}

/** A subject's record across the chain (§4.4): the deepest instance that holds its projection gives it, and every
 * instance above adds its own receipts and origins. Null when nothing in the chain has a record of it. */
export function recordView(i: Instance, hash: string): { record: RecordDoc; holder: Instance } | null {
  const layers = chain(i)
    .map((x) => ({ x, r: ownRecord(x, hash) }))
    .filter((l): l is { x: Instance; r: RecordDoc } => l.r !== null);
  if (!layers.length) return null;
  const deepest = layers[layers.length - 1]!;
  const record: RecordDoc = { ...deepest.r };
  for (const l of layers.slice(0, -1).reverse()) {
    if (l.r.receipts) record.receipts = [...(record.receipts ?? []), ...l.r.receipts];
    if (l.r.origins) record.origins = [...(record.origins ?? []), ...l.r.origins];
  }
  return { record, holder: deepest.x };
}

export function writeRecord(i: Instance, hash: string, r: RecordDoc): string {
  if (i.readonly) throw new AthError("CONFLICT", `${i.config.name} is a base and is read-only here`);
  const p = recordPath(i, hash);
  writeAtomic(p, emitRecord(r));
  return relative(i.root, p);
}

/** Every artifact hash this instance itself has a record of, by walking its records directory. */
export function ownRecords(i: Instance): string[] {
  const dir = join(i.root, "corpus", "records");
  if (!existsSync(dir)) return [];
  const out: string[] = [];
  const walk = (d: string) => {
    for (const n of readdirSync(d, { withFileTypes: true })) {
      if (n.isDirectory()) walk(join(d, n.name));
      else if (/^[0-9a-f]{64}\.yaml$/.test(n.name)) out.push(n.name.slice(0, 64));
    }
  };
  walk(dir);
  return out.sort();
}

/** What the chain holds (§5.7): every record's artifact, with the instance whose record gives its projection. */
export function holdings(i: Instance): Map<string, Instance> {
  const out = new Map<string, Instance>();
  for (const x of chain(i).reverse()) for (const h of ownRecords(x)) if (!out.has(h)) out.set(h, x);
  return out;
}

export interface ContainerRef {
  container: string;
  path: string;
  kind: "asset" | "part";
}

/** Which held containers list each constituent (§7.2.3, §12): derived from the constituents in their intrinsics. */
export function containersIndex(i: Instance): Map<string, ContainerRef[]> {
  const out = new Map<string, ContainerRef[]>();
  for (const h of holdings(i).keys()) {
    const v = recordView(i, h);
    const cs = v?.record.intrinsics?.constituents;
    if (!Array.isArray(cs)) continue;
    for (const c of cs as { path: string; blake3: string; kind: "asset" | "part" }[]) {
      const list = out.get(c.blake3) ?? [];
      list.push({ container: h, path: c.path, kind: c.kind });
      out.set(c.blake3, list);
    }
  }
  return out;
}

/** Resolve a hash or a prefix of 8 or more hex digits to the one full hash it names among `known` (§7.1.3). */
export function resolvePrefix(prefix: string, known: Iterable<string>): string {
  const p = prefix
    .replace(/^ath:\/\//, "")
    .replace(/^b3:/, "")
    .toLowerCase();
  if (!/^[0-9a-f]{8,64}$/.test(p)) throw new AthError("USAGE", `'${prefix}' is not a hash or a prefix of 8 or more hex digits`);
  const hits = new Set<string>();
  for (const h of known) if (h.startsWith(p)) hits.add(h);
  if (hits.size === 0) throw new AthError("NOT_FOUND", `nothing the chain holds has a hash beginning ${p}`);
  if (hits.size > 1) throw new AthError("USAGE", `${p} is ambiguous: ${[...hits].map((h) => h.slice(0, 12)).join(", ")}`);
  return [...hits][0]!;
}

/** The shortest prefix, of 8 or more digits, that names `hash` alone among `known`. */
export function shortest(hash: string, known: Iterable<string>): string {
  const all = [...known];
  for (let n = 8; n < 64; n++) {
    const p = hash.slice(0, n);
    if (all.filter((h) => h.startsWith(p)).length <= 1) return p;
  }
  return hash;
}
