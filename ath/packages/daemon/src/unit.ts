// unit.ts — the host's service unit for `athd`: a systemd user unit that runs `ath daemon run`, restarts it when it
// fails, re-reads its configuration on reload, and gives a running job time to finish when it stops. Its PATH is the
// installer's, so the tools custody spawns (rclone, git) resolve as they did at the terminal.
import { dirname, join } from "node:path";

export const UNIT_NAME = "athd.service";

/** The `ath` the unit runs: `$ATH_BIN`, else this compiled binary, else the workspace's `bin/ath`. */
export function athBin(env: Record<string, string | undefined>): string {
  if (env.ATH_BIN) return env.ATH_BIN;
  if (import.meta.dir.startsWith("/$bunfs")) return process.execPath;
  return join(import.meta.dir, "..", "..", "..", "bin", "ath");
}

/** Where the host's user units live: `$XDG_CONFIG_HOME/systemd/user`, beside the athenaeum configuration. */
export const unitDir = (hostConfig: string): string => join(dirname(hostConfig), "systemd", "user");

export function renderUnit(o: { bin: string; path: string }): string {
  return `[Unit]
Description=athd, the Athenaeum host daemon: one socket for every verb, and custody kept
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=PATH=${o.path}
Environment=ATH_ACTOR=athd
ExecStart=${o.bin} daemon run
ExecReload=/bin/kill -HUP $MAINPID
TimeoutStopSec=90
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
`;
}
