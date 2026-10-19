// locks.ts — named locks (spec §19.3.2): `repository` in the instance's host state, `index` in the host's state.
// One file per lock, taken with O_EXCL, carrying the holder's pid and a deadline. A stale lock (a dead pid or past
// its deadline) is reclaimed; a live one is BUSY (75). Locks are taken in LOCK_SCOPES order so no two verbs deadlock.
import { closeSync, mkdirSync, openSync, readFileSync, rmSync, writeSync } from "node:fs";
import { join } from "node:path";
import { AthError } from "./errors.ts";
import { LOCK_SCOPES, type LockScope } from "./types.ts";

const TTL_MS = 10 * 60 * 1000;

function pidAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (e) {
    return (e as NodeJS.ErrnoException).code === "EPERM";
  }
}

export interface Held {
  release(): void;
}

/** Take `scopes`, each in the directory `dirOf` names for it. */
export function acquireLocks(dirOf: (s: LockScope) => string, scopes: readonly LockScope[], now: Date, pid = process.pid): Held {
  const taken: string[] = [];
  const release = () => {
    for (const p of taken.reverse()) rmSync(p, { force: true });
    taken.length = 0;
  };
  for (const scope of LOCK_SCOPES.filter((s) => scopes.includes(s))) {
    const dir = join(dirOf(scope), "locks");
    mkdirSync(dir, { recursive: true });
    const p = join(dir, `${scope}.lock`);
    const body = JSON.stringify({ pid, until: new Date(now.getTime() + TTL_MS).toISOString() });
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const fd = openSync(p, "wx", 0o600);
        writeSync(fd, body);
        closeSync(fd);
        taken.push(p);
        break;
      } catch (e) {
        if ((e as NodeJS.ErrnoException).code !== "EEXIST") {
          release();
          throw e;
        }
        let stale = true;
        try {
          const j = JSON.parse(readFileSync(p, "utf8")) as { pid?: number; until?: string };
          const live = typeof j.pid === "number" && pidAlive(j.pid);
          const expired = typeof j.until === "string" && new Date(j.until).getTime() < now.getTime();
          stale = !live || expired;
        } catch {
          stale = true;
        }
        if (!stale || attempt === 1) {
          release();
          throw new AthError("BUSY", `the ${scope} lock is held (${p}); try again`);
        }
        rmSync(p, { force: true });
      }
    }
  }
  return { release };
}
