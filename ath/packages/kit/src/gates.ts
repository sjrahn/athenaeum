// gates.ts — the fixed gate order: tier against the caller's profile, then the actor. Out of scope looks unknown to
// agent and reader; the owner gets the real refusal.
import { AthError } from "./errors.ts";
import { BUILTIN_PROFILES, tierRank } from "./profiles.ts";
import type { Caller, CommandDef } from "./types.ts";

/** A refusal shown as an unknown command; `reason` goes to history only. */
export class HiddenError extends AthError {
  constructor(
    shown: string,
    readonly reason: string,
  ) {
    super("USAGE", shown);
  }
}

export const unknownCommand = (words: string) => `unknown command '${words}' (ath help lists them)`;

/** Whether `def` is listed for `caller` at all. */
export function visible(def: CommandDef, caller: Caller): boolean {
  return tierRank(def.meta.tier) <= tierRank(BUILTIN_PROFILES[caller.profile].tier);
}

export function checkGates(def: CommandDef, caller: Caller): AthError | null {
  const key = def.contract.key;
  const words = key.replaceAll("-", " ");
  if (!visible(def, caller)) {
    const reason = `${key} is ${def.meta.tier}-tier; profile ${caller.profile} runs up to ${BUILTIN_PROFILES[caller.profile].tier}`;
    return caller.profile === "owner" ? new AthError("DENIED", reason) : new HiddenError(unknownCommand(words), reason);
  }
  if (def.meta.mutating && !caller.actor) return new AthError("DENIED", `${key} writes; a non-terminal caller needs ATH_ACTOR`);
  return null;
}
