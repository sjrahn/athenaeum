// spawn.ts — running a local binary (git, rclone, ffprobe) and finding it on PATH. Nothing here ever opens a socket.
import { AthError } from "./errors.ts";

/** Where each binary resolves on PATH, or null. */
export function probeBinaries(names: readonly string[]): Record<string, string | null> {
  const out: Record<string, string | null> = {};
  for (const n of names) out[n] = Bun.which(n);
  return out;
}

export interface RunResult {
  code: number;
  stdout: Uint8Array;
  stderr: string;
}

/** Run a local binary to completion. A missing binary is EXTERNAL (71), so is a non-zero exit unless `allowFail`. */
export function runLocal(argv: readonly string[], o: { stdin?: Uint8Array; allowFail?: boolean; cwd?: string } = {}): RunResult {
  const bin = argv[0]!;
  if (!Bun.which(bin)) throw new AthError("EXTERNAL", `${bin} is not on PATH`);
  const r = Bun.spawnSync([...argv], {
    stdin: o.stdin ? new Blob([o.stdin as unknown as ArrayBuffer]) : undefined,
    stdout: "pipe",
    stderr: "pipe",
    cwd: o.cwd,
  });
  const res: RunResult = { code: r.exitCode, stdout: new Uint8Array(r.stdout), stderr: r.stderr.toString() };
  if (r.exitCode !== 0 && !o.allowFail)
    throw new AthError("EXTERNAL", `${bin} exited ${r.exitCode}: ${res.stderr.trim().split("\n").slice(-3).join(" | ")}`);
  return res;
}
