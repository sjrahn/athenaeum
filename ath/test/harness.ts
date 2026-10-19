// harness.ts — run the CLI in-process over a scratch directory, capturing both streams.
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { buildRegistry } from "@ath/cli/main.ts";
import { type DispatchDeps, runCli } from "@ath/kit/dispatch.ts";
import { captureIo } from "@ath/kit/io.ts";
import type { Registry } from "@ath/kit/registry.ts";
import type { SessionIdentity } from "@ath/kit/types.ts";

export interface RunOpts {
  cwd?: string;
  env?: Record<string, string | undefined>;
  tty?: boolean;
  session?: SessionIdentity | null;
  confirm?: (prompt: string) => Promise<string | null>;
  registry?: Registry;
  history?: boolean;
  /** The wall clock; absent, a fixed instant so output compares byte for byte. */
  wall?: () => Date;
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
    env: {
      HOME: process.env.HOME,
      XDG_DATA_HOME: process.env.XDG_DATA_HOME,
      XDG_STATE_HOME: process.env.XDG_STATE_HOME,
      XDG_CONFIG_HOME: process.env.XDG_CONFIG_HOME,
      XDG_RUNTIME_DIR: process.env.XDG_RUNTIME_DIR,
      USER: "tester",
      ATH_TEST: "1",
      ...(o.env ?? {}),
    },
    cwd: o.cwd ?? process.cwd(),
    tty: o.tty ?? false,
    session: () => o.session ?? null,
    confirm: o.confirm,
    history: o.history,
    wall: o.wall ?? (() => new Date("2026-03-20T09:00:00Z")),
  };
  const code = await runCli(argv, deps);
  return { code, stdout: io.stdout, stderr: io.stderr, json: () => JSON.parse(io.stdout) };
}

/** Every scratch directory made in this process; `cleanupScratch` removes them (setup.ts runs it after all tests). */
export const scratchDirs: string[] = [];

/** A scratch directory removed when the test run ends. */
export function scratch(prefix = "ath-test-"): string {
  const d = mkdtempSync(join(tmpdir(), prefix));
  scratchDirs.push(d);
  return d;
}

export function cleanupScratch(): void {
  for (const d of scratchDirs.splice(0)) rmSync(d, { recursive: true, force: true });
}

/** The repository's testdata/ (the regression library). */
export const TESTDATA = join(import.meta.dir, "..", "..", "testdata");
