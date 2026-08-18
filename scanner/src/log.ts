// Logging + human formatting. Progress and diagnostics go to stderr; the final summary
// block (or --json) goes to stdout, so the two never interleave for a consumer piping one.

export type LogLevel = "quiet" | "normal" | "verbose";

export interface LoggerOptions {
  /** non-TTY only: minimum time between two emitted progress lines (default 1000ms). Callers
   * (the scanner's hash-phase heartbeat) decide WHEN it's worth attempting a line — every N
   * hashed files, or a stall-floor timer — this is the final defensive clamp against those
   * attempts arriving faster than is useful for a log, e.g. a burst of tiny files. */
  progressMinIntervalMs?: number;
}

export class Logger {
  private readonly progressMinIntervalMs: number;
  private lastNonTtyProgressAt = -Infinity;

  constructor(
    private readonly level: LogLevel = "normal",
    opts: LoggerOptions = {},
  ) {
    this.progressMinIntervalMs = opts.progressMinIntervalMs ?? 1000;
  }

  info(msg: string): void {
    if (this.level !== "quiet") process.stderr.write(msg + "\n");
  }

  debug(msg: string): void {
    if (this.level === "verbose") process.stderr.write(msg + "\n");
  }

  warn(msg: string): void {
    process.stderr.write("warn: " + msg + "\n");
  }

  error(msg: string): void {
    process.stderr.write("error: " + msg + "\n");
  }

  /**
   * Report progress. On a TTY, rewrites the current stderr line (unchanged behavior — called
   * as often as the caller likes, e.g. once a second). Off a TTY (piped to a file, over plain
   * ssh, a cron log) a carriage-return rewrite is meaningless and would otherwise leave a
   * multi-day run's log silent between "walk done" and the final summary — so instead this
   * emits a plain, newline-terminated line, rate-limited to `progressMinIntervalMs` apart.
   * No-op when quiet.
   */
  progress(msg: string): void {
    if (this.level === "quiet") return;
    if (process.stderr.isTTY) {
      process.stderr.write("\r\x1b[2K" + msg);
      return;
    }
    const now = performance.now();
    if (now - this.lastNonTtyProgressAt < this.progressMinIntervalMs) return;
    this.lastNonTtyProgressAt = now;
    process.stderr.write(msg + "\n");
  }

  /** Ends a progress line so the next info() starts clean. No-op off a TTY — non-TTY
   * progress() lines already end in "\n", so there's nothing to close out. */
  endProgress(): void {
    if (this.level !== "quiet" && process.stderr.isTTY) process.stderr.write("\n");
  }
}

const UNITS = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"] as const;

export function humanBytes(n: bigint | number): string {
  let v = typeof n === "bigint" ? Number(n) : n;
  let u = 0;
  while (v >= 1024 && u < UNITS.length - 1) {
    v /= 1024;
    u++;
  }
  return `${v.toFixed(u === 0 ? 0 : 2)} ${UNITS[u]}`;
}

export function humanRate(bytes: bigint | number, ms: number): string {
  if (ms <= 0) return "—";
  const bytesPerSec = (typeof bytes === "bigint" ? Number(bytes) : bytes) / (ms / 1000);
  return `${humanBytes(bytesPerSec)}/s`;
}

export function humanDuration(ms: number): string {
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (x: number) => x.toString().padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`;
}

export function humanCount(n: number): string {
  return n.toLocaleString("en-US");
}
