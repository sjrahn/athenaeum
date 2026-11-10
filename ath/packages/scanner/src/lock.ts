// The run lock: one scan writes a manifest's state at a time. A full walk, a targeted run, a
// compaction and a publish each hold `<manifest dir>/scan.lock` while they run; a second one
// finds it held and stops (exit 4) without touching the state. A lock left by a process that is
// gone (same host, dead pid) is taken over. Readers never look at it.
import { closeSync, openSync, readFileSync, rmSync, writeSync } from "node:fs";
import { hostname } from "node:os";
import { join } from "node:path";

export const LOCK_FILENAME = "scan.lock";

export class ScanBusy extends Error {}

function alive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (e) {
    return (e as NodeJS.ErrnoException).code === "EPERM";
  }
}

/** Take the manifest dir's run lock; the returned function releases it. */
export function acquireScanLock(manifestDir: string): () => void {
  const path = join(manifestDir, LOCK_FILENAME);
  const body = JSON.stringify({ pid: process.pid, host: hostname(), started_at: new Date().toISOString() });
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const fd = openSync(path, "wx", 0o644);
      writeSync(fd, body);
      closeSync(fd);
      return () => rmSync(path, { force: true });
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code !== "EEXIST") throw e;
      let holder: { pid?: number; host?: string } = {};
      try {
        holder = JSON.parse(readFileSync(path, "utf8"));
      } catch {
        // a lock being written this instant, or a torn one: treat as held on the first look
      }
      const stale = attempt === 0 && holder.host === hostname() && typeof holder.pid === "number" && !alive(holder.pid);
      if (!stale) throw new ScanBusy(`${path}: another scan holds this manifest (pid ${holder.pid ?? "?"} on ${holder.host ?? "?"})`);
      rmSync(path, { force: true });
    }
  }
  throw new ScanBusy(`${path}: another scan holds this manifest`);
}
