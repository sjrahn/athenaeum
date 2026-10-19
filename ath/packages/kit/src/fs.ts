// fs.ts — every write is atomic (spec §19.3.1): written under a temporary name in the target's directory, fsynced,
// renamed into place, and the directory fsynced so the rename survives a crash.
import { closeSync, fsyncSync, mkdirSync, openSync, renameSync, rmSync, writeSync } from "node:fs";
import { basename, dirname, join } from "node:path";

let seq = 0;
/** A temporary name beside `path`, unique to this process. */
export const tempBeside = (path: string): string => join(dirname(path), `.${basename(path)}.${process.pid}.${Date.now()}.${seq++}.tmp`);

export function fsyncDir(dir: string): void {
  let fd: number | null = null;
  try {
    fd = openSync(dir, "r");
    fsyncSync(fd);
  } catch {
    // some filesystems refuse a directory fsync; the rename is still atomic
  } finally {
    if (fd !== null) closeSync(fd);
  }
}

/** Write `data` to a temporary name beside `path` and fsync it; returns the temporary path. */
export function writeTemp(path: string, data: string | Uint8Array, mode = 0o644): string {
  mkdirSync(dirname(path), { recursive: true });
  const tmp = tempBeside(path);
  const fd = openSync(tmp, "w", mode);
  try {
    writeSync(fd, typeof data === "string" ? Buffer.from(data) : data);
    fsyncSync(fd);
  } catch (e) {
    closeSync(fd);
    rmSync(tmp, { force: true });
    throw e;
  }
  closeSync(fd);
  return tmp;
}

export function writeAtomic(path: string, data: string | Uint8Array, mode = 0o644): void {
  const tmp = writeTemp(path, data, mode);
  renameSync(tmp, path);
  fsyncDir(dirname(path));
}

export const ensureDir = (p: string) => mkdirSync(p, { recursive: true });
