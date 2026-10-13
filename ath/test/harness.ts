// harness.ts — run the CLI in-process over a scratch directory, capturing both streams.
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { buildRegistry } from "../src/commands/index.ts";
import { type DispatchDeps, runCli } from "../src/kit/dispatch.ts";
import type { Registry } from "../src/kit/registry.ts";
import type { SessionIdentity } from "../src/kit/types.ts";
import { captureIo } from "../src/lib/io.ts";

export interface RunOpts {
  cwd?: string;
  env?: Record<string, string | undefined>;
  tty?: boolean;
  session?: SessionIdentity | null;
  confirm?: (prompt: string) => Promise<string | null>;
  registry?: Registry;
  history?: boolean;
}

export interface RunOut {
  code: number;
  stdout: string;
  stderr: string;
  json: () => unknown;
}

export async function ath(argv: string[], o: RunOpts = {}): Promise<RunOut> {
  const io = captureIo();
  const deps: DispatchDeps = {
    registry: o.registry ?? buildRegistry(),
    io,
    env: { HOME: process.env.HOME, USER: "tester", ATH_TEST: "1", ...(o.env ?? {}) },
    cwd: o.cwd ?? process.cwd(),
    tty: o.tty ?? false,
    session: () => o.session ?? null,
    confirm: o.confirm,
    history: o.history,
  };
  const code = await runCli(argv, deps);
  return { code, stdout: io.stdout, stderr: io.stderr, json: () => JSON.parse(io.stdout) };
}

/** A scratch directory removed at process exit. */
export function scratch(prefix = "ath-test-"): string {
  const d = mkdtempSync(join(tmpdir(), prefix));
  process.on("exit", () => rmSync(d, { recursive: true, force: true }));
  return d;
}
