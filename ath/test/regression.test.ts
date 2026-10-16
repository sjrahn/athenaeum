// regression.test.ts — the regression set (spec/successor.md Appendix B) over the real bytes. Self-skips per artifact
// when the bytes are not placed under testdata/regression/ (private exports; see testdata/README.md).
import { describe, expect, test } from "bun:test";
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { loadArtifact } from "../src/engine/corpus/derive.ts";
import { ingestFile } from "../src/engine/corpus/ingest.ts";
import { loadChain } from "../src/engine/layer/config.ts";
import { loadOntology } from "../src/engine/ontology/load.ts";
import { readCentralDirectory } from "../src/engine/ops/zip/roster.ts";
import { ath } from "./harness.ts";
import { foundation, TESTDATA } from "./layers.ts";

const R = process.env.ATH_REGRESSION ?? join(TESTDATA, "regression");
const HTML = join(R, "g8board-idle-stall-292301.html");
const CSV = join(R, "amazon-order-history.csv");
const ZIP = join(R, "discord-export.zip");
const EML = join(R, "gocf-2026-wpg.eml");
const EPUB = join(R, "novel.epub");
const MBOX = join(R, "gmail-slice.mbox");
const TWIN_PDF = join(TESTDATA, "synthetic", "procedure.pdf");
const TWIN_ID = "5e6e497d934498fc49229ba8c594684114a1213426bc1ad0113718ae72794269";
const TWIN_PASS = join(TESTDATA, "passes", `${TWIN_ID}.p1.jsonl`);
const SYN = join(TESTDATA, "synthetic");
const env = { ATH_ACTOR: "regression" };

describe("regression: the XenForo thread (html, derived tree)", () => {
  test.skipIf(!existsSync(HTML))("72 scopes by select; 31 derived bodies byte-for-byte; harvest; verify; lint; export", async () => {
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
    // 31 derived bodies byte-for-byte: 21 under html.text@1, the 10 timestamps under html.attr@1 datetime, the op
    // each term's chain names (D-derivation)
    const fixture = (await Bun.file(join(import.meta.dir, "fixtures", "g8board-html-text.json")).json()) as {
      at: string;
      term: string;
      body: string;
      rev?: string;
    }[];
    expect(fixture.length).toBe(31);
    for (const fx of fixture) {
      const s = a.table.get(fx.at);
      expect(s, fx.at).toBeDefined();
      expect(s!.readings[0]?.body, `${fx.term} at ${fx.at}`).toBe(fx.body);
      expect(s!.readings[0]?.rev, `${fx.term} at ${fx.at}`).toBe(fx.rev ?? "derived:html.text@1");
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

describe("regression: the calculation procedure (pdf, asserted tree — generated, with its generated pass)", () => {
  test("ingest → pass open → append the generated pass → sign --walked → inspect → lint → tree at → harvest → verify → export", async () => {
    const f = foundation();
    const ing = await ath(["--json", "ingest", TWIN_PDF, "--origin", "synthetic", "--via", "upload", "--received", "2026-10-15"], {
      cwd: f,
      env,
    });
    const id = (ing.json() as { data: { ingested: { blake3: string; mime: string }[] } }).data.ingested[0]!;
    expect(id.blake3).toBe(TWIN_ID);
    expect(id.mime).toBe("application/pdf");
    const open = await ath(["--json", "pass", "open", id.blake3, "--by", "gen-author", "--verify", "gen-verifier"], { cwd: f, env });
    expect((open.json() as { data: { id: string } }).data.id).toBe("p1");
    const app = await ath(["--json", "claims", "append", id.blake3, "--pass", "p1", "--from", TWIN_PASS], { cwd: f, env });
    expect(app.code, app.stderr).toBe(0);
    expect((app.json() as { data: { staged: number } }).data.staged).toBe(436); // every rev recomputes
    const sign = await ath(["--json", "pass", "sign", id.blake3, "p1", "--walked"], { cwd: f, env });
    const sd = (sign.json() as { data: { signed: boolean; findings: { code: string; severity: string; msg: string }[] } }).data;
    expect(sd.findings.filter((x) => x.severity === "block")).toEqual([]);
    expect(sd.signed).toBe(true);
    const chain = loadChain(f);
    const a = await loadArtifact(chain, loadOntology(chain), id.blake3);
    expect(a.root).toBe("methodological-tool");
    expect(a.tree).toBe("asserted");
    expect(a.pdf!.pages.length).toBe(8);
    expect(a.pdf!.chrome.length).toBe(16); // a running header and a footer on every page
    expect(a.table.unreachable().every((s) => /^page=\d+$/.test(s.at))).toBe(true); // pages past the toc stay physical
    // a container that crosses a page break (a definition list, a parameter table) is one scope at a union address
    expect([...a.table.scopes.keys()].filter((k) => k.includes(";")).length).toBe(2);
    // L7: every reading agrees with pdf.words@1 — the four equations through the tex comparator, the greek by name
    const insp = await ath(["--json", "inspect", id.blake3, "--all"], { cwd: f, env });
    expect((insp.json() as { data: { counts: Record<string, number> } }).data.counts).toEqual({ ok: 131 });
    const lint = await ath(["--json", "lint", id.blake3], { cwd: f, env });
    expect(lint.code).toBe(0);
    expect((lint.json() as { data: { findings: { code: string }[] } }).data.findings.map((x) => x.code).sort()).toEqual([
      "T-expects",
      "T-lint",
    ]);
    // designated addresses: a later key narrows inside the earlier one's subtree; a capture answers for its field
    expect((await ath(["tree", "at", id.blake3, "sec=3&para=8"], { cwd: f, env })).stdout).toContain("(paragraph)");
    expect((await ath(["tree", "at", id.blake3, "sec=5.2&eq=2"], { cwd: f, env })).stdout).toContain("(equation)");
    expect((await ath(["tree", "at", id.blake3, "sec=6.2&table=3"], { cwd: f, env })).stdout).toContain("(parameter-table)");
    expect((await ath(["tree", "at", id.blake3, "sec=6.2&table=1"], { cwd: f, env })).code).toBe(66);
    // harvest: a parameter per definition (keyed by the symbol cell), a monitored parameter per key-value table
    // (keyed by its "Data / parameter:" row), the tool itself from the metadata block; every entry binds
    const h = await ath(["--json", "harvest", id.blake3], { cwd: f, env });
    expect(h.code, h.stderr).toBe(0);
    const hd = (h.json() as { data: { concepts: number; claims: number; entries: number; written: string[] } }).data;
    expect(hd).toMatchObject({ concepts: 18, claims: 65, entries: 73 });
    expect(hd.written.filter((w) => w.startsWith("monitored-parameter-")).length).toBe(5);
    expect(hd.written.filter((w) => w.startsWith("parameter-")).length).toBe(12);
    const v = await ath(["--json", "verify", "--all"], { cwd: f, env });
    const vd = (v.json() as { data: { counts: { bound: number; entries: number; flagged: number; byStatus: Record<string, number> } } })
      .data;
    expect(vd.counts).toMatchObject({ entries: 73, bound: 73, flagged: 0, byStatus: { confirmed: 56, provisional: 9 } });
    expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
    const md = await ath(["export", "markdown", id.blake3], { cwd: f, env });
    expect(md.stdout).toContain("remainder  0 of 2671 words");
    expect(md.stdout).toContain("## 5. Calculation procedure");
    expect(md.stdout).toContain("\\tag*{Equation (2)}");
    expect(md.stdout).toContain("| Data / parameter: | $T_{a,y}$ |");
  });
});

describe("regression: the forum thread (html, derived tree — the generated twin of the XenForo capture)", () => {
  test("72 scopes by select; the banner is provenance; harvest, verify, lint, tree at, export", async () => {
    const f = foundation();
    const chain = loadChain(f);
    const o = loadOntology(chain);
    const ing = await ingestFile(chain, join(SYN, "harbourboard-thread.html"), { date: "2026-10-16" });
    expect(ing.blake3).toBe("b83e99eefb2230f36622c9654bf857ed8555dbef352de20cc67d6f8e9009128c");
    expect(ing.capturedFrom?.value).toMatchObject({
      origin: "harbourboard.example",
      uri: "https://www.harbourboard.example/threads/mooring-line-chafe.48213/",
      via: "capture",
      snapshot: "2026-08-15T23:40:36Z",
      fidelity: "lean",
    });
    const a = await loadArtifact(chain, o, ing.blake3);
    expect(a.root).toBe("xenforo-thread");
    expect(a.table.size).toBe(72);
    expect(a.table.unreachable()).toEqual([]);
    const title = a.table.find("thread-title")!;
    expect(title.at).toBe("bytes=4455,4537");
    expect(title.readings[0]).toMatchObject({ body: "Mooring line chafe — ✓ sorted", rev: "derived:html.text@1" });
    expect(a.table.findAll("post").map((p) => p.fields.position)).toEqual(["#1", "#2", "#3", "#4", "#5", "#6", "#7", "#8", "#9", "#10"]);
    expect(a.table.findAll("timestamp").every((t) => t.readings[0]?.rev === "derived:html.attr@1 datetime")).toBe(true);
    // XenForo carries a quote's source on the attribution link, not on the blockquote: the `quote` select matches nothing
    expect(a.table.findAll("quote")).toEqual([]);
    const h = await ath(["--json", "harvest", ing.blake3], { cwd: f, env });
    expect((h.json() as { data: { concepts: number; claims: number; entries: number } }).data).toMatchObject({
      concepts: 17,
      claims: 68,
      entries: 83,
    });
    const v = await ath(["--json", "verify", "--all"], { cwd: f, env });
    expect(v.code).toBe(0);
    const vd = (
      v.json() as { data: { counts: { bound: number; entries: number; flagged: number; held: number; byStatus: Record<string, number> } } }
    ).data;
    expect(vd.counts).toMatchObject({ entries: 83, bound: 83, flagged: 0, held: 0, byStatus: { confirmed: 58, provisional: 10 } });
    expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
    expect((await ath(["tree", "at", ing.blake3, "post=4"], { cwd: f, env })).stdout.trim()).toBe("bytes=9216,10770  (post)");
    const md = await ath(["export", "markdown", ing.blake3], { cwd: f, env });
    expect(md.stdout).toContain("remainder  22 of 6376");
    expect(md.stdout).toContain("<!-- bytes=4455,4537 -->\n# Mooring line chafe");
  });
});

describe("regression: the regatta mailing (rfc822, derived tree — the generated twin of the festival mailing)", () => {
  test("header + body + blocks; the HTML alternative and three attachments are subjects; the message harvests", async () => {
    const f = foundation();
    const chain = loadChain(f);
    const o = loadOntology(chain);
    const ing = await ingestFile(chain, join(SYN, "regatta-mailing.eml"), {
      date: "2026-10-16",
      provenance: { origin: "gmail", via: "export" },
    });
    expect(ing.blake3).toBe("6cdfa47f2509ead14a3818eac7b16c6e20800f6fe5b1e6c93c188e0b72562dfc");
    expect(ing.mime).toBe("message/rfc822");
    expect(ing.attests.value).toMatchObject({
      content_type: "multipart/mixed",
      date_iso: "2026-04-22T03:33:28Z",
      subject: "Port Ellen Regatta 2026 — volunteer schedule, poster and roles",
    });
    expect((ing.attests.value as { parts: unknown[] }).parts.length).toBe(6);
    expect(ing.members.map((m) => m.mime)).toEqual([
      "text/html",
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "image/jpeg",
      "application/pdf",
    ]);
    expect((ing.attests.value as { members: { filename?: string }[] }).members.map((m) => m.filename ?? null)).toEqual([
      null,
      "2026 Regatta Schedule.xlsx",
      "Regatta-Volunteer-Poster.jpg",
      "Regatta Roles 2026.pdf",
    ]);
    const a = await loadArtifact(chain, o, ing.blake3);
    expect(a.root).toBe("rfc822");
    expect(a.table.walk().map((s) => s.terms.join("+"))).toEqual([
      "rfc822",
      "message-header",
      "message-body",
      ...Array(6).fill("paragraph"),
      "signature",
    ]);
    expect(a.table.find("message-body")!.fields).toEqual({ part: "1.1", encoding: "quoted-printable", charset: "UTF-8" });
    for (const m of ing.members) {
      const ma = await loadArtifact(chain, o, m.blake3);
      expect(ma.root, m.mime).toBe({ "text/html": "html", "image/jpeg": "jpeg", "application/pdf": "pdf" }[m.mime] ?? "xlsx");
    }
    const h = await ath(["--json", "harvest", ing.blake3], { cwd: f, env });
    expect((h.json() as { data: { concepts: number; claims: number } }).data).toMatchObject({ concepts: 1, claims: 4 });
    const v = await ath(["--json", "verify", "--all"], { cwd: f, env });
    const vd = (v.json() as { data: { counts: { bound: number; entries: number; flagged: number } } }).data;
    expect(vd.counts).toMatchObject({ entries: 4, bound: 4, flagged: 0 });
    expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
    expect((await ath(["tree", "at", ing.blake3, "1/0"], { cwd: f, env })).stdout).toContain("(paragraph)");
  });
});

describe("regression: the lantern novel (epub, container with a spine — the generated twin of the novel)", () => {
  test("52 members, 25 spine items in order; a chapter classifies by its package and derives; the publication harvests", async () => {
    const f = foundation();
    const chain = loadChain(f);
    const o = loadOntology(chain);
    const ing = await ingestFile(chain, join(SYN, "lantern-novel.epub"), {
      date: "2026-10-16",
      provenance: { origin: "synthetic", via: "upload" },
    });
    expect(ing.blake3).toBe("a04764fbe6acb210160ea018f07f3b3e5bdf48a6f3e06c96f60116d54ee9c673");
    expect(ing.mime).toBe("application/epub+zip");
    expect(ing.members.length).toBe(52);
    expect(ing.attests.value).toMatchObject({
      title: "The Lantern Room",
      creator: "Ida Thorn",
      language: "en",
      isbn: "9780000000019",
      opf: "content.opf",
    });
    const a = await loadArtifact(chain, o, ing.blake3);
    expect(a.root).toBe("epub");
    const walk = a.table.walk();
    expect(walk.length).toBe(26);
    expect(walk[1]!.at).toBe("path=text%2Ftitlepage.xhtml");
    expect(walk.slice(1).every((s) => s.terms[0] === "spine-item")).toBe(true);
    const ch = ing.members.find((m) => (m.capturedFrom!.value as { path: string }).path === "text/part0005.html")!;
    const ca = await loadArtifact(chain, o, ch.blake3);
    expect(ca.root).toBe("epub-chapter");
    expect(ca.table.findAll("paragraph").length).toBe(606);
    expect(ca.table.findAll("quote").length).toBe(6);
    expect(ca.table.findAll("paragraph").every((p) => p.readings[0]?.rev === "derived:html.text@1")).toBe(true);
    const h = await ath(["--json", "harvest", ing.blake3], { cwd: f, env });
    expect((h.json() as { data: { concepts: number; claims: number } }).data).toMatchObject({ concepts: 1, claims: 5 });
    const v = await ath(["--json", "verify", "--all"], { cwd: f, env });
    const vd = (v.json() as { data: { counts: { bound: number; entries: number; flagged: number } } }).data;
    expect(vd.counts).toMatchObject({ entries: 5, bound: 5, flagged: 0 });
    expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
  });
});

describe("regression: the quay chat archive (mbox, container of messages — the generated twin of the mailbox slice)", () => {
  test("358 messages are subjects, every one a message; alternatives are members; nothing lands on the mailbox", async () => {
    const f = foundation();
    const chain = loadChain(f);
    const o = loadOntology(chain);
    const ing = await ingestFile(chain, join(SYN, "quay-chat.mbox"), {
      date: "2026-10-16",
      provenance: { origin: "google-takeout", via: "export" },
    });
    expect(ing.blake3).toBe("489636cafe2eeb8e2e639189383e291c8f8404e097799af6824467485265c4a3");
    expect(ing.mime).toBe("application/mbox");
    expect(ing.members.length).toBe(358);
    expect(ing.members.every((m) => m.mime === "message/rfc822")).toBe(true);
    const a = await loadArtifact(chain, o, ing.blake3);
    expect(a.root).toBe("mbox");
    expect(a.table.size).toBe(1);
    let bodies = 0;
    let htmlAlternatives = 0;
    let stuffed = 0;
    for (const m of ing.members) {
      const ma = await loadArtifact(chain, o, m.blake3);
      expect(ma.root).toBe("rfc822");
      const body = ma.table.find("message-body");
      if (body) {
        bodies++;
        if (String(body.readings[0]?.body).includes("\nFrom the quay")) stuffed++; // un-stuffed on the way out
      }
      const roster = (ma.attests.value as { members?: { mime: string }[] }).members ?? [];
      if (roster.some((r) => r.mime === "text/html")) htmlAlternatives++;
    }
    expect(bodies).toBe(2);
    expect(stuffed).toBe(2);
    expect(htmlAlternatives).toBe(358);
    expect(readdirSync(join(f, "corpus")).filter((n) => n.endsWith(".claims.jsonl")).length).toBe(1 + 358);
    expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
  });
});

describe("regression: the quay chat export (zip, container — the generated twin of the Discord export)", () => {
  test("members are subjects; the JSON and the SVG are zstd (method 93), the PNGs stored; a route canonicalises to the member", async () => {
    const f = foundation();
    const chain = loadChain(f);
    const o = loadOntology(chain);
    const bytes = new Uint8Array(await Bun.file(join(SYN, "quay-chat-export.zip")).arrayBuffer());
    expect(readCentralDirectory(bytes).map((e) => e.method)).toEqual([93, 0, 0, 0, 0, 0, 0, 0, 93]);
    const ing = await ingestFile(chain, join(SYN, "quay-chat-export.zip"), {
      date: "2026-10-16",
      provenance: { origin: "discord", via: "export" },
    });
    expect(ing.blake3).toBe("0cc4bf7d6def2f15484b2d14ddafdeb9e13a1a4b2b1a7d2e9b5398a962feda03");
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
      // D-members-depth: a member's own members stay on its roster; nothing below the mailbox's messages is a subject
      expect(readdirSync(join(f, "corpus")).filter((n) => n.endsWith(".claims.jsonl")).length).toBe(1 + 358);
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
