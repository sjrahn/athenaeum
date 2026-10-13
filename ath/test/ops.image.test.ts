// ops.image.test.ts — image.words@1 as a proposal: tesseract over the synthetic sign, the proposal staged on a pass,
// L7 listing every image reading (no derivation), the export carrying the labels. Skips without tesseract.
import { describe, expect, test } from "bun:test";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { ocrWords, parseTsv, proposalLines } from "../src/engine/ops/image/words.ts";
import { ath } from "./harness.ts";
import { foundation, TESTDATA } from "./layers.ts";

const SIGN = join(TESTDATA, "synthetic", "sign.jpg");
const env = { ATH_ACTOR: "tester" };
const hasTesseract = Bun.which("tesseract") !== null;

describe("image.words@1", () => {
  test("parseTsv groups words into lines with normalised boxes", () => {
    const tsv = [
      "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
      "5\t1\t1\t1\t1\t1\t10\t20\t100\t40\t90\tHello",
      "5\t1\t1\t1\t1\t2\t120\t20\t80\t40\t91\tthere",
      "5\t1\t1\t1\t2\t1\t10\t100\t50\t40\t88\tBye",
      "4\t1\t1\t1\t2\t0\t0\t0\t0\t0\t-1\t",
    ].join("\n");
    const lines = parseTsv(tsv, 1000, 500);
    expect(lines.length).toBe(2);
    expect(lines[0]!.text).toBe("Hello there");
    expect(lines[0]!.bbox).toEqual([0.01, 0.04, 0.19, 0.08]);
    expect(lines[1]!.text).toBe("Bye");
    const p = proposalLines({ engine: "t", width: 1000, height: 500, lines });
    expect(p.length).toBe(6);
    expect(p[0]).toEqual({ at: "bbox=0.01,0.04,0.19,0.08", predicate: "manifests", term: "label" });
    expect(p[2]).toMatchObject({ predicate: "reads_as", aspect: "text", body: "Hello there" });
  });

  test.skipIf(!hasTesseract)("the synthetic sign reads back; staged, signed, listed by L7, exported", async () => {
    const bytes = new Uint8Array(await Bun.file(SIGN).arrayBuffer());
    const res = ocrWords(bytes, "image/jpeg");
    expect(res.width).toBe(900);
    expect(res.lines.length).toBeGreaterThanOrEqual(3);
    expect(res.lines[0]!.text).toBe("RETURNS ONLY");
    expect(res.lines.every((l) => l.bbox.every((n) => n >= 0 && n <= 1))).toBe(true);
    const f = foundation();
    const ing = await ath(["--json", "ingest", SIGN, "--origin", "synthetic", "--via", "upload", "--received", "2026-10-13"], {
      cwd: f,
      env,
    });
    const id = (ing.json() as { data: { ingested: { blake3: string; mime: string }[] } }).data.ingested[0]!;
    expect(id.mime).toBe("image/jpeg");
    const tree0 = await ath(["--json", "tree", id.blake3], { cwd: f, env });
    expect((tree0.json() as { data: { root: string; tree: string } }).data).toMatchObject({ root: "jpeg", tree: "asserted" });
    const prop = await ath(["image", "words", id.blake3], { cwd: f, env });
    expect(prop.code).toBe(0);
    const file = join(f, "ocr.jsonl");
    writeFileSync(file, prop.stdout);
    await ath(["pass", "open", id.blake3, "--by", "tesseract-5", "--verify", "claude-sonnet"], { cwd: f, env });
    expect((await ath(["claims", "append", id.blake3, "--pass", "p1", "--from", file], { cwd: f, env })).code).toBe(0);
    const sign = await ath(["--json", "pass", "sign", id.blake3, "p1"], { cwd: f, env });
    expect((sign.json() as { data: { signed: boolean } }).data.signed).toBe(true);
    const insp = await ath(["--json", "inspect", id.blake3, "--all"], { cwd: f, env });
    const counts = (insp.json() as { data: { counts: Record<string, number> } }).data.counts;
    expect(Object.keys(counts)).toEqual(["no-derivation"]);
    expect(counts["no-derivation"]).toBeGreaterThanOrEqual(3);
    const md = await ath(["export", "markdown", id.blake3], { cwd: f, env });
    expect(md.stdout).toContain("RETURNS ONLY");
    expect(md.stdout).toContain("<!-- bbox=");
    expect((await ath(["lint", id.blake3], { cwd: f, env })).code).toBe(0);
  });
});
