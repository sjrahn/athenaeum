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
const EML = join(R, "gocf-2026-wpg.eml");
const EPUB = join(R, "novel.epub");
const MBOX = join(R, "gmail-slice.mbox");
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

describe("regression: a festival mailing (rfc822, derived tree, four attachments)", () => {
  test.skipIf(!existsSync(EML))(
    "header + body + blocks; the HTML alternative and three attachments are subjects; the message harvests",
    async () => {
      const f = foundation();
      const chain = loadChain(f);
      const o = loadOntology(chain);
      const ing = await ingestFile(chain, EML, { date: "2026-10-13", provenance: { origin: "gmail", via: "export" } });
      expect(ing.blake3).toBe("36c1188d271552f814612c517fbec5da425a42883d63a87fd4116675530adbfe");
      expect(ing.mime).toBe("message/rfc822");
      expect(ing.attests.value).toMatchObject({ content_type: "multipart/mixed", date_iso: "2026-04-22T03:33:28Z" });
      expect((ing.attests.value as { parts: unknown[] }).parts.length).toBe(6);
      expect(ing.members.map((m) => m.mime)).toEqual([
        "text/html",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "image/jpeg",
        "application/pdf",
      ]);
      const a = await loadArtifact(chain, o, ing.blake3);
      expect(a.root).toBe("rfc822");
      expect(a.table.walk().map((s) => s.terms.join("+"))).toEqual([
        "rfc822",
        "message-header",
        "message-body",
        "paragraph",
        "paragraph",
        "paragraph",
        "paragraph",
        "paragraph",
        "signature",
      ]);
      const body = a.table.find("message-body")!;
      expect(body.fields).toEqual({ part: "1.1", encoding: "quoted-printable", charset: "UTF-8" });
      for (const m of ing.members) {
        const ma = await loadArtifact(chain, o, m.blake3);
        expect(ma.root, m.mime).toBe({ "text/html": "html", "image/jpeg": "jpeg", "application/pdf": "pdf" }[m.mime] ?? "xlsx");
      }
      const h = await ath(["--json", "harvest", ing.blake3], { cwd: f, env });
      expect((h.json() as { data: { concepts: number; claims: number } }).data).toMatchObject({ concepts: 1, claims: 4 });
      const v = await ath(["--json", "verify", "--all"], { cwd: f, env });
      const vd = (v.json() as { data: { counts: { bound: number; entries: number; flagged: number } } }).data;
      expect(vd.counts.flagged).toBe(0);
      expect(vd.counts.bound).toBe(vd.counts.entries);
      expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
      const at = await ath(["tree", "at", ing.blake3, "1/0"], { cwd: f, env });
      expect(at.stdout).toContain("(paragraph)");
    },
  );
});

describe("regression: a novel (epub, container with a spine)", () => {
  test.skipIf(!existsSync(EPUB))(
    "52 members, 25 spine items in order; a chapter classifies by its package and derives; the publication harvests",
    async () => {
      const f = foundation();
      const chain = loadChain(f);
      const o = loadOntology(chain);
      const ing = await ingestFile(chain, EPUB, { date: "2026-10-13", provenance: { origin: "discord", via: "export" } });
      expect(ing.blake3).toBe("b8ded2e04ee9a11c3d401e8d39e64497426772f480cbde765abeb917a4732fee");
      expect(ing.mime).toBe("application/epub+zip");
      expect(ing.members.length).toBe(52);
      expect(ing.attests.value).toMatchObject({ title: "Dark Matter", language: "en", isbn: "9781101904237", opf: "content.opf" });
      const a = await loadArtifact(chain, o, ing.blake3);
      expect(a.root).toBe("epub");
      const walk = a.table.walk();
      expect(walk.length).toBe(26);
      expect(walk[1]!.at).toBe("path=text%2Ftitlepage.xhtml");
      expect(walk.slice(1).every((s) => s.terms[0] === "spine-item")).toBe(true);
      const ch = ing.members.find((m) => (m.capturedFrom!.value as { path: string }).path === "text/part0005.html")!;
      const ca = await loadArtifact(chain, o, ch.blake3);
      expect(ca.root).toBe("epub-chapter");
      expect(ca.table.findAll("paragraph").length).toBe(608);
      expect(ca.table.findAll("quote").length).toBe(6);
      expect(ca.table.findAll("paragraph").every((p) => p.readings[0]?.rev === "derived:html.text@1")).toBe(true);
      const h = await ath(["--json", "harvest", ing.blake3], { cwd: f, env });
      expect((h.json() as { data: { concepts: number; claims: number } }).data).toMatchObject({ concepts: 1, claims: 5 });
      const v = await ath(["--json", "verify", "--all"], { cwd: f, env });
      const vd = (v.json() as { data: { counts: { bound: number; entries: number; flagged: number } } }).data;
      expect(vd.counts.flagged).toBe(0);
      expect(vd.counts.bound).toBe(vd.counts.entries);
      expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
    },
  );
});

describe("regression: a mailbox slice (mbox, container of messages)", () => {
  test.skipIf(!existsSync(MBOX))(
    "358 messages are subjects, every one a message; alternatives are members; nothing lands on the mailbox",
    async () => {
      const f = foundation();
      const chain = loadChain(f);
      const o = loadOntology(chain);
      const ing = await ingestFile(chain, MBOX, { date: "2026-10-13", provenance: { origin: "google-takeout", via: "export" } });
      expect(ing.blake3).toBe("7755d697e7ab330535d4c3555ecae4334176f6353758fce6404adc62546d5116");
      expect(ing.mime).toBe("application/mbox");
      expect(ing.members.length).toBe(358);
      expect(ing.members.every((m) => m.mime === "message/rfc822")).toBe(true);
      const a = await loadArtifact(chain, o, ing.blake3);
      expect(a.root).toBe("mbox");
      expect(a.table.size).toBe(1);
      // a chat archive: nearly every message is text/xml + text/html alternatives (both members, D-rfc822), two carry a text/plain body
      let bodies = 0;
      let htmlAlternatives = 0;
      for (const m of ing.members) {
        const ma = await loadArtifact(chain, o, m.blake3);
        expect(ma.root).toBe("rfc822");
        if (ma.table.find("message-body")) bodies++;
        const roster = (ma.attests.value as { members?: { mime: string }[] }).members ?? [];
        if (roster.some((r) => r.mime === "text/html")) htmlAlternatives++;
      }
      expect(bodies).toBe(2);
      expect(htmlAlternatives).toBeGreaterThan(300);
      expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
    },
  );
});

/** One exemplar per mime (testdata/exemplars.yaml): every placed file ingests, classifies to its root term, and lints clean. */
describe("regression: one exemplar per mime", () => {
  const manifest = (
    Bun.YAML.parse(require("node:fs").readFileSync(join(TESTDATA, "exemplars.yaml"), "utf8")) as {
      file: string;
      mime: string;
      root: string;
      blake3: string;
      source: string;
    }[]
  ).filter((e) => e.source === "regression" || e.source === "synthetic");
  for (const e of manifest) {
    const path = join(e.source === "regression" ? R : join(TESTDATA, "synthetic"), e.file);
    test.skipIf(!existsSync(path))(`${e.mime} → ${e.root}`, async () => {
      const f = foundation();
      const chain = loadChain(f);
      const o = loadOntology(chain);
      const ing = await ingestFile(chain, path, { date: "2026-10-13", members: false });
      expect(ing.blake3).toBe(e.blake3);
      expect(ing.mime).toBe(e.mime);
      const a = await loadArtifact(chain, o, ing.blake3);
      expect(a.root).toBe(e.root);
      expect((await ath(["lint", ing.blake3], { cwd: f, env })).code).toBe(0);
    });
  }
});
