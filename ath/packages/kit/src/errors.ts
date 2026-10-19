// errors.ts — the kit's one error type: a closed code (types.ts ERROR_CODES) that maps to a sysexits exit, a message,
// and optional structured data for the envelope.
import { ERROR_CODES, type ErrorCode } from "./types.ts";

export class AthError extends Error {
  /** The failure came back from the host daemon, which recorded it in the history itself. */
  relayed?: boolean;

  constructor(
    readonly code: ErrorCode,
    message: string,
    readonly data?: unknown,
  ) {
    super(message);
  }

  /** The process exit this error ends with. */
  get exit(): number {
    return ERROR_CODES[this.code];
  }
}

/** Whether `e` is an AthError (by shape, so duplicate module copies still match). */
export function isAthError(e: unknown): e is AthError {
  return e instanceof AthError || (e instanceof Error && typeof (e as AthError).code === "string" && (e as AthError).code in ERROR_CODES);
}
