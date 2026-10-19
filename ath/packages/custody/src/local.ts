// local.ts — the host's local store (spec §18.2.3): a managed store at $XDG_DATA_HOME/athenaeum/, its trees
// `artifacts/` and `testimony/` laid out by hash, its id written into the store itself so the store is recognised
// wherever it is. A put writes under a temporary name, verifies the BLAKE3 as the bytes are written, and renames
// into place (§18.3.1); a read verifies again (§18.1). The local store holds without persisting: it is evictable.
import { constants, copyFileSync, existsSync, linkSync, mkdirSync, readFileSync, renameSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { AthError } from "@ath/kit/errors.ts";
import { fsyncDir, writeAtomic, writeTemp } from "@ath/kit/fs.ts";
import { blake3Hex } from "@ath/kit/hash.ts";
import { UUID } from "@ath/kit/root.ts";

export type Tree = "artifacts" | "testimony";

export interface LocalStore {
  id: string;
  dir: string;
  path(tree: Tree, hash: string): string;
  has(tree: Tree, hash: string): boolean;
  /** Place bytes under their hash; refuses bytes that are not the hash. Returns whether they were new here. */
  put(tree: Tree, hash: string, bytes: Uint8Array): Promise<boolean>;
  /** The bytes, verified against their hash, or null when the store does not hold them. */
  get(tree: Tree, hash: string): Promise<Uint8Array | null>;
  /** Place a file of an observed tree by the first link method the filesystem supports, else by copy (§18.5.3); the
   * placed file is verified before it takes its name. Returns how, or `present` when the store already holds it. */
  link(
    tree: Tree,
    hash: string,
    src: string,
    methods: readonly ("reflink" | "hardlink")[],
  ): Promise<"reflink" | "hardlink" | "copy" | "present">;
  /** Remove a copy (eviction, or bytes found not to be their hash). */
  remove(tree: Tree, hash: string): void;
}

const ID_FILE = "store.yaml";

export function openLocalStore(dir: string): LocalStore {
  mkdirSync(dir, { recursive: true });
  const idPath = join(dir, ID_FILE);
  let id: string;
  if (existsSync(idPath)) {
    const doc = Bun.YAML.parse(readFileSync(idPath, "utf8")) as { id?: unknown } | null;
    if (typeof doc?.id !== "string" || !UUID.test(doc.id)) throw new AthError("CONFIG", `${idPath} names no store id`);
    id = doc.id;
  } else {
    id = crypto.randomUUID();
    writeAtomic(idPath, `id: ${id}\nrole: managed\ntags: [local]\n`);
  }
  const path = (tree: Tree, hash: string) => join(dir, tree, hash.slice(0, 2), hash);
  return {
    id,
    dir,
    path,
    has: (tree, hash) => existsSync(path(tree, hash)),
    async put(tree, hash, bytes) {
      const p = path(tree, hash);
      if (existsSync(p)) return false;
      const got = await blake3Hex(bytes);
      if (got !== hash) throw new AthError("CONFLICT", `bytes hash to ${got}, not ${hash}`);
      const tmp = writeTemp(p, bytes, 0o444);
      // a copy verified at write: re-hash what landed before it takes the name (§19.3.1)
      if ((await blake3Hex(new Uint8Array(readFileSync(tmp)))) !== hash) {
        rmSync(tmp, { force: true });
        throw new AthError("EXTERNAL", `the copy of ${hash} did not verify as written`);
      }
      mkdirSync(dirname(p), { recursive: true });
      renameSync(tmp, p);
      fsyncDir(dirname(p));
      return true;
    },
    async link(tree, hash, src, methods) {
      const p = path(tree, hash);
      if (existsSync(p)) return "present";
      mkdirSync(dirname(p), { recursive: true });
      const tmp = `${p}.${process.pid}.tmp`;
      let how: "reflink" | "hardlink" | "copy" = "copy";
      for (const m of methods) {
        try {
          if (m === "reflink") copyFileSync(src, tmp, constants.COPYFILE_FICLONE_FORCE);
          else linkSync(src, tmp);
          how = m;
          break;
        } catch {
          rmSync(tmp, { force: true });
        }
      }
      // a hardlink shares the observed file's inode: its mode is the observed file's, and is left alone
      if (how === "copy") copyFileSync(src, tmp);
      if ((await blake3Hex(new Uint8Array(readFileSync(tmp)))) !== hash) {
        rmSync(tmp, { force: true });
        throw new AthError("CONFLICT", `${src} no longer hashes to ${hash}`);
      }
      renameSync(tmp, p);
      fsyncDir(dirname(p));
      return how;
    },
    remove: (tree, hash) => rmSync(path(tree, hash), { force: true }),
    async get(tree, hash) {
      const p = path(tree, hash);
      if (!existsSync(p)) return null;
      const b = new Uint8Array(readFileSync(p));
      if ((await blake3Hex(b)) !== hash) throw new AthError("CONFLICT", `the local copy of ${hash} is corrupt`);
      return b;
    },
  };
}
