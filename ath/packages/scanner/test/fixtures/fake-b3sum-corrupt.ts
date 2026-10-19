#!/usr/bin/env bun
// Test fixture: passes --version but always reports a WRONG (fixed) digest for any input —
// used to prove discoverNativeHasher refuses a binary that fails its startup verification
// and falls back to WASM, rather than trusting a broken/misidentified binary.

const args = process.argv.slice(2);

if (args.includes("--version")) {
  console.log("fake-b3sum 1.0.0 (ath-scan test fixture, corrupt)");
  process.exit(0);
}

const noNames = args.includes("--no-names");
const files = args.filter((a) => !a.startsWith("--"));
const WRONG_DIGEST = "0".repeat(64);
for (const f of files) {
  process.stdout.write(noNames ? WRONG_DIGEST + "\n" : `${WRONG_DIGEST}  ${f}\n`);
}
