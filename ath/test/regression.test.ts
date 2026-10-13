// regression.test.ts — the regression set (spec/successor.md Appendix B) over the real bytes. Self-skips per artifact
// when the bytes are not placed under testdata/regression/ (private exports; see testdata/README.md).
import { describe, expect, test } from "bun:test";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { loadArtifact } from "../src/engine/corpus/derive.ts";
import { ingestFile } from "../src/engine/corpus/ingest.ts";
import { loadChain } from "../src/engine/layer/config.ts";
import { loadOntology } from "../src/engine/ontology/load.ts";
import { ath } from "./harness.ts";
import { foundation, TESTDATA } from "./layers.ts";

const R = process.env.ATH_REGRESSION ?? join(TESTDATA, "regression");
const HTML = join(R, "g8board-idle-stall-292301.html");
const CSV = join(R, "amazon-order-history.csv");
const env = { ATH_ACTOR: "regression" };

describe("regression: the XenForo thread (html, derived tree)", () => {
  test.skipIf(!existsSync(HTML))("72 scopes by select; 31 html.text@1 bodies byte-for-byte; harvest; verify; lint; export", async () => {
    const f = foundation();
    const chain = loadChain(f);
    const o = loadOntology(chain);
    const ing = await ingestFile(chain, HTML, { date: "2026-10-13" });
    expect(ing.blake3).toBe("dd0a78441fe3ae117f520809a759dac6cba0fbf52737bb2baf1cd19e1d695299");
    expect(ing.capturedFrom?.value).toMatchObject({
      origin: "g8board.com",
      uri: "https://www.g8board.com/threads/idle-stall.292301/",
      via: "capture",
      snapshot: "2026-08-15T23:40:36Z",
      fidelity: "lean",
    });
    const a = loadArtifact(chain, o, ing.blake3);
    expect(a.root).toBe("xenforo-thread");
    expect(a.table.size).toBe(72);
    expect(a.table.unreachable()).toEqual([]);
    const fixture = (await Bun.file(join(import.meta.dir, "fixtures", "g8board-html-text.json")).json()) as {
      at: string;
      term: string;
      body: string;
    }[];
    expect(fixture.length).toBe(31);
    for (const fx of fixture) {
      const s = a.table.get(fx.at);
      expect(s, fx.at).toBeDefined();
      expect(s!.readings[0]?.body, `${fx.term} at ${fx.at}`).toBe(fx.body);
    }
    expect(a.table.findAll("post").map((p) => p.fields.position)).toEqual(["#1", "#2", "#3", "#4", "#5", "#6", "#7", "#8", "#9", "#10"]);
    const h = await ath(["--json", "harvest", ing.blake3], { cwd: f, env });
    expect((h.json() as { data: { concepts: number; claims: number; entries: number } }).data).toMatchObject({
      concepts: 16,
      claims: 65,
      entries: 83,
    });
    const v = await ath(["--json", "verify", "--all"], { cwd: f, env });
    expect(v.code).toBe(0);
    const vd = (
      v.json() as {
        data: {
          counts: {
            concepts: number;
            claims: number;
            entries: number;
            bound: number;
            flagged: number;
            held: number;
            byStatus: Record<string, number>;
          };
        };
      }
    ).data;
    expect(vd.counts).toMatchObject({ concepts: 16, claims: 65, entries: 83, bound: 83, flagged: 0, held: 0 });
    expect(vd.counts.byStatus.confirmed).toBe(57);
    expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
    const at = await ath(["tree", "at", ing.blake3, "post=4"], { cwd: f, env });
    expect(at.stdout.trim()).toBe("bytes=575696,587501  (post)");
    const md = await ath(["export", "markdown", ing.blake3], { cwd: f, env });
    expect(md.stdout).toContain("remainder  1309 of 6866");
    expect(md.stdout).toContain("<!-- bytes=518950,518985 -->\n# Idle/stall");
  });
});

describe("regression: the Amazon order history (csv, derived tree)", () => {
  test.skipIf(!existsSync(CSV))("275 records, 29 columns; 426 concepts; every entry bound", async () => {
    const f = foundation();
    const chain = loadChain(f);
    const o = loadOntology(chain);
    const ing = await ingestFile(chain, CSV, {
      date: "2026-10-13",
      provenance: { origin: "amazon.ca", via: "upload", note: "Request My Data export" },
    });
    expect(ing.blake3).toBe("1409369e05ce462408344c922183331d96fe70117f4c27389d75817e39702711");
    expect(ing.attests.value).toMatchObject({ mime: "text/csv", bytes: 151157, rows: 275, header_row: 0, cols: 29, bom: true });
    const a = loadArtifact(chain, o, ing.blake3);
    expect(a.root).toBe("amazon-order-history");
    expect(a.table.walk().length).toBe(277);
    expect(a.table.unreachable().length).toBe(29);
    const h = await ath(["--json", "harvest", ing.blake3], { cwd: f, env });
    expect((h.json() as { data: { concepts: number } }).data.concepts).toBe(426);
    const v = await ath(["--json", "verify", "--all"], { cwd: f, env });
    expect(v.code).toBe(0);
    const vd = (v.json() as { data: { counts: { concepts: number; flagged: number; held: number; entries: number; bound: number } } }).data;
    expect(vd.counts.concepts).toBe(426);
    expect(vd.counts.flagged).toBe(0);
    expect(vd.counts.bound).toBe(vd.counts.entries);
    expect((await ath(["lint", ing.blake3], { cwd: f, env })).code).toBe(0);
    const at = await ath(["tree", "at", ing.blake3, "col=Currency"], { cwd: f, env });
    expect(at.stdout.trim()).toBe("col=3  (currency-code)");
  });
});
