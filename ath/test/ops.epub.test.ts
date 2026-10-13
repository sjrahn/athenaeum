// ops.epub.test.ts — the EPUB (D-epub): the package document attested (Dublin Core, the spine as member paths),
// every member a subject, one route scope per spine item in reading order, a chapter classified by its package
// (matches by container) and derived through html.text@1, the publication harvested from the attestation.
import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { loadArtifact } from "../src/engine/corpus/derive.ts";
import { ingestFile } from "../src/engine/corpus/ingest.ts";
import { loadChain } from "../src/engine/layer/config.ts";
import { loadOntology } from "../src/engine/ontology/load.ts";
import { attestEpub, parseOpf } from "../src/engine/ops/epub/attest.ts";
import { readJsonl } from "../src/lib/jsonl.ts";
import { ath } from "./harness.ts";
import { foundation } from "./layers.ts";

const FIX = join(import.meta.dir, "fixtures");
const EPUB = join(FIX, "small.epub");
const env = { ATH_ACTOR: "tester" };
const read = async (p: string) => new Uint8Array(await Bun.file(p).arrayBuffer());

describe("epub attest", () => {
  test("the OPF: metadata, manifest hrefs resolved against the package path, the spine in order", () => {
    const opf = parseOpf(
      "a/b/c.opf",
      '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="u"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>T</dc:title><dc:identifier id="u">X</dc:identifier></metadata><manifest><item id="1" href="../x%20y.xhtml" media-type="application/xhtml+xml"/><item id="2" href="z.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="2"/><itemref idref="1"/></spine></package>',
    );
    expect(opf.title).toBe("T");
    expect(opf.identifier).toBe("X");
    expect(opf.spine).toEqual(["a/b/z.xhtml", "a/x y.xhtml"]);
  });

  test("the fixture attests Dublin Core, the ISBN, the spine and the roster", async () => {
    const a = await attestEpub(await read(EPUB), "application/epub+zip");
    expect(a.value).toMatchObject({
      title: "A Small Book",
      creator: "Ada Example",
      language: "en",
      identifier: "00000000-0000-4000-8000-00000000c0de",
      isbn: "9780000000002",
      publisher: "Athenaeum Press",
      opf: "OEBPS/content.opf",
      spine: ["OEBPS/text/toc.xhtml", "OEBPS/text/ch1.xhtml", "OEBPS/text/ch2.xhtml"],
    });
    expect(a.members!.length).toBe(7);
  });
});

describe("epub through the CLI", () => {
  test("members are subjects; the spine is the tree; a chapter is told by its package; the publication harvests", async () => {
    const f = foundation();
    const chain = loadChain(f);
    const o = loadOntology(chain);
    const ing = await ingestFile(chain, EPUB, { date: "2026-10-13", provenance: { origin: "fixtures", via: "upload" } });
    expect(ing.mime).toBe("application/epub+zip");
    expect(ing.members.map((m) => m.mime).sort()).toEqual([
      "application/xml",
      "application/xml",
      "text/css",
      "text/html",
      "text/html",
      "text/html",
      "text/plain",
    ]);
    const book = await loadArtifact(chain, o, ing.blake3);
    expect(book.root).toBe("epub");
    expect(book.tree).toBe("derived");
    expect(book.table.walk().map((s) => `${s.terms.join("+")}@${s.at}`)).toEqual([
      "epub@whole",
      "spine-item@path=OEBPS%2Ftext%2Ftoc.xhtml",
      "spine-item@path=OEBPS%2Ftext%2Fch1.xhtml",
      "spine-item@path=OEBPS%2Ftext%2Fch2.xhtml",
    ]);
    const ch1 = ing.members.find((m) => (m.capturedFrom!.value as { path: string }).path === "OEBPS/text/ch1.xhtml")!;
    const c = await loadArtifact(chain, o, ch1.blake3);
    expect(c.root).toBe("epub-chapter");
    expect(c.rootChain.slice(0, 3)).toEqual(["epub-chapter", "html", "document"]);
    const walk = c.table.walk();
    expect(walk.map((s) => s.terms.join("+"))).toEqual(["epub-chapter", "heading", "paragraph", "paragraph"]);
    expect(walk[1]!.fields).toEqual({ level: 0 });
    expect(walk[1]!.readings[0]).toMatchObject({ body: "Chapter One", rev: "derived:html.text@1" });
    expect(walk[3]!.readings[0]!.body).toBe("The clocks were striking thirteen — twice.");
    const h = await ath(["--json", "harvest", ing.blake3], { cwd: f, env });
    expect(h.code, h.stderr).toBe(0);
    expect((h.json() as { data: { concepts: number; claims: number } }).data).toMatchObject({ concepts: 1, claims: 5 });
    const slug = "publication-00000000-0000-4000-8000-00000000c0de";
    const lines = readJsonl(join(f, "ledger", `${slug}.claims.jsonl`));
    const title = lines.find((l) => l.predicate === "title")!;
    expect(title.value).toBe("A Small Book");
    expect((title.evidence as { reading: string; kind: string }[])[0]).toMatchObject({
      reading: "line:attests title",
      kind: "authoritative",
    });
    expect((lines.find((l) => l.predicate === "creator")!.evidence as { kind: string }[])[0]!.kind).toBe("direct");
    const v = await ath(["--json", "verify", slug], { cwd: f, env });
    const vd = (v.json() as { data: { counts: { bound: number; entries: number; flagged: number } } }).data;
    expect(vd.counts.flagged).toBe(0);
    expect(vd.counts.bound).toBe(vd.counts.entries);
    // a claim cited through the package route binds on the chapter's own scope
    const para = walk[2]!;
    const { writeFileSync } = await import("node:fs");
    writeFileSync(
      join(f, "ledger", "t.claims.jsonl"),
      [
        '{"subject":"t","predicate":"term","value":"concept"}',
        `{"subject":"t","predicate":"opens","value":"April","evidence":[{"anchor":"corpus://${ing.blake3}?path=OEBPS%2Ftext%2Fch1.xhtml;${para.at}&text","quote":"bright cold day in April","kind":"direct","mode":"stated","reading":"derived:html.text@1"}],"by":"ath.test@1"}`,
      ]
        .map((l) => `${l}\n`)
        .join(""),
    );
    const vt = await ath(["--json", "verify", "t"], { cwd: f, env });
    const claims = (vt.json() as { data: { claims: { bindings: { state: string; at: string }[] }[] } }).data.claims;
    expect(claims[0]!.bindings[0]).toMatchObject({ state: "bound", at: para.at });
    expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
    const at = await ath(["tree", "at", ing.blake3, "1"], { cwd: f, env });
    expect(at.stdout.trim()).toBe("path=OEBPS%2Ftext%2Fch1.xhtml  (spine-item)");
  });
});
