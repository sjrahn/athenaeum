// resolve.test.ts — `resolve` and `propose` end to end (§19.5): a route through a container canonicalised to the asset
// (§7.5.2), the constituent route in custody with its trace (§18.8), a refused region (§7.4.3), the surface of a
// structured artifact, the bytes at an address, a PDF page rendered for a reader, the hints at an address.
import { describe, expect, test } from "bun:test";
import { copyFileSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { ath, scratch, TESTDATA } from "./harness.ts";

const SYN = join(TESTDATA, "synthetic");
const ZIP = "da7b858a7acc71ea1953f162369503c564bce9e6ec59ad1b717c6864ccaf34f0";
const CSV = "7ce98d2c8bf71eae6ce2ac944cca99c1a84e8bf5c4d64d2a653aab11f6780964";
const PLAN = "0c4efa1371eeacce3467e37e8af4cbabda275d74461cf25cb6dbf2dc68c24865";
const env = { ATH_ACTOR: "reader-a" };
type D = Record<string, unknown>;

async function instanceWithZip() {
  const root = join(scratch(), "household");
  expect((await ath(["instance", "init", root], { env })).code).toBe(0);
  const work = scratch();
  copyFileSync(join(SYN, "drive-folder.zip"), join(work, "drive-folder.zip"));
  expect((await ath(["--root", root, "ingest", "drive-folder.zip"], { env, cwd: work })).code).toBe(0);
  return root;
}

describe("resolve", () => {
  test("a route to an asset canonicalises to the asset; custody takes the constituent route and says so", async () => {
    const root = await instanceWithZip();
    const r = await ath(["--json", "resolve", `ath://da7b858a?path=Harbour plans/Berth list.csv&row=1&col=1`, "--trace"], {
      env,
      cwd: root,
    });
    expect(r.code, r.stdout).toBe(0);
    const d = (r.json() as { data: D }).data;
    expect(d).toMatchObject({
      anchor: `ath://${CSV}?row=1&col=1`,
      artifact: CSV,
      mime: "text/csv",
      class: "structured",
      surface: "Lantern",
    });
    expect((d.route as string[])[0]).toBe(`${CSV}  ← path=Harbour plans/Berth list.csv in ${ZIP}`);
    expect((d.route as string[])[1]).toContain(`${ZIP}  ← store local [local]`);
  });

  test("a region the artifact does not have is refused; the bytes at an address; a PDF page rendered as PNG", async () => {
    const root = await instanceWithZip();
    expect((await ath(["resolve", `ath://${PLAN}?page=9`], { env, cwd: root })).code).toBe(66);
    expect((await ath(["resolve", `ath://${CSV}?row=99`], { env, cwd: root })).code).toBe(66);
    expect((await ath(["resolve", `ath://${ZIP}?path=nowhere.txt`], { env, cwd: root })).code).toBe(66);
    const out = join(scratch(), "berths.csv");
    const csv = await ath(["--json", "resolve", `ath://${CSV}`, "--out", out], { env, cwd: root });
    expect(csv.code, csv.stdout).toBe(0);
    expect(readFileSync(out, "utf8").startsWith("Berth,Vessel,Length (m)")).toBe(true);
    const span = join(scratch(), "span.txt");
    expect((await ath(["resolve", `ath://${CSV}?path=x`, "--out", span], { env, cwd: root })).code).toBe(66);
    const png = join(scratch(), "page.png");
    const page = await ath(["--json", "resolve", `ath://${PLAN}?page=1&bbox=0,0,0.5,0.25`, "--out", png], { env, cwd: root });
    expect(page.code, page.stdout).toBe(0);
    const bytes = readFileSync(png);
    expect([...bytes.subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
    const view = new DataView(bytes.buffer, bytes.byteOffset);
    expect(view.getUint32(16)).toBeGreaterThan(100); // width at 2 px per point, half the page
  });
});

describe("propose", () => {
  test("the hints at an address of a rendered artifact; a structured one proposes nothing", async () => {
    const root = await instanceWithZip();
    // the plan is an asset with no record of its own: ingest it alone so it says what it is
    const work = scratch();
    const r = await ath(["--json", "resolve", `ath://${PLAN}`, "--out", join(work, "plan.pdf")], { env, cwd: root });
    expect(r.code).toBe(0);
    expect((await ath(["--root", root, "ingest", "plan.pdf"], { env, cwd: work })).code).toBe(0);
    const p = await ath(["--json", "propose", PLAN.slice(0, 8), "page=1"], { env, cwd: root });
    expect(p.code, p.stdout).toBe(0);
    const hints = (p.json() as { data: { hints: { op: string; text: string; units: { at: string }[] }[] } }).data.hints;
    expect(hints.map((h) => h.op)).toEqual(["pdf.words@1"]);
    expect(hints[0]!.text.split("\n")[0]).toBe("Mooring plan 2026");
    expect(hints[0]!.units[0]!.at).toMatch(/^page=1&bbox=/);
    expect((await ath(["propose", ZIP.slice(0, 8)], { env, cwd: root })).code).toBe(64);
  });
});
