// fs.ts — atomic file writes (tmp + rename in the same directory) and small path helpers.
import { closeSync, fsyncSync, mkdirSync, openSync, renameSync, writeSync } from "node:fs";
import { dirname, join } from "node:path";

export function writeAtomic(path: string, data: string | Uint8Array): void {
  mkdirSync(dirname(path), { recursive: true });
  const tmp = join(dirname(path), `.${process.pid}.${Date.now()}.tmp`);
  const fd = openSync(tmp, "w", 0o644);
  try {
    writeSync(fd, data as Uint8Array);
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
  renameSync(tmp, path);
}

export const ensureDir = (p: string) => mkdirSync(p, { recursive: true });
