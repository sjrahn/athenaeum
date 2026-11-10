// The status file (`--status-file <path>`): one JSON object describing the run in progress,
// rewritten whole (temp, then rename) at most every couple of seconds and at every change of
// phase, so a status page or a poller can read it without waking the disks the scan reads.
// Put it on a RAM filesystem (`/var/log` on unRAID). Every field is present from the first write
// (README.md, "Status file"); `phase` is one of walk · hash · scrub · publish · done · refused · failed.
import { renameSync, writeFileSync } from "node:fs";
import { hostname } from "node:os";

export type Phase = "walk" | "hash" | "scrub" | "publish" | "done" | "refused" | "failed";

export class StatusFile {
  private last = 0;
  private state: Record<string, unknown>;

  constructor(
    private readonly path: string | undefined,
    base: Record<string, unknown>,
    private readonly minIntervalMs = 2000,
  ) {
    // every field is there from the first write, so a reader sees one shape throughout
    this.state = {
      ...base,
      phase: "walk",
      mode: null,
      generation: null,
      dryRun: false,
      pid: process.pid,
      host: hostname(),
      started_at: new Date().toISOString(),
      filesSeen: 0,
      toHash: 0,
      bytesToHash: "0",
      hashed: 0,
      bytesHashed: "0",
      published: false,
      summary: null,
      error: null,
    };
  }

  update(fields: Record<string, unknown>, force = false): void {
    this.state = { ...this.state, ...fields };
    if (!this.path) return;
    const now = performance.now();
    if (!force && now - this.last < this.minIntervalMs) return;
    this.last = now;
    const tmp = `${this.path}.tmp`;
    try {
      writeFileSync(tmp, `${JSON.stringify({ ...this.state, updated_at: new Date().toISOString() })}\n`);
      renameSync(tmp, this.path);
    } catch {
      // a status file never fails a scan
    }
  }

  phase(phase: Phase, fields: Record<string, unknown> = {}): void {
    this.update({ ...fields, phase }, true);
  }
}
