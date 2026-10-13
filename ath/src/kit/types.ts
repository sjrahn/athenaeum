// types.ts — the kit's shared shapes: commands, tiers and profiles, callers, errors, envelopes, events, locks, history.
// Interfaces only; each module implements its part. The model is the ita CLI's (architecture, not code).
import type { AnyContract, ArgsOf, DataOf } from "../../contracts/index.ts";
import type { Io } from "../lib/io.ts";

// ── tiers, profiles and callers ─────────────────────────────────────────────────────────

/** A command's danger class, lowest first: `read` changes nothing; `write` is what an agent may do alone (ingest,
 * passes, harvest, sort); `admin` changes the owner's own record (the owner file) and needs the owner at a terminal. */
export type Tier = "read" | "write" | "admin";
export const TIERS: readonly Tier[] = ["read", "write", "admin"];

/** The built-in profiles, widest first; each is a subset of the one before it. */
export type ProfileName = "owner" | "agent" | "reader";
export const PROFILES: readonly ProfileName[] = ["owner", "agent", "reader"];

export interface Profile {
  name: ProfileName;
  /** The highest tier it runs. */
  tier: Tier;
}

/** The nearest Claude Code session among this process's ancestors, found from the process tree and the session
 * files (`<config>/sessions/<pid>.json`), never from the environment alone. */
export interface SessionIdentity {
  id: string;
  pid: number;
  name: string | null;
}

/** human: a terminal with no Claude ancestry; session: a Claude session; script: no terminal, no Claude. */
export type CallerKind = "human" | "session" | "script";

export interface Caller {
  profile: ProfileName;
  kind: CallerKind;
  session: SessionIdentity | null;
  /** How the profile was chosen, one line per step (`ath whoami`). */
  basis: string[];
  /** `ATH_ACTOR`, else `$USER` at a terminal; null when neither. */
  actor: string | null;
  /** stdin is a terminal (injected, never probed below the dispatcher). */
  tty: boolean;
}

// ── errors ──────────────────────────────────────────────────────────────────────────────

/** The closed error-code list and the sysexits each maps to. Verdicts (lint errors, verify failures) are not errors:
 * they are ok-envelopes with an exitCode of 1. */
export const ERROR_CODES = {
  FAILED: 1, // a verdict: the command ran and its answer is no
  USAGE: 64, // EX_USAGE
  NOT_FOUND: 66, // EX_NOINPUT: a subject, file or layer that does not exist
  INTERNAL: 70, // EX_SOFTWARE: an unexpected throw
  EXTERNAL: 71, // EX_OSERR: a tool outside ath failed (tesseract)
  CONFLICT: 73, // EX_CANTCREAT: a write refused by the contract (identity, shadowing, undeclared field)
  BUSY: 75, // EX_TEMPFAIL: a lock is held
  DENIED: 77, // EX_NOPERM: the caller's profile may not run this
  CONFIG: 78, // EX_CONFIG: athenaeum.yaml, the ontology or the chain is broken
} as const;
export type ErrorCode = keyof typeof ERROR_CODES;

// ── envelope ────────────────────────────────────────────────────────────────────────────

export type Envelope<D = unknown> =
  | { ok: true; cmd: string; version: string; elapsed_ms: number; data: D; exit_code?: number }
  | { ok: false; cmd: string; version: string; elapsed_ms: number; error: { code: ErrorCode; message: string; data?: unknown } };

// ── events ──────────────────────────────────────────────────────────────────────────────

export type EventLevel = "debug" | "info" | "warn" | "error";

export interface KitEvent {
  /** Dotted name, e.g. `ingest.file`, `lint.finding`. */
  kind: string;
  level: EventLevel;
  msg: string;
  data?: Record<string, unknown>;
  ts?: string;
}

export type EventSink = (e: KitEvent) => void;

export interface EventBus {
  emit(e: KitEvent): void;
  subscribe(sink: EventSink): () => void;
}

// ── commands ────────────────────────────────────────────────────────────────────────────

export type LockScope = "corpus" | "ledger" | "ontology";
export const LOCK_SCOPES: readonly LockScope[] = ["corpus", "ledger", "ontology"];

export interface CommandMeta {
  /** One line for `ath help`. */
  summary: string;
  tier: Tier;
  /** Whether it writes anything; a mutating call from a non-terminal caller needs ATH_ACTOR. */
  mutating: boolean;
  locks?: LockScope[];
  examples?: string[];
  aliases?: string[];
  /** Longer help body printed under the usage line. */
  help?: string;
}

export interface Clock {
  now(): Date;
  /** The injected instant, or the wall clock; provenance dates use this. */
  iso(): string;
}

export interface KitCtx {
  io: Io;
  clock: Clock;
  env: Record<string, string | undefined>;
  caller: Caller;
  events: EventBus;
  /** The top layer's root when one was found (`--root`, $ATHENAEUM_ROOT, or a walk up for athenaeum.yaml). */
  root: string | null;
  /** The working directory the command was invoked from. */
  cwd: string;
  /** `--json` was passed: the command's text renderer is skipped. */
  json: boolean;
  /** Ask at the terminal; null at end of input. Absent for non-terminal callers. */
  confirm?: (prompt: string) => Promise<string | null>;
  /** `ath <words>`, for messages. */
  prog: string;
}

export interface RunResult<D> {
  data: D;
  /** A verdict: the command ran, the answer is no (lint found errors). Reported as ok with exit_code. */
  exitCode?: number;
}

export interface CommandDef<C extends AnyContract = AnyContract> {
  meta: CommandMeta;
  contract: C;
  run(ctx: KitCtx, args: ArgsOf<C>): RunResult<DataOf<C>> | Promise<RunResult<DataOf<C>>>;
  /** Render data as text (the default output); absent → JSON is printed in text mode too. */
  text?(data: DataOf<C>, io: Io, ctx: KitCtx): void;
}

// ── history ─────────────────────────────────────────────────────────────────────────────

export interface HistoryLine {
  v: 1;
  ts: string;
  cmd: string;
  argv: string[];
  profile: ProfileName;
  actor: string | null;
  exit: number;
  elapsed_ms: number;
  error?: ErrorCode;
}
