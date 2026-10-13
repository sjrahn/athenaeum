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
const PDF = join(R, "am-tool-03-v3.pdf");
const ZIP = join(R, "discord-export.zip");
const PASS = join(TESTDATA, "passes", "404d090fea45729f3e5933835fbd833ec7859595ccc5b6cf47f77ac0850f5232.p1.jsonl");
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
    const a = await loadArtifact(chain, o, ing.blake3);
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
    const a = await loadArtifact(chain, o, ing.blake3);
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

describe("regression: CDM TOOL03 (pdf, asserted tree)", () => {
  test.skipIf(!existsSync(PDF))(
    "ingest → pass open → append the fixture (121 revs recompute) → sign → inspect → lint → export",
    async () => {
      const f = foundation();
      const ing = await ath(
        [
          "--json",
          "ingest",
          PDF,
          "--origin",
          "cdm.unfccc.int",
          "--via",
          "upload",
          "--uri",
          "https://cdm.unfccc.int/methodologies/PAmethodologies/tools/am-tool-03-v3.pdf",
          "--received",
          "2026-10-13",
        ],
        { cwd: f, env },
      );
      const id = (ing.json() as { data: { ingested: { blake3: string; mime: string }[] } }).data.ingested[0]!;
      expect(id.blake3).toBe("404d090fea45729f3e5933835fbd833ec7859595ccc5b6cf47f77ac0850f5232");
      expect(id.mime).toBe("application/pdf");
      const open = await ath(["--json", "pass", "open", id.blake3, "--by", "claude-opus-4-8", "--verify", "claude-sonnet-5_3"], {
        cwd: f,
        env,
      });
      expect((open.json() as { data: { id: string } }).data.id).toBe("p1");
      const app = await ath(["--json", "claims", "append", id.blake3, "--pass", "p1", "--from", PASS], { cwd: f, env });
      expect(app.code, app.stderr).toBe(0);
      expect((app.json() as { data: { staged: number } }).data.staged).toBe(410);
      const sign = await ath(["--json", "pass", "sign", id.blake3, "p1", "--walked"], { cwd: f, env });
      const sd = (sign.json() as { data: { signed: boolean; findings: { code: string; severity: string; msg: string }[] } }).data;
      expect(sd.findings.filter((x) => x.severity === "block").map((x) => `${x.code} ${x.msg}`)).toEqual([]);
      expect(sd.signed).toBe(true);
      const insp = await ath(["--json", "inspect", id.blake3], { cwd: f, env });
      const rows = (insp.json() as { data: { rows: { terms: string[]; state: string }[]; counts: Record<string, number> } }).data;
      expect(rows.counts.ok).toBeGreaterThan(100);
      expect(rows.rows.filter((r) => r.state === "diverges").every((r) => r.terms.includes("equation"))).toBe(true);
      expect((await ath(["lint", id.blake3], { cwd: f, env })).code).toBe(0);
      const at = await ath(["tree", "at", id.blake3, "sec=5&para=6"], { cwd: f, env });
      expect(at.stdout).toContain("(paragraph)");
      const md = await ath(["export", "markdown", id.blake3], { cwd: f, env });
      expect(md.stdout).toContain("## 5. Baseline methodology procedure");
      expect(md.stdout).toContain("\\tag*{Equation (1)}");
    },
  );
});

describe("regression: a Discord export (zip, container)", () => {
  test.skipIf(!existsSync(ZIP))("members are subjects; the JSON and the PNGs classify; a route canonicalises to the member", async () => {
    const f = foundation();
    const chain = loadChain(f);
    const o = loadOntology(chain);
    const ing = await ingestFile(chain, ZIP, { date: "2026-10-13", provenance: { origin: "discord", via: "export" } });
    expect(ing.mime).toBe("application/zip");
    expect(ing.members.length).toBe(9);
    expect(ing.members.map((m) => m.mime).sort()).toEqual(["application/json", ...Array(7).fill("image/png"), "image/svg+xml"].sort());
    const a = await loadArtifact(chain, o, ing.blake3);
    expect(a.root).toBe("zip");
    const png = ing.members.find((m) => m.mime === "image/png")!;
    const pa = await loadArtifact(chain, o, png.blake3);
    expect(pa.root).toBe("png");
    expect(pa.tree).toBe("asserted");
    expect((pa.capturedFrom!.value as { container: string }).container).toBe(`corpus://${ing.blake3}`);
    expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
  });
});
