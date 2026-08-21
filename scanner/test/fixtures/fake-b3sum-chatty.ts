#!/usr/bin/env bun
// Test fixture: a b3sum that behaves correctly (real BLAKE3 digest on stdout, exit 0) but
// also writes well over a pipe's OS buffer size (~64KiB on Linux) to stderr before it exits —
// simulating a verbose/warning-per-file real-world b3sum. Used to prove `runB3sum` (hasher.ts)
// drains stderr concurrently with stdout/exited rather than only reading it after checking the
// exit code: a caller that doesn't will have this fixture block forever on the stderr write,
// deadlocking whatever awaited its exit.

import { blake3 } from "hash-wasm";

const args = process.argv.slice(2);

if (args.includes("--version")) {
  console.log("fake-b3sum 1.0.0 (ath-scan test fixture, chatty)");
  process.exit(0);
}

const noNames = args.includes("--no-names");
const files = args.filter((a) => !a.startsWith("--"));

// Well over any plausible pipe buffer (64KiB on Linux) so a child that blocks on a full pipe
// reproduces reliably rather than depending on exact OS buffering.
const CHATTER_LINE = "warning: simulated chatty b3sum stderr line for deadlock regression test\n";
const CHATTER_BYTES = 512 * 1024;
let written = 0;
while (written < CHATTER_BYTES) {
  process.stderr.write(CHATTER_LINE);
  written += CHATTER_LINE.length;
}

for (const f of files) {
  const buf = new Uint8Array(await Bun.file(f).arrayBuffer());
  const digest = await blake3(buf);
  process.stdout.write(noNames ? digest + "\n" : `${digest}  ${f}\n`);
}
