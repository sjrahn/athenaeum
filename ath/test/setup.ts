// setup.ts — bun test preload: mark the run, point HOME and every XDG base at a scratch directory so no test reads
// the real ~/.claude/sessions or host state or writes anywhere real, and remove every scratch directory when the file is done.
import { afterAll } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { cleanupScratch } from "./harness.ts";

process.env.ATH_TEST = "1";
const scratchHome = mkdtempSync(join(tmpdir(), "ath-home-"));
process.env.HOME = scratchHome;
process.env.CLAUDE_CONFIG_DIR = join(scratchHome, ".claude");
for (const [k, d] of [
  ["XDG_DATA_HOME", ".local/share"],
  ["XDG_STATE_HOME", ".local/state"],
  ["XDG_CONFIG_HOME", ".config"],
  ["XDG_RUNTIME_DIR", "run"],
  ["XDG_CACHE_HOME", ".cache"],
] as const)
  process.env[k] = join(scratchHome, d);
delete process.env.ATHENAEUM_ROOT;
delete process.env.ATH_PROFILE;
delete process.env.ATH_ACTOR;
// bun test does not reliably run process exit hooks; afterAll in the preload runs after each test file
afterAll(cleanupScratch);
process.on("exit", () => {
  cleanupScratch();
  rmSync(scratchHome, { recursive: true, force: true });
});
