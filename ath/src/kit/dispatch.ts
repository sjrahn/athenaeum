// dispatch.ts — runCli: global flags, command resolution, then caller → gates → args → locks → run → output → history.
// Never calls process.exit; returns the exit code.
import { type AnyContract, ContractUsageError, contractJsonSchema, parseArgv, usageText } from "../../contracts/index.ts";
import type { Io } from "../lib/io.ts";
import { resolveCaller } from "./caller.ts";
import { makeClock } from "./clock.ts";
import { errEnvelope, okEnvelope, toAthError } from "./envelope.ts";
import { AthError } from "./errors.ts";
import { collectSink, createEventBus, levelFor, textSink } from "./events.ts";
import { checkGates, HiddenError, visible } from "./gates.ts";
import { appendHistory } from "./history.ts";
import { acquireLocks } from "./locks.ts";
import type { Registry } from "./registry.ts";
import { findRoot } from "./root.ts";
import type { Caller, CommandDef, HistoryLine, KitCtx, SessionIdentity } from "./types.ts";
import { ATH_VERSION } from "./version.ts";

export interface DispatchDeps {
  registry: Registry;
  io: Io;
  env: Record<string, string | undefined>;
  cwd: string;
  /** stdin is a terminal. */
  tty: boolean;
  /** The nearest Claude session among the ancestors; absent = none. */
  session?: () => SessionIdentity | null;
  /** Ask at the terminal; absent = admin commands are refused. */
  confirm?: (prompt: string) => Promise<string | null>;
  /** History is appended when a root is known; tests may turn it off. */
  history?: boolean;
  prog?: string;
}

export interface Globals {
  json: boolean;
  verbose: number;
  quiet: boolean;
  root?: string;
  profile?: string;
  now?: string;
  words: string[];
}

const GLOBAL_USAGE = `usage: ath [--json] [-v|-q] [--root PATH] [--profile P] [--now ISO] <words…> [args] [flags]
       ath help [words…] | ath <words…> --help | ath <words…> --schema

global flags (before the command's words):
  --json      print the envelope {ok, cmd, version, elapsed_ms, data | error} instead of text
  -v / -q     more / fewer progress lines on stderr
  --root      the instance root (default: $ATHENAEUM_ROOT, else the nearest athenaeum.yaml above the cwd)
  --profile   narrow the caller's profile (owner · agent · reader); never widens
  --now       fix the clock (ISO-8601) for reproducible provenance dates

exit codes: 0 ok · 1 a verdict (lint errors, verify failures) · 64 usage · 66 not found · 70 internal ·
71 an external tool failed · 73 a write the contract refuses · 75 busy · 77 denied · 78 config
`;

export function parseGlobals(argv: readonly string[]): Globals {
  const g: Globals = { json: false, verbose: 0, quiet: false, words: [] };
  let i = 0;
  for (; i < argv.length; i++) {
    const t = argv[i]!;
    if (t === "--json") g.json = true;
    else if (t === "-v") g.verbose++;
    else if (t === "-q") g.quiet = true;
    else {
      const m = /^--(root|profile|now)(?:=(.*))?$/.exec(t);
      if (!m) break;
      let v = m[2];
      if (v === undefined) {
        v = argv[++i];
        if (v === undefined) throw new AthError("USAGE", `--${m[1]}: expected one argument`);
      }
      if (m[1] === "root") g.root = v;
      else if (m[1] === "profile") g.profile = v;
      else g.now = v;
    }
  }
  g.words = argv.slice(i);
  return g;
}

function helpText(registry: Registry, caller: Caller, prog: string, words: string[]): string | null {
  const listed = registry.list().filter((d) => visible(d, caller));
  if (words.length === 0) {
    const groups = registry.groups().filter((g) => listed.some((d) => registry.groupOf(d.contract.key) === g.name));
    const w = Math.max(0, ...groups.map((g) => g.name.length));
    const lines = groups.map((g) => `  ${g.name.padEnd(w)}  ${g.summary}`);
    return `${GLOBAL_USAGE}\ngroups (${prog} help <group> for its commands):\n${lines.join("\n")}\n`;
  }
  const r = registry.resolve(words);
  if (r && r.consumed === words.length && visible(r.def, caller)) return commandHelp(prog, r.def);
  const group = words[0]!;
  const inGroup = listed.filter((d) => registry.groupOf(d.contract.key) === group);
  if (!inGroup.length) return null;
  const w = Math.max(...inGroup.map((d) => d.contract.key.length));
  const lines = inGroup.map((d) => `  ${d.contract.key.replaceAll("-", " ").padEnd(w)}  ${d.meta.summary}`);
  return `${group}:\n${lines.join("\n")}\n`;
}

function commandHelp(prog: string, def: CommandDef): string {
  let s = usageText(prog, def.contract, def.meta.summary);
  if (def.meta.help) s += `\n${def.meta.help.trim()}\n`;
  if (def.meta.examples?.length) s += `\nexamples:\n${def.meta.examples.map((e) => `  ${e}`).join("\n")}\n`;
  s += `\ntier: ${def.meta.tier}${def.meta.mutating ? " · writes" : ""}${def.meta.locks?.length ? ` · locks ${def.meta.locks.join(", ")}` : ""}\n`;
  return s;
}

/** Run one invocation; returns the exit code. */
export async function runCli(argv: readonly string[], deps: DispatchDeps): Promise<number> {
  const io = deps.io;
  const prog = deps.prog ?? "ath";
  const started = performance.now();
  let g: Globals;
  try {
    g = parseGlobals(argv);
  } catch (e) {
    const err = toAthError(e);
    io.err(`${prog}: ${err.message}\n`);
    return err.exit;
  }
  const json = g.json;
  const fail = (cmd: string, e: unknown, caller?: Caller, root?: string | null, words?: string[]): number => {
    const err = toAthError(e);
    if (json) io.out(`${JSON.stringify(errEnvelope(cmd, err, performance.now() - started))}\n`);
    else {
      io.err(`${prog}: ${err.message}\n`);
      if (err.code === "USAGE") io.err(`(${prog} help for usage)\n`);
    }
    if (caller && root && deps.history !== false) record(root, cmd, words ?? [], caller, err.exit, started, err.code, e);
    return err.exit;
  };

  let clock: ReturnType<typeof makeClock>;
  try {
    clock = makeClock(g.now);
  } catch (e) {
    return fail("", new AthError("USAGE", (e as Error).message));
  }
  const session = deps.session ? deps.session() : null;
  let caller: Caller;
  try {
    caller = resolveCaller({ env: deps.env, tty: deps.tty, session, profileFlag: g.profile });
  } catch (e) {
    return fail("", e);
  }
  const root = findRoot(deps.cwd, deps.env, g.root);

  const words = g.words;
  if (words.length === 0) {
    io.err(helpText(deps.registry, caller, prog, []) ?? GLOBAL_USAGE);
    return 64;
  }
  if (words[0] === "help") {
    const h = helpText(deps.registry, caller, prog, words.slice(1));
    if (h === null) return fail("help", new AthError("USAGE", `unknown command '${words.slice(1).join(" ")}' (${prog} help lists them)`));
    io.out(h);
    return 0;
  }

  const resolved = deps.registry.resolve(words);
  if (!resolved || !visible(resolved.def, caller)) {
    const shown = words.join(" ");
    return fail(shown, new AthError("USAGE", `unknown command '${shown}' (${prog} help lists them)`));
  }
  const { def, consumed } = resolved;
  const rest = words.slice(consumed);
  const cmd = def.contract.key;
  if (rest[0] === "--help" || rest[0] === "-h") {
    io.out(commandHelp(prog, def));
    return 0;
  }
  if (rest[0] === "--schema") {
    io.out(`${JSON.stringify(contractJsonSchema(def.contract), null, 2)}\n`);
    return 0;
  }

  const gate = checkGates(def, caller);
  if (gate) {
    if (gate instanceof HiddenError && root && deps.history !== false)
      record(root, cmd, rest, caller, gate.exit, started, "DENIED", gate.reason);
    return fail(cmd, gate, gate instanceof HiddenError ? undefined : caller, root, rest);
  }

  let args: unknown;
  try {
    args = parseArgv(def.contract as AnyContract, rest);
  } catch (e) {
    if (!(e instanceof ContractUsageError)) return fail(cmd, e, caller, root, rest);
    if (!json) io.err(`${prog} ${cmd.replaceAll("-", " ")}: ${e.message}\n${usageText(prog, def.contract)}`);
    else io.out(`${JSON.stringify(errEnvelope(cmd, new AthError("USAGE", e.message), performance.now() - started))}\n`);
    return 64;
  }

  if (def.meta.tier === "admin") {
    if (json)
      return fail(
        cmd,
        new AthError("DENIED", `${cmd} is admin-tier and confirms at a terminal; it does not run under --json`),
        caller,
        root,
        rest,
      );
    if (!deps.confirm || !caller.tty)
      return fail(cmd, new AthError("DENIED", `${cmd} is admin-tier: the owner confirms it at a terminal`), caller, root, rest);
    io.err(`${cmd.replaceAll("-", " ")} changes the owner's record. Type the command's name to confirm: `);
    const typed = await deps.confirm("");
    if (typed === null || (typed.trim() !== cmd.replaceAll("-", " ") && typed.trim() !== cmd)) {
      return fail(cmd, new AthError("DENIED", `${cmd}: not confirmed`), caller, root, rest);
    }
  }

  const events = createEventBus(clock);
  const sink = json ? collectSink() : textSink(io, levelFor(g.verbose, g.quiet));
  events.subscribe(sink);
  const ctx: KitCtx = {
    io,
    clock,
    env: deps.env,
    caller,
    events,
    root,
    cwd: deps.cwd,
    json,
    confirm: deps.confirm,
    prog: `${prog} ${cmd.replaceAll("-", " ")}`,
  };

  let held: { release(): void } | null = null;
  try {
    if (def.meta.locks?.length) {
      if (!root)
        throw new AthError("CONFIG", `${cmd} needs an instance root (--root, $ATHENAEUM_ROOT, or an athenaeum.yaml above the cwd)`);
      held = acquireLocks(root, def.meta.locks, clock.now());
    }
    const result = await def.run(ctx, args as never);
    const exit = result.exitCode ?? 0;
    if (json) io.out(`${JSON.stringify(okEnvelope(cmd, result.data, performance.now() - started, exit))}\n`);
    else if (def.text) def.text(result.data as never, io, ctx);
    else io.out(`${JSON.stringify(result.data, null, 2)}\n`);
    if (root && deps.history !== false) record(root, cmd, rest, caller, exit, started);
    return exit;
  } catch (e) {
    return fail(cmd, e, caller, root, rest);
  } finally {
    held?.release();
  }
}

function record(
  root: string,
  cmd: string,
  argv: string[],
  caller: Caller,
  exit: number,
  started: number,
  error?: HistoryLine["error"],
  detail?: unknown,
): void {
  const line: HistoryLine = {
    v: 1,
    ts: new Date().toISOString(),
    cmd,
    argv,
    profile: caller.profile,
    actor: caller.actor,
    exit,
    elapsed_ms: Math.round(performance.now() - started),
  };
  if (error) line.error = error;
  if (typeof detail === "string" && error === "DENIED") (line as HistoryLine & { reason?: string }).reason = detail;
  try {
    appendHistory(root, line);
  } catch {
    // history never fails a command
  }
}

export { ATH_VERSION };
