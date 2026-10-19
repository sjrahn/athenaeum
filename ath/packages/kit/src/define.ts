// define.ts — defineCommand: declaration-time checks on a command's meta.
import type { AnyContract } from "@ath/contracts";
import { AthError } from "./errors.ts";
import { type CommandDef, LOCK_SCOPES, TIERS } from "./types.ts";

const KEBAB = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/;

export function defineCommand<C extends AnyContract>(def: CommandDef<C>): CommandDef<C> {
  const key = def.contract.key;
  const bad = (m: string): never => {
    throw new AthError("INTERNAL", `command ${key}: ${m}`);
  };
  const m = def.meta;
  if (!TIERS.includes(m.tier)) bad(`tier must be one of ${TIERS.join(", ")}`);
  if (m.tier === "read" && m.mutating) bad("a read command cannot be mutating");
  if (!m.summary.trim() || /[\r\n]/.test(m.summary)) bad("summary must be one non-empty line");
  for (const s of m.locks ?? []) if (!LOCK_SCOPES.includes(s)) bad(`unknown lock scope '${s}'`);
  for (const a of m.aliases ?? []) if (!KEBAB.test(a)) bad(`alias '${a}' must be kebab-case`);
  return def;
}
