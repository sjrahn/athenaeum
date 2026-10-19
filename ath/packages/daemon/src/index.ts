// index.ts — the host daemon (§18.9): its verbs, its server and the client the dispatcher hands index writes to.
export { ask, forwarder, NoDaemon, pidAlive, request, type SocketFetch } from "./client.ts";
export { type DaemonDeps, registerDaemon } from "./commands.ts";
export { type DaemonConfig, type DaemonPaths, daemonPaths, JOBS, type JobKind, loadDaemonConfig } from "./config.ts";
export { backoffMs, type JobState, nextAt, settle } from "./jobs.ts";
export { type DaemonHandle, type DaemonStatus, type StartOpts, startDaemon, type Timers } from "./server.ts";
export { athBin, renderUnit, UNIT_NAME, unitDir } from "./unit.ts";
