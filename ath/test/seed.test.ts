// seed.test.ts — the regression instance pair, built by testdata/seed.ts through the tool's own verbs, is the same on
// every run: every file of `reference` and `household` hashes as the reviewed golden in test/fixtures/seed.jsonl says
// (regenerate with ATH_UPDATE_GOLDEN=1 and review the diff). The pair loads, checks with nothing blocking, and shows
// the stages: a formed procedure, a read listing and plan, a transcribed photograph, structured exports, an unread clip.
import { describe, expect, test } from "bun:test";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";
import { blake3Hex } from "@ath/kit/hash.ts";
import { seed } from "../../testdata/seed.ts";
import { ath, scratch } from "./harness.ts";

const GOLDEN = join(import.meta.dir, "fixtures", "seed.jsonl");

function files(dir: string): string[] {
  const out: string[] = [];
  for (const n of readdirSync(dir, { withFileTypes: true })) {
    if (n.name === ".git") continue;
    const p = join(dir, n.name);
    if (n.isDirectory()) out.push(...files(p));
    else out.push(p);
  }
  return out;
}

describe("seed", () => {
  test("the pair is built by the tool and hashes as the golden says; it loads and checks clean", async () => {
    const out = join(scratch(), "pair");
    const { reference, household, host } = await seed(out);
    const lines: string[] = [];
    for (const f of [...files(reference), ...files(household)].map((p) => relative(out, p)).sort())
      lines.push(JSON.stringify({ path: f, blake3: await blake3Hex(new Uint8Array(readFileSync(join(out, f)))) }));
    const got = `${lines.join("\n")}\n`;
    if (process.env.ATH_UPDATE_GOLDEN === "1") writeFileSync(GOLDEN, got);
    expect(got).toBe(readFileSync(GOLDEN, "utf8"));
    const env = {
      ATH_ACTOR: "reader-a",
      HOME: host,
      XDG_DATA_HOME: join(host, "data"),
      XDG_STATE_HOME: join(host, "state"),
      XDG_CONFIG_HOME: join(host, "config"),
      XDG_CACHE_HOME: join(host, "cache"),
    };
    const run = (argv: string[]) => ath(["--json", ...argv], { env, cwd: household });
    expect((await run(["instance", "check"])).code).toBe(0);
    const checked = (await run(["check", "--all"])).json() as { data: { findings: { level: string }[] } };
    expect(checked.data.findings.filter((f) => f.level === "block")).toEqual([]);
    const held = (await run(["holdings"])).json() as { data: { records: { stage: string | null; mime: string }[] } };
    expect(held.data.records.map((r) => `${r.stage ?? "structured"} ${r.mime}`).sort()).toEqual([
      "formed application/pdf",
      "read application/pdf",
      "read text/html",
      "structured application/json",
      "structured application/zip",
      "transcribed image/jpeg",
      "unread video/quicktime",
    ]);
  });
});
