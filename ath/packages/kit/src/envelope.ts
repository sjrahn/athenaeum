// envelope.ts — the --json envelope shapes and the error normaliser.
import { ContractUsageError } from "@ath/contracts";
import { AthError, isAthError } from "./errors.ts";
import type { Envelope } from "./types.ts";
import { ATH_VERSION } from "./version.ts";

export function okEnvelope<D>(cmd: string, data: D, elapsedMs: number, exitCode?: number): Envelope<D> {
  const e: Envelope<D> = { ok: true, cmd, version: ATH_VERSION, elapsed_ms: Math.round(elapsedMs), data };
  if (exitCode !== undefined && exitCode !== 0) e.exit_code = exitCode;
  return e;
}

export function errEnvelope(cmd: string, err: AthError, elapsedMs: number): Extract<Envelope, { ok: false }> {
  const error: { code: AthError["code"]; message: string; data?: unknown } = { code: err.code, message: err.message };
  if (err.data !== undefined) error.data = err.data;
  return { ok: false, cmd, version: ATH_VERSION, elapsed_ms: Math.round(elapsedMs), error };
}

/** ContractUsageError → USAGE; AthError passes through; anything else → INTERNAL. */
export function toAthError(e: unknown): AthError {
  if (isAthError(e)) return e as AthError;
  if (e instanceof ContractUsageError) return new AthError("USAGE", e.message);
  return new AthError("INTERNAL", e instanceof Error ? (e.stack ?? e.message) : String(e));
}
