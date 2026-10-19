// io.ts — the output seam: commands write through an Io, so in-process tests can capture what a subprocess would print.

export interface Io {
  out(s: string): void;
  err(s: string): void;
}

// A closed pipe (`ath … | head`) ends that stream's output quietly instead of throwing EPIPE mid-command.
const piped = { stdout: false, stderr: false };
function write(name: "stdout" | "stderr", s: string): void {
  if (piped[name]) return;
  try {
    process[name].write(s);
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code !== "EPIPE") throw e;
    piped[name] = true;
  }
}

for (const name of ["stdout", "stderr"] as const) {
  process[name].on("error", (e: NodeJS.ErrnoException) => {
    if (e.code !== "EPIPE") throw e;
    piped[name] = true;
  });
}

export const processIo: Io = {
  out: (s) => write("stdout", s),
  err: (s) => write("stderr", s),
};

/** An Io that records both streams (for in-process tests). */
export function captureIo(): Io & { stdout: string; stderr: string } {
  const c = {
    stdout: "",
    stderr: "",
    out(s: string) {
      c.stdout += s;
    },
    err(s: string) {
      c.stderr += s;
    },
  };
  return c;
}
