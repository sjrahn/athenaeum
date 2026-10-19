// journal.ts — a verb that writes several files (a rename, a merge, a repin, a reshard) journals them first (spec
// §19.3.1): every new content is written to a temporary file beside its target, then the plan — each target with its
// temporary file, or a removal — is written atomically into the instance's host state as the commit point, then the
// renames and removals run, then the plan goes. An interrupted verb is completed from its plan, or, when it stopped
// before the plan was written, undone by removing its temporary files; either happens before any verb runs again.
import { existsSync, readdirSync, readFileSync, renameSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fsyncDir, writeAtomic, writeTemp } from "./fs.ts";

export interface JournalWrite {
  /** The file to write, or to remove when `content` is null. */
  path: string;
  content: string | Uint8Array | null;
}

interface Step {
  path: string;
  tmp: string | null;
}

const PLAN = "journal.json";
const PENDING = "journal.pending";

/** Write every file of `writes` so that no reader sees some written and others not, across a crash. */
export function commitJournal(state: string, writes: readonly JournalWrite[]): void {
  const pendingDir = join(state, PENDING);
  const steps: Step[] = [];
  // record the temporary names before writing them, so an interruption here is undone
  writeAtomic(join(pendingDir, "names.json"), "[]");
  for (const w of writes) {
    const tmp = w.content === null ? null : writeTemp(w.path, w.content);
    steps.push({ path: w.path, tmp });
    writeAtomic(join(pendingDir, "names.json"), JSON.stringify(steps));
  }
  writeAtomic(join(state, PLAN), JSON.stringify(steps));
  rmSync(pendingDir, { recursive: true, force: true });
  apply(state, steps);
}

function apply(state: string, steps: readonly Step[]): void {
  const dirs = new Set<string>();
  for (const s of steps) {
    if (s.tmp === null) rmSync(s.path, { force: true });
    else if (existsSync(s.tmp)) renameSync(s.tmp, s.path);
    dirs.add(dirname(s.path));
  }
  for (const d of dirs) fsyncDir(d);
  rmSync(join(state, PLAN), { force: true });
}

/** Complete or undo an interrupted journal; returns what it did, or null when there was nothing to do. */
export function recoverJournal(state: string): "completed" | "undone" | null {
  const plan = join(state, PLAN);
  if (existsSync(plan)) {
    apply(state, JSON.parse(readFileSync(plan, "utf8")) as Step[]);
    rmSync(join(state, PENDING), { recursive: true, force: true });
    return "completed";
  }
  const pendingDir = join(state, PENDING);
  if (!existsSync(pendingDir)) return null;
  try {
    for (const s of JSON.parse(readFileSync(join(pendingDir, "names.json"), "utf8")) as Step[]) if (s.tmp) rmSync(s.tmp, { force: true });
  } catch {
    // an unreadable list: the temporary files are dot-files beside their targets and harm nothing
  }
  rmSync(pendingDir, { recursive: true, force: true });
  return "undone";
}

/** Whether a journal is pending (for checks). */
export const journalPending = (state: string): boolean =>
  existsSync(join(state, PLAN)) || (existsSync(state) && readdirSync(state).includes(PENDING));
