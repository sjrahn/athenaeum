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
import { readJsonl } from "../src/lib/jsonl.ts";
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
  test.skipIf(!existsSync(HTML))(
    "76 scopes by select; 31 derived bodies byte-for-byte; quotes link posts; harvest; verify; lint; export",
    async () => {
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
      expect(a.table.size).toBe(76);
      // a quote is told by XenForo's markup and its attribution names the quoted post (D-attr-pattern)
      expect(a.table.findAll("quote-source").map((q) => q.fields.target)).toEqual(["post-3758898", "post-3758911"]);
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
        claims: 67,
        entries: 85,
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
      expect(vd.counts).toMatchObject({ concepts: 16, claims: 67, entries: 85, bound: 85, flagged: 0, held: 0 });
      const quoting = readJsonl(join(f, "ledger", "g8board-post-3758899.claims.jsonl")).find((l) => l.predicate === "quotes")!;
      expect(quoting.object).toBe("g8board-post-3758898");
      expect(vd.counts.byStatus.confirmed).toBe(57);
      expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
      const at = await ath(["tree", "at", ing.blake3, "post=4"], { cwd: f, env });
      expect(at.stdout.trim()).toBe("bytes=575696,587501  (post)");
      const md = await ath(["export", "markdown", ing.blake3], { cwd: f, env });
      expect(md.stdout).toContain("remainder  1309 of 6866");
      expect(md.stdout).toContain("<!-- bytes=518950,518985 -->\n# Idle/stall");
    },
  );
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
  test("76 scopes by select; the banner is provenance; quotes link posts; harvest, verify, lint, tree at, export", async () => {
    const f = foundation();
    const chain = loadChain(f);
    const o = loadOntology(chain);
    const ing = await ingestFile(chain, join(SYN, "harbourboard-thread.html"), { date: "2026-10-16" });
    expect(ing.blake3).toBe("430c0b0f1239932484a48c43bd1b0c3b069958c6ca73d273f97645d32b8b1d2e");
    expect(ing.capturedFrom?.value).toMatchObject({
      origin: "harbourboard.example",
      uri: "https://www.harbourboard.example/threads/mooring-line-chafe.48213/",
      via: "capture",
      snapshot: "2026-06-07T14:03:19Z",
      fidelity: "lean",
    });
    const a = await loadArtifact(chain, o, ing.blake3);
    expect(a.root).toBe("xenforo-thread");
    expect(a.table.size).toBe(76);
    expect(a.table.unreachable()).toEqual([]);
    const title = a.table.find("thread-title")!;
    expect(title.at).toBe("bytes=4455,4537");
    expect(title.readings[0]).toMatchObject({ body: "Mooring line chafe — ✓ sorted", rev: "derived:html.text@1" });
    expect(a.table.findAll("post").map((p) => p.fields.position)).toEqual(["#1", "#2", "#3", "#4", "#5", "#6", "#7", "#8", "#9", "#10"]);
    expect(a.table.findAll("timestamp").every((t) => t.readings[0]?.rev === "derived:html.attr@1 datetime")).toBe(true);
    // XenForo carries a quote's source on the attribution link inside the blockquote: the quote-source's target names the quoted post
    expect(a.table.findAll("quote").length).toBe(2);
    expect(a.table.findAll("quote-source").map((q) => q.fields.target)).toEqual(["post-482133", "post-482136"]);
    const h = await ath(["--json", "harvest", ing.blake3], { cwd: f, env });
    expect((h.json() as { data: { concepts: number; claims: number; entries: number } }).data).toMatchObject({
      concepts: 17,
      claims: 70,
      entries: 85,
    });
    const v = await ath(["--json", "verify", "--all"], { cwd: f, env });
    expect(v.code).toBe(0);
    const vd = (
      v.json() as { data: { counts: { bound: number; entries: number; flagged: number; held: number; byStatus: Record<string, number> } } }
    ).data;
    expect(vd.counts).toMatchObject({ entries: 85, bound: 85, flagged: 0, held: 0, byStatus: { confirmed: 58, provisional: 12 } });
    const quoting = readJsonl(join(f, "ledger", "g8board-post-482135.claims.jsonl")).find((l) => l.predicate === "quotes")!;
    expect(quoting).toMatchObject({ object: "g8board-post-482133", qualifiers: { as: "post-482133" } });
    expect((quoting.evidence as { reading: string }[])[0]!.reading).toBe("line:manifests target");
    expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
    expect((await ath(["tree", "at", ing.blake3, "post=4"], { cwd: f, env })).stdout.trim()).toBe("bytes=9216,10770  (post)");
    const md = await ath(["export", "markdown", ing.blake3], { cwd: f, env });
    expect(md.stdout).toContain("remainder  22 of 6376");
    expect(md.stdout).toContain("<!-- bytes=4455,4537 -->\n# Mooring line chafe");
  });
});

describe("regression: the quay messages (html, derived tree — the generated twin of an iMessage conversation page)", () => {
  test("a sidecar folds the export's provenance; 40 messages derive with sender, instant, bubble, attachments, a reply, reactions", async () => {
    const f = foundation();
    const chain = loadChain(f);
    const o = loadOntology(chain);
    const ing = await ath(["--json", "ingest", join(SYN, "quay-messages.html"), "--received", "2026-10-16"], { cwd: f, env });
    expect(ing.code, ing.stderr).toBe(0);
    const row = (ing.json() as { data: { ingested: { blake3: string; capturedFrom: { value: Record<string, unknown> } }[] } }).data
      .ingested[0]!;
    expect(row.blake3).toBe("2af1ebd5e916e7c54994c775685203a1b537d98e40484abd4ef5ab9389a88153");
    const a = await loadArtifact(chain, o, row.blake3);
    expect(a.capturedFrom!.value).toMatchObject({
      origin: "imessage-export",
      via: "export",
      snapshot: "2026-04-01T06:00:00Z",
      engine: "imessage-exporter 3.0.0",
      fields: { schema: "imessage-export", period: "2026-03" },
    });
    expect(a.root).toBe("imessage-conversation");
    expect(a.table.size).toBe(168);
    expect(a.table.unreachable()).toEqual([]);
    const count = (t: string) => a.table.findAll(t).length;
    expect([
      count("message"),
      count("author"),
      count("sent-at"),
      count("bubble"),
      count("attachment"),
      count("reaction"),
      count("quote"),
      count("link-card"),
      count("edit-history"),
    ]).toEqual([40, 40, 40, 38, 2, 4, 1, 1, 1]);
    const first = a.table.children(a.table.find("message")!.at);
    expect(first.map((s) => s.terms[0])).toEqual(["sent-at", "author", "bubble"]);
    expect(first[0]!.fields).toEqual({ instant: "Mar 02, 2026  9:45:38 AM" });
    expect(first[0]!.readings[0]).toMatchObject({ body: "Mar 02, 2026 9:45:38 AM", rev: "derived:html.text@1" });
    expect(a.table.find("attachment")!.fields).toEqual({ alt: "attachment" });
    expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
    expect((await ath(["export", "markdown", row.blake3], { cwd: f, env })).stdout).toContain("remainder  340 of 5099");
  });
});

describe("regression: the pump service manual (html, derived tree — the generated twin of a service-manual page capture)", () => {
  test("the banner is provenance; topics, headings, notices, steps, specification rows, figures and captions derive; nothing is left over", async () => {
    const f = foundation();
    const chain = loadChain(f);
    const o = loadOntology(chain);
    const ing = await ingestFile(chain, join(SYN, "pump-service-manual.html"), { date: "2026-10-16" });
    expect(ing.blake3).toBe("7d848c4f9fb5e9cb7cc1cab1d765ba9dd88f28f5f191e810ddcde657c3c4dc9b");
    expect(ing.capturedFrom?.value).toMatchObject({
      origin: "manuals.example.invalid",
      via: "capture",
      snapshot: "2026-05-20T15:02:11Z",
      fidelity: "lean",
    });
    const a = await loadArtifact(chain, o, ing.blake3);
    expect(a.root).toBe("service-manual-page");
    expect(a.table.size).toBe(75);
    expect(a.table.unreachable()).toEqual([]);
    const count = (t: string) => a.table.findAll(t).length;
    expect([
      count("topic"),
      count("heading"),
      count("notice"),
      count("paragraph"),
      count("procedure-step"),
      count("list-item"),
      count("spec-table"),
      count("spec-row"),
      count("figure"),
      count("caption"),
    ]).toEqual([5, 6, 4, 5, 19, 14, 3, 12, 3, 3]);
    const title = a.table.find("heading")!;
    expect(title.fields).toEqual({ level: 0 });
    expect(title.readings[0]!.body).toBe("Impeller replacement");
    expect(a.table.find("figure")!.fields.original).toBe("https://manuals.example.invalid/assets/figures/hl200-1.png");
    expect(a.table.children(a.table.find("spec-table")!.at).every((s) => s.terms[0] === "spec-row")).toBe(true);
    expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
    const md = await ath(["export", "markdown", ing.blake3], { cwd: f, env });
    expect(md.stdout).toContain("remainder  0 of 4467");
    expect(md.stdout).toContain("# Impeller replacement");
    expect(md.stdout).toContain("## Impeller removal");
  });
});

/** The export bundles (D-roster): a bundle is told by its layout, its members by their names; every member a subject. */
describe("regression: export bundles (zip, containers — generated twins of the account exports)", () => {
  const bundles: {
    file: string;
    blake3: string;
    root: string;
    origin: string;
    members: number;
    roots: Record<string, number>;
  }[] = [
    {
      file: "facebook-month-bundle.zip",
      blake3: "e82abeed5b994c8ac3fcc048ef9a9ef56fdf9be485e06ad1bbee88df815f50bb",
      root: "facebook-export-bundle",
      origin: "facebook-export-bundle",
      members: 28,
      roots: { "messenger-conversation": 4, png: 13, gif: 6, mp4: 3, json: 2 },
    },
    {
      file: "instagram-month-bundle.zip",
      blake3: "2997cc1236fc3fa8ac6010cb8fe4818accb914d8a0efb8dbc60b0bda07939135",
      root: "instagram-export-bundle",
      origin: "instagram-export-bundle",
      members: 27,
      roots: { "instagram-conversation": 3, png: 13, gif: 6, mp4: 4, json: 1 },
    },
    {
      file: "threads-month-bundle.zip",
      blake3: "a55a755c4e751fbb987eb307ceb4a9111be4f6f133ea4d32bc0aff6896998866",
      root: "threads-export-bundle",
      origin: "threads-export-bundle",
      members: 23,
      roots: { "threads-conversation": 3, png: 12, gif: 6, json: 2 },
    },
    {
      file: "chat-month-bundle.zip",
      blake3: "fb67bd410ffd71eb2b161bb3f1aaf4e6cae49c9dc2788726945074b63251e5bc",
      root: "google-chat-export-bundle",
      origin: "google-chat-export-bundle",
      members: 5,
      roots: { "google-chat-conversation": 2, "google-chat-roster": 2, png: 1 },
    },
    {
      file: "messages-week-bundle.zip",
      blake3: "7c75a49d830b525cef5f156a47057e5e922e729365e02d53df7aa161a8a7198f",
      root: "imessage-export-bundle",
      origin: "imessage-export-bundle",
      members: 4,
      roots: { "imessage-conversation": 4 },
    },
    {
      file: "mail-month-bundle.zip",
      blake3: "23725953b0780d273016a739d228ab1ae7719d0d4c3196ed7756ff318d7b32e7",
      root: "proton-mail-export",
      origin: "proton-mail-export",
      members: 12,
      roots: { rfc822: 6, "mail-export-metadata": 6 },
    },
    {
      file: "photos-month-bundle.zip",
      blake3: "2940d7706dac5b59e2526b984c358e61b6d15a61f3e9b18ff6eee333c0e78ac3",
      root: "photo-library-export",
      origin: "osxphotos-export",
      members: 13,
      roots: { heic: 2, "photo-sidecar": 6, jpeg: 3, quicktime: 1, png: 1 },
    },
    {
      file: "orders-delivery.zip",
      blake3: "e635ad727152ed032d8bbde3a56a2f97b5821b42da9c1b851408162cf6c28d23",
      root: "data-request-delivery",
      origin: "amazon-export",
      members: 6,
      roots: { csv: 3, pdf: 1, png: 1, "plain-text": 1 },
    },
    {
      file: "rides-export.zip",
      blake3: "a9fe6816e26e9d640be1839b6152b8e0c98a1db2f59c355af14acb271fe986e1",
      root: "rides-export",
      origin: "uber-export",
      members: 6,
      roots: { csv: 5, "plain-text": 1 },
    },
    {
      file: "health-export.zip",
      blake3: "bc55b3a4d2c117a93f3d02fc4c927d6ad20e202dbe8f9881cbc81e83b8417006",
      root: "health-export",
      origin: "apple-health-export",
      members: 6,
      roots: { xml: 4, csv: 1, json: 1 },
    },
    {
      file: "host-diagnostics.zip",
      blake3: "755432d18af5c7c13ec1a0b048abe410d403072afbc529373f5e26847e00dc2d",
      root: "host-diagnostics",
      origin: "host-diagnostic",
      members: 19,
      roots: { "plain-text": 19 },
    },
    {
      file: "vault-subtree.zip",
      blake3: "e0fb7ff7cbf4fe64e2330669e50540eaae1c28118e9ef7213dfcece0f4411967",
      root: "vault-export",
      origin: "obsidian-vault",
      members: 10,
      roots: { json: 2, markdown: 7, png: 1 },
    },
    {
      file: "vendor-share.zip",
      blake3: "7fafd3bd49d5586e8ad43ddd00d78dcd76b083599c41268274d70defcf4a013f",
      root: "vendor-share",
      origin: "vendor-download",
      members: 9,
      roots: { pdf: 3, dxf: 1, zip: 1, rar: 1, "seven-zip": 1, executable: 1, "plain-text": 1 },
    },
    {
      file: "agent-session.zip",
      blake3: "81f4436b4be4918124484ef6b8441694b5c34be4a2bdfa238644aee94195fbb3",
      root: "agent-session",
      origin: "claude-code-session",
      members: 5,
      roots: { ndjson: 2, json: 3 },
    },
    {
      file: "statements-year.zip",
      blake3: "f993a31d5faf7e08e823ea80b554c6085665e3034a0335b1b1d7d7e0487ce53a",
      root: "statement-series",
      origin: "bank-statement",
      members: 12,
      roots: { pdf: 12 },
    },
    {
      file: "card-dump.zip",
      blake3: "08ac924b1b01e9f58d9c8b5908e0e52d13127273948fae6b658c286f1f0723bf",
      root: "card-dump",
      origin: "camera-sd-dump",
      members: 9,
      roots: { "raw-image": 3, heic: 3, mp4: 1, xml: 2 },
    },
    {
      file: "takeout-slice.zip",
      blake3: "1d7dc1e96ea93fc2e55b9099393e5907fc1619f49f52a952bea95872c34f3387",
      root: "takeout-slice",
      origin: "google-takeout",
      members: 10,
      roots: { html: 2, xml: 2, csv: 2, vcard: 1, json: 2, calendar: 1 },
    },
    {
      file: "drive-folder.zip",
      blake3: "da7b858a7acc71ea1953f162369503c564bce9e6ec59ad1b717c6864ccaf34f0",
      root: "zip",
      origin: "google-drive-export",
      members: 4,
      roots: { pdf: 1, csv: 1, markdown: 1, png: 1 },
    },
    {
      file: "profile-year.zip",
      blake3: "96d4f9ff048b937ff9db93f4e58e02e624609166887f4bce07a4033b16ef7a00",
      root: "profile-year",
      origin: "facebook-profile-year",
      members: 6,
      roots: { json: 2, png: 3, mp4: 1 },
    },
  ];
  for (const b of bundles) {
    test(`${b.file}: ${b.root}, ${b.members} members, each a subject classified by its container and name`, async () => {
      const f = foundation();
      const chain = loadChain(f);
      const o = loadOntology(chain);
      const r = await ath(["--json", "ingest", join(SYN, b.file), "--received", "2026-10-16"], { cwd: f, env });
      expect(r.code, r.stderr).toBe(0);
      const rows = (r.json() as { data: { ingested: { blake3: string; mime: string }[] } }).data.ingested;
      expect(rows[0]!.blake3).toBe(b.blake3);
      expect(rows[0]!.mime).toBe("application/zip");
      expect(rows.length - 1).toBe(b.members);
      const a = await loadArtifact(chain, o, b.blake3);
      expect(a.root).toBe(b.root);
      expect((a.capturedFrom!.value as { origin: string; via: string; fields: unknown }).origin).toBe(b.origin); // the sidecar
      expect((a.capturedFrom!.value as { via: string }).via).toBe("export");
      const roots: Record<string, number> = {};
      for (const m of rows.slice(1)) {
        const ma = await loadArtifact(chain, o, m.blake3);
        roots[ma.root ?? "null"] = (roots[ma.root ?? "null"] ?? 0) + 1;
        expect((ma.capturedFrom!.value as { container: string }).container).toBe(`corpus://${b.blake3}`);
      }
      expect(roots).toEqual(b.roots);
      expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
    });
  }
});

/** Loose files a producer left a `.capture.yaml` beside (D-sidecar): the origin folds in; classification is by the bytes. */
describe("regression: loose documents with sidecars", () => {
  const docs: { file: string; blake3: string; root: string; origin: string }[] = [
    {
      file: "statement-2026-03.pdf",
      blake3: "409245363c6bf171d93a05a4c3df8b87145d2a6411e36f5c7c2676583b17f02d",
      root: "pdf",
      origin: "bank-statement",
    },
    {
      file: "tax-slip-2025.pdf",
      blake3: "9c7ac767810beee6fbb6c41dd874ed5915d70026c8c054ae42be7332d6ba0ae4",
      root: "pdf",
      origin: "tax-slip",
    },
    {
      file: "policy-schedule.pdf",
      blake3: "c662da40ef0466ef873181c07902d07583842c6fc930fe90d23821b6832d872f",
      root: "pdf",
      origin: "insurance-document",
    },
    {
      file: "account-confirmation.pdf",
      blake3: "7b2edf118bd04aca3b665e230b1a75ef9925130d30e249671b53390aa8b5efa5",
      root: "pdf",
      origin: "banking-document",
    },
    {
      file: "chart-printout.pdf",
      blake3: "24c1477b3562892536c1e39587659065673147397d3eae0f6a47eaa99ad441ec",
      root: "pdf",
      origin: "health-record",
    },
    {
      file: "design-export.pdf",
      blake3: "38cc78eb0aec488d7e71ab9ba19f08450ffea6ab4b44060f5574bebb31959790",
      root: "pdf",
      origin: "claude-export",
    },
    {
      file: "owner-statement.md",
      blake3: "6d4a69b2935ac22f1eb8e5b3236448a1a2e07bdc6ed51aa00cfc3b744ce430e8",
      root: "markdown",
      origin: "owner-statement",
    },
    {
      file: "contact-card.vcf",
      blake3: "75eee68fdbadde02da00b5004924dc771245aca6a4b864b0b257cf254d9844fe",
      root: "vcard",
      origin: "icloud-contacts-card",
    },
    {
      file: "sms-2026-03.ndjson",
      blake3: "2275613d697f25e2846499b364fa223facbbd568598fd6ce84223c9950e35e34",
      root: "ndjson",
      origin: "sms-backup",
    },
    {
      file: "location-history.json",
      blake3: "8c73633d06364efe3dd483cb1fceebccae53dbbbc43586ea3bc704827c1fada9",
      root: "json",
      origin: "google-timeline-export",
    },
  ];
  for (const d of docs) {
    test(`${d.file}: ${d.root} from ${d.origin}`, async () => {
      const f = foundation();
      const chain = loadChain(f);
      const o = loadOntology(chain);
      const r = await ath(["--json", "ingest", join(SYN, d.file), "--received", "2026-10-16"], { cwd: f, env });
      expect(r.code, r.stderr).toBe(0);
      expect((r.json() as { data: { ingested: { blake3: string }[] } }).data.ingested[0]!.blake3).toBe(d.blake3);
      const a = await loadArtifact(chain, o, d.blake3);
      expect(a.root).toBe(d.root);
      expect((a.capturedFrom!.value as { origin: string; fields: Record<string, unknown> }).origin).toBe(d.origin);
      expect(Object.keys((a.capturedFrom!.value as { fields: Record<string, unknown> }).fields).length).toBeGreaterThan(0);
      expect((await ath(["lint", d.blake3], { cwd: f, env })).code).toBe(0);
    });
  }
});

/** Generic page captures: four page kinds told by their markup, each a derived tree under its own root. */
describe("regression: generic page captures (html, derived trees — generated twins of the web captures)", () => {
  const pages: { file: string; blake3: string; root: string; scopes: number; remainder: string }[] = [
    {
      file: "harbour-article.html",
      blake3: "95460875093fd57a8d64913a45afd50b035ab53de34a2c1c988faa096e18c3b3",
      root: "article-page",
      scopes: 21,
      remainder: "11 of 3638",
    },
    {
      file: "rope-product.html",
      blake3: "d97e60d369370010642454bbb6abf2472697c76854e126db24c8a6529856ca95",
      root: "product-page",
      scopes: 18,
      remainder: "56 of 1594",
    },
    {
      file: "order-detail.html",
      blake3: "9515b279f0de5ca3bbfe81e028f1234be064db4c9a7d86b08774b85c0a27cc6f",
      root: "order-page",
      scopes: 15,
      remainder: "53 of 482",
    },
    {
      file: "cottage-listing.html",
      blake3: "7684234e970a2940ac15d0974c20cded566641eefa6c5bcd5dd2ac45b1e396cc",
      root: "listing-page",
      scopes: 22,
      remainder: "51 of 1261",
    },
  ];
  for (const p of pages) {
    test(`${p.file}: ${p.root}, ${p.scopes} scopes`, async () => {
      const f = foundation();
      const chain = loadChain(f);
      const o = loadOntology(chain);
      const ing = await ingestFile(chain, join(SYN, p.file), { date: "2026-10-16" });
      expect(ing.blake3).toBe(p.blake3);
      expect((ing.capturedFrom!.value as { via: string }).via).toBe("capture"); // the banner
      const a = await loadArtifact(chain, o, p.blake3);
      expect(a.root).toBe(p.root);
      expect(a.table.size).toBe(p.scopes);
      expect(a.table.unreachable()).toEqual([]);
      expect(a.table.find("heading")!.fields).toEqual({ level: 0 });
      expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
      expect((await ath(["export", "markdown", p.blake3], { cwd: f, env })).stdout).toContain(`remainder  ${p.remainder}`);
    });
  }
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
    expect(ing.blake3).toBe("2c694381523f325f5347167ce5e2a07bc3cb51ebfae3df46dc3d209145e9e9be");
    expect(ing.mime).toBe("message/rfc822");
    expect(ing.attests.value).toMatchObject({
      content_type: "multipart/mixed",
      date_iso: "2026-04-19T01:12:05Z",
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
    expect(ing.blake3).toBe("7ccea7956323b20d2874a1ec5a035263db53682c6d945ddd46307ecbf12a1587");
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
    expect(ing.blake3).toBe("43ccf072e23a9cf6b5d322262fd1649644795ffdcf51099b49941e0623dd6112");
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
