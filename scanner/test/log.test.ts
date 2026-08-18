// Logger.progress()'s non-TTY heartbeat: off a TTY (this test process's stderr — bun test
// runs non-interactively), a carriage-return rewrite is meaningless, so progress() instead
// emits plain, newline-terminated, rate-limited lines. quiet suppresses everything.

import { test, expect } from "bun:test";
import { Logger } from "../src/log.ts";

/** Capture what a callback writes to process.stderr, then restore it — used instead of a
 * TTY-only mock since this test process's stderr.isTTY is already falsy (bun test's own
 * stderr is piped), which is exactly the condition under test. */
function captureStderr(fn: () => void): string[] {
  const orig = process.stderr.write;
  const chunks: string[] = [];
  process.stderr.write = ((chunk: unknown) => {
    chunks.push(String(chunk));
    return true;
  }) as typeof process.stderr.write;
  try {
    fn();
  } finally {
    process.stderr.write = orig;
  }
  return chunks;
}

test("precondition: this test process's stderr is not a TTY", () => {
  expect(process.stderr.isTTY).toBeFalsy();
});

test("non-TTY progress() emits a plain newline-terminated line, then rate-limits further calls", async () => {
  const log = new Logger("normal", { progressMinIntervalMs: 50 });

  const first = captureStderr(() => log.progress("hash: 1/10 files"));
  expect(first).toEqual(["hash: 1/10 files\n"]); // plain line, no \r\x1b[2K rewrite

  const immediateRepeat = captureStderr(() => log.progress("hash: 2/10 files"));
  expect(immediateRepeat).toEqual([]); // rate-limited: arrived well under progressMinIntervalMs later

  await new Promise((r) => setTimeout(r, 60));
  const afterInterval = captureStderr(() => log.progress("hash: 3/10 files"));
  expect(afterInterval).toEqual(["hash: 3/10 files\n"]); // interval elapsed: allowed through
});

test("non-TTY endProgress() is a no-op (lines already end in \\n)", () => {
  const log = new Logger("normal", { progressMinIntervalMs: 1 });
  const chunks = captureStderr(() => log.endProgress());
  expect(chunks).toEqual([]);
});

test("quiet suppresses progress() entirely, on or off a TTY", () => {
  const log = new Logger("quiet", { progressMinIntervalMs: 1 });
  const chunks = captureStderr(() => {
    log.progress("hash: 1/10 files");
    log.progress("hash: 2/10 files");
  });
  expect(chunks).toEqual([]);
});

test("the progressMinIntervalMs default is 1 second when unset", async () => {
  const log = new Logger("normal"); // no options — default 1000ms
  const first = captureStderr(() => log.progress("a"));
  expect(first.length).toBe(1);
  const soon = captureStderr(() => log.progress("b"));
  expect(soon).toEqual([]); // well under 1000ms later
});
