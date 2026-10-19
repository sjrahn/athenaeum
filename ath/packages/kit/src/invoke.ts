// invoke.ts — a verb invoked with an args object rather than argv: the surface the HTTP server (§16) and the host
// daemon's socket (§18.9.2) share with the terminal. The same registry, gates, locks, journal and history; the same
// envelope `--json` prints. The caller is handed in, never taken from the process: over a wire it is an `agent` at
// most, may only narrow, and an admin verb — confirmed at a terminal — is refused, as are keys a contract lacks.
import { ContractUsageError, parseArgs } from "@ath/contracts";
import { clockAt, makeClock, wallClock } from "./clock.ts";
import { execute, recordHistory } from "./dispatch.ts";
import { errEnvelope, okEnvelope, toAthError } from "./envelope.ts";
import { AthError } from "./errors.ts";
import { collectSink, createEventBus } from "./events.ts";
import { checkGates, visible } from "./gates.ts";
import type { Io } from "./io.ts";
import type { Registry } from "./registry.ts";
import { instanceId } from "./root.ts";
import type { Caller, Envelope, KitCtx } from "./types.ts";
import { hostPaths, instanceState } from "./xdg.ts";

export interface InvokeOpts {
  registry: Registry;
  /** The verb's key (`pass-sign`) or its words joined by spaces. */
  verb: string;
  args: unknown;
  caller: Caller;
  root: string | null;
  env: Record<string, string | undefined>;
  cwd: string;
  wall?: () => Date;
  history?: boolean;
  /** For messages: how the verb was reached. */
  via: string;
}

const nullIo: Io = { out: () => {}, err: () => {} };

export async function invoke(o: InvokeOpts): Promise<{ envelope: Envelope; exit: number }> {
  const started = performance.now();
  const key = o.verb.trim().replace(/\s+/g, "-");
  const fail = (e: unknown, cmd = key) => {
    const err = toAthError(e);
    return { envelope: errEnvelope(cmd, err, performance.now() - started), exit: err.exit };
  };
  const r = o.registry.resolve([key]);
  if (!r || r.consumed !== 1 || !visible(r.def, o.caller)) return fail(new AthError("USAGE", `unknown verb '${o.verb}'`));
  const def = r.def;
  const cmd = def.contract.key;
  if (def.meta.tier === "admin")
    return fail(new AthError("DENIED", `${cmd} is the owner's, confirmed at a terminal; it is not run ${o.via}`), cmd);
  const gate = checkGates(def, o.caller);
  if (gate) return fail(gate, cmd);
  let args: unknown;
  try {
    args = parseArgs(def.contract, o.args ?? {});
  } catch (e) {
    return fail(e instanceof ContractUsageError ? new AthError("USAGE", e.message) : e, cmd);
  }
  const host = hostPaths(o.env);
  const id = o.root ? instanceId(o.root) : null;
  const instance = id ? { id, state: instanceState(host, id) } : null;
  const events = createEventBus(makeClock());
  events.subscribe(collectSink());
  const ctx: KitCtx = {
    io: nullIo,
    clock: makeClock(),
    wall: o.wall ? clockAt(o.wall) : wallClock(),
    host,
    instance,
    env: o.env,
    caller: o.caller,
    events,
    root: o.root,
    cwd: o.cwd,
    json: true,
    prog: `ath ${cmd.replaceAll("-", " ")}`,
  };
  try {
    const result = await execute(def, args, ctx);
    const exit = result.exitCode ?? 0;
    if (instance && o.history !== false) recordHistory(instance.state, cmd, [JSON.stringify(o.args ?? {})], o.caller, exit, started);
    return { envelope: okEnvelope(cmd, result.data, performance.now() - started, exit), exit };
  } catch (e) {
    const out = fail(e, cmd);
    if (instance && o.history !== false)
      recordHistory(instance.state, cmd, [JSON.stringify(o.args ?? {})], o.caller, out.exit, started, toAthError(e).code);
    return out;
  }
}

/** The HTTP status an envelope answers with (§19.4.2): 200 for ok, a verdict included. */
export function httpStatus(e: Envelope): number {
  if (e.ok) return 200;
  switch (e.error.code) {
    case "USAGE":
      return 400;
    case "DENIED":
      return 403;
    case "NOT_FOUND":
      return 404;
    case "CONFLICT":
      return 409;
    case "BUSY":
      return 423;
    case "EXTERNAL":
      return 502;
    case "UNAVAILABLE":
      return 503;
    default:
      return 500;
  }
}
