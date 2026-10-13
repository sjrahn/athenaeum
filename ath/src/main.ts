#!/usr/bin/env bun
// main.ts — the `ath` entry point: wires the real environment (stdin tty, process tree, terminal confirm) into the
// kit's dispatcher and sets the exit code. Everything testable lives below this file.
import { createInterface } from "node:readline";
import { buildRegistry } from "./commands/index.ts";
import { runCli } from "./kit/dispatch.ts";
import { claudeSession, processIdentityDeps } from "./kit/identity.ts";
import { processIo } from "./lib/io.ts";

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
