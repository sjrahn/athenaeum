// identity.ts — who is above us in the process tree: the nearest Claude Code session, found from `/proc` ancestry and
// the session files under `$CLAUDE_CONFIG_DIR` (else `~/.claude`), never from the environment alone (which a shell
// can empty). macOS falls back to one `ps` table. Any hit means Claude ancestry.
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { SessionIdentity } from "./types.ts";

/** Parent pid of `pid` from /proc, or null. */
export function procPpid(pid: number): number | null {
  try {
    const stat = readFileSync(`/proc/${pid}/stat`, "utf8");
    const close = stat.lastIndexOf(")");
    const fields = stat.slice(close + 2).split(" ");
    const ppid = Number(fields[1]);
    return Number.isFinite(ppid) ? ppid : null;
  } catch {
    return null;
  }
}

/** `pid → ppid` from one `ps -axo pid=,ppid=` run (macOS and the test double). */
export function parsePsTable(text: string): Map<number, number> {
  const m = new Map<number, number>();
  for (const line of text.split("\n")) {
    const t = line.trim().split(/\s+/);
    if (t.length >= 2) m.set(Number(t[0]), Number(t[1]));
  }
  return m;
}

export interface IdentityDeps {
  pid: number;
  ppid: (pid: number) => number | null;
  sessionsDir: string;
  exists: (p: string) => boolean;
  read: (p: string) => string;
}

export function processIdentityDeps(env: Record<string, string | undefined>): IdentityDeps {
  const config = env.CLAUDE_CONFIG_DIR ?? join(env.HOME ?? "", ".claude");
  let table: Map<number, number> | null = null;
  const ppid = (pid: number): number | null => {
    if (process.platform === "linux") return procPpid(pid);
    if (!table) {
      try {
        table = parsePsTable(Bun.spawnSync(["ps", "-axo", "pid=,ppid="]).stdout.toString());
      } catch {
        table = new Map();
      }
    }
    return table.get(pid) ?? null;
  };
  return { pid: process.pid, ppid, sessionsDir: join(config, "sessions"), exists: existsSync, read: (p) => readFileSync(p, "utf8") };
}

/** Every ancestor pid, nearest first, up to init. */
export function walkAncestors(d: IdentityDeps): number[] {
  const out: number[] = [];
  const seen = new Set<number>();
  let p: number | null = d.pid;
  while (p !== null && p > 1 && !seen.has(p) && out.length < 256) {
    seen.add(p);
    out.push(p);
    p = d.ppid(p);
  }
  return out;
}

/** The nearest ancestor (self included) that has a session file, or null. */
export function claudeSession(d: IdentityDeps): SessionIdentity | null {
  for (const pid of walkAncestors(d)) {
    const file = join(d.sessionsDir, `${pid}.json`);
    if (!d.exists(file)) continue;
    let id = "";
    let name: string | null = null;
    try {
      const j = JSON.parse(d.read(file)) as { sessionId?: unknown; name?: unknown };
      if (typeof j.sessionId === "string") id = j.sessionId;
      if (typeof j.name === "string") name = j.name;
    } catch {
      // an unreadable session file is still a session
    }
    return { id, pid, name };
  }
  return null;
}
