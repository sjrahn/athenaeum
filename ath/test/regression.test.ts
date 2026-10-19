// regression.test.ts — the regression set end to end: every exemplar in testdata/exemplars.yaml ingested, with the
// testimony beside it, into one instance that starts from the regression ontology (testdata/ontology/). The instance
// loads — the tool registers an intrinsics op for every mime and every op the vocabulary names (§19.2.2) — and its
// vocabulary checks clean; each artifact's record is its projection and loads back to the same bytes (§8.2.2); each
// classifies to the shape `classifies` names and to none where it names none (§11.5), and its tree is derived from
// that shape on a structured artifact, proposed over its hints on a rendered one (§11.7); the record checks find
// nothing blocking (§17).
import { beforeAll, describe, expect, test } from "bun:test";
import { copyFileSync, cpSync, existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { formatOf } from "@ath/engine/formats/index.ts";
import { emitRecord, loadRecord } from "@ath/engine/record/document.ts";
import { ath, scratch, TESTDATA } from "./harness.ts";

interface Exemplar {
  file: string;
  blake3: string;
  mime: string;
  classifies?: string;
}
const exemplars = Bun.YAML.parse(readFileSync(join(TESTDATA, "exemplars.yaml"), "utf8")) as Exemplar[];
const env = { ATH_ACTOR: "reader-a" };
let root = "";
const run = (argv: string[]) => ath(["--json", ...argv], { env, cwd: root });
const data = <D>(r: { json: () => unknown }) => (r.json() as { data: D }).data;

beforeAll(async () => {
  root = join(scratch(), "regression");
  expect((await ath(["instance", "init", root], { env })).code).toBe(0);
  cpSync(join(TESTDATA, "ontology"), root, { recursive: true });
  const work = scratch();
  for (const e of exemplars) {
    copyFileSync(join(TESTDATA, "synthetic", e.file), join(work, e.file));
    const t = join(TESTDATA, "synthetic", `${e.file}.testimony.yaml`);
    if (existsSync(t)) copyFileSync(t, join(work, `${e.file}.testimony.yaml`));
  }
  const r = await ath(["--json", "--root", root, "ingest", ...exemplars.map((e) => e.file)], { env, cwd: work });
  expect(r.code, r.stdout).toBe(0);
});

describe("the regression set", () => {
  test("the instance loads with every exemplar held, and its vocabulary checks clean", async () => {
    expect((await run(["instance", "check"])).code).toBe(0);
    expect((await run(["vocab", "check"])).code).toBe(0);
    const h = data<{ records: { hash: string }[] }>(await run(["holdings"]));
    expect(new Set(h.records.map((x) => x.hash))).toEqual(new Set(exemplars.map((e) => e.blake3)));
  });

  test("every record is its projection and loads back to its own bytes", () => {
    for (const e of exemplars) {
      const text = readFileSync(join(root, "corpus/records", e.blake3.slice(0, 2), `${e.blake3}.yaml`), "utf8");
      const rec = loadRecord(text, e.file);
      expect(
        Object.keys(rec).filter((k) => !["intrinsics", "receipts", "origins"].includes(k)),
        e.file,
      ).toEqual([]);
      expect(rec.intrinsics?.mime, e.file).toBe(e.mime);
      expect(emitRecord(rec), e.file).toBe(text);
      expect(rec.origins?.length ?? 0, e.file).toBe(existsSync(join(TESTDATA, "synthetic", `${e.file}.testimony.yaml`)) ? 1 : 0);
    }
  });

  test("each classifies to the shape it names, and its tree comes from that shape", async () => {
    const wrong: string[] = [];
    for (const e of exemplars) {
      const t = data<{ shape: string | null; kind: string; scopes: unknown[] }>(await run(["tree", e.blake3]));
      if (t.shape !== (e.classifies ?? null)) wrong.push(`${e.file}: classified ${t.shape}, listed ${e.classifies ?? "none"}`);
      const rendered = formatOf(e.mime).class === "rendered";
      if (e.classifies && t.kind !== (rendered ? "proposed" : "derived")) wrong.push(`${e.file}: tree ${t.kind}`);
    }
    expect(wrong).toEqual([]);
  });

  test("the record checks find nothing blocking", async () => {
    const r = await run(["check", "--all"]);
    const findings = (r.json() as { data: { findings: { level: string; subject?: string; message: string }[] } }).data.findings;
    expect(findings.filter((f) => f.level === "block")).toEqual([]);
  });
});
