// kit.journal.test.ts — a multi-file write (§19.3.1): all files or none across an interruption, completed from the
// plan once it is written, undone before it is.
import { describe, expect, test } from "bun:test";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { writeTemp } from "@ath/kit/fs.ts";
import { commitJournal, journalPending, recoverJournal } from "@ath/kit/journal.ts";
import { scratch } from "./harness.ts";

describe("journal", () => {
  test("writes, replaces and removes several files at once, leaving nothing behind", () => {
    const repo = scratch();
    const state = scratch();
    writeFileSync(join(repo, "old.jsonl"), "old\n");
    writeFileSync(join(repo, "gone.jsonl"), "x\n");
    commitJournal(state, [
      { path: join(repo, "a", "new.jsonl"), content: "new\n" },
      { path: join(repo, "old.jsonl"), content: "replaced\n" },
      { path: join(repo, "gone.jsonl"), content: null },
    ]);
    expect(readFileSync(join(repo, "a", "new.jsonl"), "utf8")).toBe("new\n");
    expect(readFileSync(join(repo, "old.jsonl"), "utf8")).toBe("replaced\n");
    expect(existsSync(join(repo, "gone.jsonl"))).toBe(false);
    expect(readdirSync(repo).filter((n) => n.endsWith(".tmp"))).toEqual([]);
    expect(journalPending(state)).toBe(false);
    expect(recoverJournal(state)).toBeNull();
  });

  test("an interruption after the plan is completed; one before it is undone", () => {
    const repo = scratch();
    const state = scratch();
    writeFileSync(join(repo, "b.jsonl"), "before\n");
    const ta = writeTemp(join(repo, "a.jsonl"), "A\n");
    const tb = writeTemp(join(repo, "b.jsonl"), "B\n");
    writeFileSync(
      join(state, "journal.json"),
      JSON.stringify([
        { path: join(repo, "a.jsonl"), tmp: ta },
        { path: join(repo, "b.jsonl"), tmp: tb },
      ]),
    );
    expect(journalPending(state)).toBe(true);
    expect(recoverJournal(state)).toBe("completed");
    expect(readFileSync(join(repo, "a.jsonl"), "utf8")).toBe("A\n");
    expect(readFileSync(join(repo, "b.jsonl"), "utf8")).toBe("B\n");

    const tc = writeTemp(join(repo, "b.jsonl"), "C\n");
    mkdirSync(join(state, "journal.pending"));
    writeFileSync(join(state, "journal.pending", "names.json"), JSON.stringify([{ path: join(repo, "b.jsonl"), tmp: tc }]));
    expect(recoverJournal(state)).toBe("undone");
    expect(readFileSync(join(repo, "b.jsonl"), "utf8")).toBe("B\n");
    expect(existsSync(tc)).toBe(false);
  });
});
