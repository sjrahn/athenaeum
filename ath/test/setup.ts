// setup.ts — bun test preload: mark the run, and point HOME at a scratch directory so no test reads the real
// ~/.claude/sessions or writes anywhere real.
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

process.env.ATH_TEST = "1";
const scratchHome = mkdtempSync(join(tmpdir(), "ath-home-"));
process.env.HOME = scratchHome;
process.env.CLAUDE_CONFIG_DIR = join(scratchHome, ".claude");
delete process.env.ATHENAEUM_ROOT;
delete process.env.ATH_PROFILE;
delete process.env.ATH_ACTOR;
process.on("exit", () => rmSync(scratchHome, { recursive: true, force: true }));
