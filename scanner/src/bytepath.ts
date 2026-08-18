// Direct byte path (v0.4.0, "direct byte path"): unRAID's `/mnt/user/<share>` is an shfs FUSE
// union mount that caps aggregate read throughput well below what the underlying disks can do
// individually. Each file's backing storage element is discoverable via the `system.LOCATION`
// xattr (a disk name like `disk7`, or a pool name like `warm`); the real bytes live at
// `/mnt/<element>/<path relative to /mnt/user/>`. Reading from there bypasses FUSE entirely.
//
// DESIGN PRINCIPLE (inviolable): the share view is the truth. Identity, paths, manifest
// contents, mime sniffing — all derived from the share side, unchanged. This module's only job
// is to compute an alternate READ location for the same bytes, and to verify (via lstat) that
// it's still the same content before anything trusts it — the unRAID mover can relocate a file
// between disks at any time, and a stale backing path would silently hash the wrong bytes.

import { lstat } from "node:fs/promises";
import { join } from "node:path";
import { dlopen, FFIType, ptr } from "bun:ffi";

/**
 * A resolver from a share-side absolute path to its backing (direct) path, plus the storage
 * element name (informational — used for disk-aware scheduling). Returns `null` when the
 * element can't be determined (xattr unreadable) — callers fall back to the share path.
 * Deliberately a plain interface (not tied to unRAID) so tests can inject a fake without ffi
 * or real xattrs, and so a future non-unRAID backend can implement the same shape.
 */
export interface BytePathResolver {
  readonly mode: string;
  resolve(sharePath: string): { bytePath: string; element: string } | null;
}

// ── system.LOCATION xattr: bun:ffi getxattr(2), falling back to a `getfattr` spawn ──────────

type XattrBackend = "ffi" | "getfattr";

let cachedBackend: XattrBackend | null = null;
let ffiGetxattr: ((pathBuf: Buffer, nameBuf: Buffer, valueBuf: Buffer, size: number) => number) | null = null;

/** Attempt to load libc's getxattr via bun:ffi. Wrapped in try/catch: `dlopen("libc.so.6", ...)`
 * may simply not be loadable on some host (missing glibc, FFI disabled in this Bun build,
 * ...) — that's not a per-call error, it's "this backend doesn't exist here," so it's resolved
 * once and cached. */
function tryInitFfi(): boolean {
  try {
    const lib = dlopen("libc.so.6", {
      getxattr: {
        args: [FFIType.ptr, FFIType.ptr, FFIType.ptr, FFIType.u64],
        returns: FFIType.i64,
      },
    });
    ffiGetxattr = (pathBuf, nameBuf, valueBuf, size) => Number(lib.symbols.getxattr(ptr(pathBuf), ptr(nameBuf), ptr(valueBuf), BigInt(size)));
    return true;
  } catch {
    return false;
  }
}

const XATTR_VALUE_BYTES = 256;

function getLocationViaFfi(path: string): string | null {
  if (!ffiGetxattr) return null;
  try {
    const pathBuf = Buffer.from(path + "\0", "utf8");
    const nameBuf = Buffer.from("system.LOCATION\0", "utf8");
    const valueBuf = Buffer.alloc(XATTR_VALUE_BYTES);
    const n = ffiGetxattr(pathBuf, nameBuf, valueBuf, XATTR_VALUE_BYTES);
    if (n < 0) return null; // ENODATA, ENOTSUP, ENOENT, ... — no such attribute, not fatal
    const value = valueBuf.subarray(0, n).toString("utf8").trim();
    return value.length > 0 ? value : null;
  } catch {
    return null;
  }
}

function getLocationViaGetfattr(path: string): string | null {
  try {
    const res = Bun.spawnSync(["getfattr", "--absolute-names", "--only-values", "-n", "system.LOCATION", path], {
      stdout: "pipe",
      stderr: "ignore",
    });
    if (res.exitCode !== 0) return null;
    const value = res.stdout.toString("utf8").trim();
    return value.length > 0 ? value : null;
  } catch {
    return null;
  }
}

/**
 * Read the `system.LOCATION` xattr of `path` — the unRAID-assigned backing storage element
 * (`disk7`, `warm`, ...). Never throws: returns `null` on any error (no such attribute,
 * unsupported filesystem, missing `getfattr`, ...). The working backend (ffi vs the slower
 * `getfattr` spawn fallback) is discovered once and cached for the process lifetime — see
 * tryInitFfi().
 */
export function getLocationXattr(path: string): string | null {
  if (cachedBackend === null) {
    cachedBackend = tryInitFfi() ? "ffi" : "getfattr";
  }
  return cachedBackend === "ffi" ? getLocationViaFfi(path) : getLocationViaGetfattr(path);
}

/** Test-only: forget the cached backend/loaded symbol so a test can force re-discovery. */
export function _resetXattrBackendForTests(): void {
  cachedBackend = null;
  ffiGetxattr = null;
}

// ── unRAID resolver: share path -> backing path ──────────────────────────────────────────

const UNRAID_USER_ROOT = "/mnt/user";

/**
 * Build a resolver for an unRAID `shfs` share rooted at `/mnt/user/...`. Throws if `root`
 * isn't under `/mnt/user/` — this resolver's path math is meaningless anywhere else.
 * `xattrReader` defaults to `getLocationXattr` (real xattr lookups); tests inject a fake to
 * exercise the path math without depending on ffi or a real unRAID array.
 */
export function createUnraidResolver(root: string, xattrReader: (path: string) => string | null = getLocationXattr): BytePathResolver {
  const prefix = UNRAID_USER_ROOT + "/";
  if (!root.startsWith(prefix)) {
    throw new Error(`--byte-path unraid requires a root under ${prefix} (got ${root})`);
  }
  return {
    mode: "unraid",
    resolve(sharePath: string): { bytePath: string; element: string } | null {
      const element = xattrReader(sharePath);
      if (!element) return null;
      const rel = sharePath.slice(prefix.length);
      return { bytePath: join("/mnt", element, rel), element };
    },
  };
}

// ── hash-time plan: resolve + verify-by-lstat before anything trusts the backing path ───────

/** The share-side facts already known for a file (from the walk's own lstat) — the pin a
 * candidate backing path must match exactly before it's trusted. Structurally compatible with
 * walk.ts's FileEntry, so callers pass one directly. */
export interface HashPathTarget {
  abspath: string; // the share path
  size: bigint;
  mtimeNs: bigint;
}

export interface HashPathPlan {
  /** Where to read from first: the backing path if the pin verified, else the share path. */
  path: string;
  /** True iff `path` is the backing (direct) path, i.e. the pin matched. */
  direct: boolean;
}

/**
 * Resolve `target`'s backing path (if a resolver is given) and verify it before trusting it:
 * the backing path must lstat to the EXACT same `size` and `mtimeNs` the share-side walk
 * already recorded. A mismatch (or an lstat failure — e.g. the mover hasn't finished moving
 * the file, or already moved it elsewhere) means the pin didn't hold, so the plan falls back
 * to the share path. No resolver at all is the plain non-direct case.
 */
export async function planHashPath(resolver: BytePathResolver | undefined, target: HashPathTarget): Promise<HashPathPlan> {
  if (!resolver) return { path: target.abspath, direct: false };
  const resolved = resolver.resolve(target.abspath);
  if (!resolved) return { path: target.abspath, direct: false };
  try {
    const st = await lstat(resolved.bytePath, { bigint: true });
    if (st.size === target.size && st.mtimeNs === target.mtimeNs) {
      return { path: resolved.bytePath, direct: true };
    }
  } catch {
    /* backing path unreadable/gone right now — fall through to the share path */
  }
  return { path: target.abspath, direct: false };
}
