#!/usr/bin/env bun
// main.ts — the `ath` entry point: builds the registry and wires the real environment (stdin tty, process tree,
// terminal confirm, the host daemon's socket) into the kit's dispatcher. Everything testable lives below this file.
import { createInterface } from "node:readline";
import { type DaemonDeps, daemonPaths, forwarder, registerDaemon } from "@ath/daemon";
import { runCli } from "@ath/kit/dispatch.ts";
import { claudeSession, processIdentityDeps } from "@ath/kit/identity.ts";
import { processIo } from "@ath/kit/io.ts";
import { createRegistry, type Registry } from "@ath/kit/registry.ts";
import { hostPaths } from "@ath/kit/xdg.ts";
import { registerVerbs } from "@ath/verbs";

export function buildRegistry(daemon: DaemonDeps = {}): Registry {
  const r = createRegistry();
  registerVerbs(r);
  registerDaemon(r, daemon);
  return r;
}

function confirm(prompt: string): Promise<string | null> {
  const rl = createInterface({ input: process.stdin, output: process.stderr, terminal: true });
  return new Promise((resolve) => {
    rl.question(prompt, (a) => {
      rl.close();
      resolve(a);
    });
    rl.on("close", () => resolve(null));
  });
}

if (import.meta.main) {
  const tty = process.stdin.isTTY === true;
  const athd = daemonPaths(hostPaths(process.env));
  const code = await runCli(Bun.argv.slice(2), {
    registry: buildRegistry(),
    io: processIo,
    env: process.env,
    cwd: process.cwd(),
    tty,
    session: () => claudeSession(processIdentityDeps(process.env)),
    confirm: tty ? confirm : undefined,
    forward: forwarder(athd.socket, athd.pid),
  });
  process.exitCode = code;
}
