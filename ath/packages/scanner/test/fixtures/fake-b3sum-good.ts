#!/usr/bin/env bun
// Test fixture: stands in for a real b3sum binary. Computes real BLAKE3 via hash-wasm (the
// same implementation ath-scan's own WASM path uses), so both discoverNativeHasher's startup
// verification and any digest-correctness assertion in a test hold for real content — not
// just "some string routing worked." Lives under test/fixtures/ (not a tmpdir) specifically
// so Bun's module resolution can find hash-wasm by walking up to the project's node_modules.
//
// Set ATH_SCAN_TEST_FAIL_BASENAME to make this fixture fail (nonzero exit) for any input
// file whose basename matches — used to test the per-file "b3sum-failed" skip path without
// breaking startup verification (which hashes a differently-named temp file).

import { blake3 } from "hash-wasm";
import { basename } from "node:path";
import { appendFileSync } from "node:fs";

const args = process.argv.slice(2);

if (args.includes("--version")) {
  console.log("fake-b3sum 1.0.0 (ath-scan test fixture)");
  process.exit(0);
}

const noNames = args.includes("--no-names");
const files = args.filter((a) => !a.startsWith("--"));
const failBasename = process.env.ATH_SCAN_TEST_FAIL_BASENAME;
const concurrencyLog = process.env.ATH_SCAN_TEST_CONCURRENCY_LOG;
const concurrencyDelayMs = Number(process.env.ATH_SCAN_TEST_CONCURRENCY_DELAY_MS ?? "0");

for (const f of files) {
  if (failBasename && basename(f) === failBasename) {
    process.stderr.write(`simulated b3sum failure for ${f}\n`);
    process.exit(1);
  }
  // appendFileSync (O_APPEND) is atomic for writes this small, unlike a read-modify-write —
  // needed since multiple fixture processes may genuinely run at the same time here.
  if (concurrencyLog) appendFileSync(concurrencyLog, `start ${Date.now()}\n`);
  if (concurrencyDelayMs > 0) await new Promise((r) => setTimeout(r, concurrencyDelayMs));
  const buf = new Uint8Array(await Bun.file(f).arrayBuffer());
  const digest = await blake3(buf);
  if (concurrencyLog) appendFileSync(concurrencyLog, `end ${Date.now()}\n`);
  process.stdout.write(noNames ? digest + "\n" : `${digest}  ${f}\n`);
}
