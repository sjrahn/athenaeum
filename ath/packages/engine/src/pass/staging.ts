// staging.ts — an open pass (spec §13.2): staged in the instance's host state, outside the repository, under its
// subject and id; it records the author, the vocabulary pin it reads against, and the BLAKE3 of the record or entity
// file it was opened against, so signing against a file that has changed since is refused. What a record pass
// stages: readings by address (and the addresses it retires), a tree, chrome rules, a shape, what it attests, a note.
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { AthError } from "@ath/kit/errors.ts";
import { writeAtomic } from "@ath/kit/fs.ts";
import type { Reading, Scope } from "../record/document.ts";

type J = Record<string, unknown>;

export interface StagedPass {
  subject: string;
  kind: "record" | "entity";
  id: string;
  by: string;
  vocab: string;
  opened: string;
  /** The BLAKE3 of the file the pass was opened against, or null when there was none. */
  against: string | null;
  readings?: Record<string, Reading>;
  retire?: string[];
  scopes?: Scope[];
  chrome?: J[];
  shape?: string;
  attests?: ("readings" | "structure")[];
  note?: string;
  /** An entity pass's claim lines (§14). */
  lines?: J[];
}

export const stagingDir = (state: string, subject: string) => join(state, "passes", subject);
const file = (state: string, subject: string, id: string) => join(stagingDir(state, subject), `${id}.json`);

export function readStaged(state: string, subject: string, id: string): StagedPass {
  const p = file(state, subject, id);
  if (!existsSync(p)) throw new AthError("NOT_FOUND", `no open pass ${id} on ${subject}`);
  return JSON.parse(readFileSync(p, "utf8")) as StagedPass;
}

export function writeStaged(state: string, s: StagedPass): void {
  mkdirSync(stagingDir(state, s.subject), { recursive: true });
  writeAtomic(file(state, s.subject, s.id), `${JSON.stringify(s, null, 2)}\n`);
}

export const dropStaged = (state: string, subject: string, id: string) => rmSync(file(state, subject, id), { force: true });

/** Every open pass on a subject, by id. */
export function openPasses(state: string, subject: string): string[] {
  const d = stagingDir(state, subject);
  return existsSync(d)
    ? readdirSync(d)
        .filter((n) => /^p[1-9]\d*\.json$/.test(n))
        .map((n) => n.slice(0, -5))
    : [];
}

/** The next pass id (§13.1.2): one more than the highest on the subject, signed or open, in this instance. */
export function nextId(signed: Iterable<string>, open: Iterable<string>): string {
  let n = 0;
  for (const id of [...signed, ...open]) n = Math.max(n, Number(id.slice(1)) || 0);
  return `p${n + 1}`;
}
