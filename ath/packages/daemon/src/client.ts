// client.ts — one request to the host daemon over its socket (§18.9.2): `POST /v1/<verb>` with the arguments and the
// instance root as one JSON object; the caller's actor, its narrowed profile and its working directory ride as headers.
// The answer is the envelope. Two callers: the `daemon` verbs, for which a daemon that is not running is `unavailable`
// (69), and the dispatcher handing over a verb that writes the host index, for which it means "run it here" — unless
// the daemon's process is alive and its socket does not answer, which fails closed as `busy` rather than write beside it.
import { existsSync, readFileSync } from "node:fs";
import { AthError } from "@ath/kit/errors.ts";
import type { Caller, Envelope } from "@ath/kit/types.ts";

/** `fetch` with Bun's `unix` option; injected so tests can stand one in. */
export type SocketFetch = (url: string, init: RequestInit & { unix: string }) => Promise<Response>;
const realFetch: SocketFetch = (url, init) => fetch(url, init);

export interface Request {
  socket: string;
  verb: string;
  /** The verb's arguments, `root` among them. */
  body: Record<string, unknown>;
  caller?: Pick<Caller, "actor" | "profile">;
  cwd?: string;
  /** Give up after this long; absent, wait for the verb however long it runs. */
  timeoutMs?: number;
  fetch?: SocketFetch;
}

export class NoDaemon extends Error {}

/** The daemon's envelope, or NoDaemon when nothing answers on the socket. */
export async function request(r: Request): Promise<Envelope> {
  if (!existsSync(r.socket)) throw new NoDaemon(`no daemon socket at ${r.socket}`);
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (r.caller?.actor) headers["ath-actor"] = r.caller.actor;
  if (r.caller?.profile) headers["ath-profile"] = r.caller.profile;
  if (r.cwd) headers["ath-cwd"] = r.cwd;
  let res: Response;
  try {
    res = await (r.fetch ?? realFetch)(`http://athd/v1/${r.verb}`, {
      unix: r.socket,
      method: "POST",
      headers,
      body: JSON.stringify(r.body),
      ...(r.timeoutMs ? { signal: AbortSignal.timeout(r.timeoutMs) } : {}),
    });
  } catch (e) {
    throw new NoDaemon(`the daemon does not answer on ${r.socket}: ${(e as Error).message}`);
  }
  try {
    return (await res.json()) as Envelope;
  } catch {
    throw new AthError("EXTERNAL", `the daemon answered ${res.status} without an envelope`);
  }
}

/** Whether the pid a pid file names is a live process. */
export function pidAlive(pidFile: string): number | null {
  let pid = 0;
  try {
    const t = readFileSync(pidFile, "utf8");
    pid = /^\s*\d+\s*$/.test(t) ? Number(t) : 0;
  } catch {
    return null;
  }
  if (pid <= 1) return null;
  try {
    process.kill(pid, 0);
    return pid;
  } catch (e) {
    return (e as NodeJS.ErrnoException).code === "EPERM" ? pid : null;
  }
}

/** The envelope's data, or its error thrown; a daemon not running is `unavailable`. For the `daemon` verbs. */
export async function ask<D>(r: Request): Promise<{ data: D; exitCode?: number; relayed: true }> {
  let env: Envelope;
  try {
    env = await request({ timeoutMs: 10_000, ...r });
  } catch (e) {
    if (e instanceof NoDaemon) throw new AthError("UNAVAILABLE", `the host daemon is not running (${e.message})`);
    throw e;
  }
  if (!env.ok) throw new AthError(env.error.code, env.error.message, env.error.data);
  return { data: env.data as D, relayed: true, ...(env.exit_code ? { exitCode: env.exit_code } : {}) };
}

/** The dispatcher's hand-over (kit `Forward`): the daemon's envelope, or null when no daemon runs. */
export function forwarder(socket: string, pidFile: string, fetchImpl?: SocketFetch) {
  return async (o: { verb: string; args: unknown; root: string | null; cwd: string; caller: Caller }): Promise<Envelope | null> => {
    try {
      return await request({
        socket,
        verb: o.verb,
        body: { ...(o.args as Record<string, unknown>), ...(o.root ? { root: o.root } : {}) },
        caller: o.caller,
        cwd: o.cwd,
        ...(fetchImpl ? { fetch: fetchImpl } : {}),
      });
    } catch (e) {
      if (!(e instanceof NoDaemon)) throw e;
      const pid = pidAlive(pidFile);
      if (pid !== null && existsSync(socket))
        throw new AthError(
          "BUSY",
          `the host daemon (pid ${pid}) is running but its socket does not answer; it writes the index, so nothing is written here`,
        );
      return null;
    }
  };
}
