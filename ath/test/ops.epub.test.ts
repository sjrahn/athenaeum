// ops.epub.test.ts — the EPUB (D-epub): the package document attested (Dublin Core, the spine as member paths),
// every member a subject, one route scope per spine item in reading order, a chapter classified by its package
// (matches by container) and derived through html.text@1, the publication harvested from the attestation.
import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { parseOpf } from "@ath/engine/formats/epub/opf.ts";
import { intrinsicsOf } from "@ath/engine/formats/index.ts";

const FIX = join(import.meta.dir, "fixtures");
const EPUB = join(FIX, "small.epub");
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

  test("intrinsics: the Dublin Core, the ISBN, the package, the spine, and media as assets and the rest as parts", async () => {
    const a = await intrinsicsOf(await read(EPUB), "application/epub+zip");
    expect(a.value).toMatchObject({
      title: "A Small Book",
      creator: "Ada Example",
      language: "en",
      identifier: "00000000-0000-4000-8000-00000000c0de",
      isbn: "9780000000002",
      publisher: "Athenaeum Press",
      op: "epub.intrinsics@1",
      package: "OEBPS/content.opf",
      spine: ["OEBPS/text/toc.xhtml", "OEBPS/text/ch1.xhtml", "OEBPS/text/ch2.xhtml"],
    });
    expect(a.constituents.length).toBe(7);
    const kinds = Object.fromEntries(a.constituents.map((c) => [c.path, c.kind]));
    expect(Object.values(kinds).filter((k) => k === "asset").length).toBe(
      a.constituents.filter((c) => /^image|^audio|^video/.test(String(c.fields?.mime))).length,
    );
    expect(kinds["OEBPS/content.opf"]).toBe("part");
    expect(kinds.mimetype).toBe("part");
  });
});
