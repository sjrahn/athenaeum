// index.ts — the kit's public API.

export { type CallerInput, resolveCaller } from "./caller.ts";
export { makeClock } from "./clock.ts";
export { defineCommand } from "./define.ts";
export { type DispatchDeps, type Globals, parseGlobals, runCli } from "./dispatch.ts";
export { errEnvelope, okEnvelope, toAthError } from "./envelope.ts";
export { AthError, isAthError } from "./errors.ts";
export { collectSink, createEventBus, levelFor, textSink } from "./events.ts";
export { checkGates, HiddenError, unknownCommand, visible } from "./gates.ts";
export { appendHistory, historyPath, readHistory } from "./history.ts";
export { claudeSession, type IdentityDeps, parsePsTable, processIdentityDeps, procPpid, walkAncestors } from "./identity.ts";
export { acquireLocks, type Held } from "./locks.ts";
export { BUILTIN_PROFILES, narrowerProfile, parseProfile, tierRank } from "./profiles.ts";
export { createRegistry, type Registry } from "./registry.ts";
export { CONFIG_FILE, findRoot, stateDir } from "./root.ts";
export * from "./types.ts";
export { ATH_VERSION } from "./version.ts";
