// index.ts — the kit's public API: the dispatcher and what every verb shares (callers, gates, envelopes, locks,
// history, the journal, host paths, canonical lines, hashes, atomic writes).

export { type CallerInput, resolveCaller } from "./caller.ts";
export * from "./canonical.ts";
export { clockAt, isoSecond, makeClock, wallClock } from "./clock.ts";
export { defineCommand } from "./define.ts";
export { type DispatchDeps, type Forward, type Globals, parseGlobals, runCli } from "./dispatch.ts";
export { parseDuration } from "./duration.ts";
export { errEnvelope, okEnvelope, toAthError } from "./envelope.ts";
export { AthError, isAthError } from "./errors.ts";
export { collectSink, createEventBus, levelFor, textSink } from "./events.ts";
export { ensureDir, fsyncDir, writeAtomic, writeTemp } from "./fs.ts";
export { checkGates, HiddenError, unknownCommand, visible } from "./gates.ts";
export { blake3File, blake3Hex, blake3Stream, isBlake3, sha256Hex, short } from "./hash.ts";
export { appendHistory, historyPath, readHistory } from "./history.ts";
export { claudeSession, type IdentityDeps, parsePsTable, processIdentityDeps, procPpid, walkAncestors } from "./identity.ts";
export { captureIo, type Io, processIo } from "./io.ts";
export { commitJournal, type JournalWrite, journalPending, recoverJournal } from "./journal.ts";
export { acquireLocks, type Held } from "./locks.ts";
export { BUILTIN_PROFILES, narrowerProfile, parseProfile, tierRank } from "./profiles.ts";
export { createRegistry, type Registry } from "./registry.ts";
export { CONFIG_FILE, findRoot, instanceId, UUID } from "./root.ts";
export { probeBinaries, runLocal } from "./spawn.ts";
export * from "./types.ts";
export { ATH_VERSION } from "./version.ts";
export { type HostPaths, hostPaths, instanceState } from "./xdg.ts";
