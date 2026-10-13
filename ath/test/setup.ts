// setup.ts — bun test preload: mark the run, point HOME at a scratch directory so no test reads the real
// ~/.claude/sessions or writes anywhere real, and remove every scratch directory when the file is done.
import { afterAll } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { cleanupScratch } from "./harness.ts";

process.env.ATH_TEST = "1";
const scratchHome = mkdtempSync(join(tmpdir(), "ath-home-"));
process.env.HOME = scratchHome;
process.env.CLAUDE_CONFIG_DIR = join(scratchHome, ".claude");
delete process.env.ATHENAEUM_ROOT;
delete process.env.ATH_PROFILE;
delete process.env.ATH_ACTOR;
// bun test does not reliably run process exit hooks; afterAll in the preload runs after each test file
afterAll(cleanupScratch);
process.on("exit", () => {
  cleanupScratch();
  rmSync(scratchHome, { recursive: true, force: true });
});
