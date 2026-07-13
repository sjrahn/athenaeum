// Logging + human formatting. Progress and diagnostics go to stderr; the final summary
// block (or --json) goes to stdout, so the two never interleave for a consumer piping one.

export type LogLevel = "quiet" | "normal" | "verbose";

export class Logger {
  constructor(private readonly level: LogLevel = "normal") {}

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

  /** Rewrites the current stderr line (progress ticker); no-op when not a TTY or quiet. */
  progress(msg: string): void {
    if (this.level === "quiet") return;
    if (process.stderr.isTTY) {
      process.stderr.write("\r\x1b[2K" + msg);
    }
  }

  /** Ends a progress line so the next info() starts clean. */
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
