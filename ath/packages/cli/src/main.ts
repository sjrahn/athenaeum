#!/usr/bin/env bun
// main.ts — the `ath` entry point: builds the registry and wires the real environment (stdin tty, process tree,
// terminal confirm) into the kit's dispatcher. Everything testable lives below this file.
import { createInterface } from "node:readline";
import { runCli } from "@ath/kit/dispatch.ts";
import { claudeSession, processIdentityDeps } from "@ath/kit/identity.ts";
import { processIo } from "@ath/kit/io.ts";
import { createRegistry, type Registry } from "@ath/kit/registry.ts";
import { registerVerbs } from "@ath/verbs";

export function buildRegistry(): Registry {
  const r = createRegistry();
  registerVerbs(r);
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
  const code = await runCli(Bun.argv.slice(2), {
    registry: buildRegistry(),
    io: processIo,
    env: process.env,
    cwd: process.cwd(),
    tty,
    session: () => claudeSession(processIdentityDeps(process.env)),
    confirm: tty ? confirm : undefined,
  });
  process.exitCode = code;
}
