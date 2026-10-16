#!/usr/bin/env bun
// novel.ts — the twin of the novel: an EPUB 2 package in calibre's layout (mimetype stored first, container.xml,
// content.opf with Dublin Core and a scheme=ISBN identifier, toc.ncx, a stylesheet, a title page, 24 chapters as
// text/partNNNN.html with h1, p and the odd blockquote, 22 small images) — 52 members, 25 spine items. One long
// chapter carries several hundred paragraphs, as the real one does. Fictional book, generated prose.
//
//   bun testdata/synthetic/gen/novel.ts
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { png } from "./lib/png.ts";
import { int, lcg, paragraph, sentence } from "./lib/rand.ts";
import { zip, type ZipEntry } from "./lib/zip.ts";

const OUT = join(dirname(Bun.fileURLToPath(import.meta.url)), "..", "lantern-novel.epub");
const r = lcg(9);
const TITLE = "The Lantern Room";
const AUTHOR = "Ida Thorn";
const UUID = "3b2a1c40-7e5d-4f1a-9c0e-00000000c0de";
const ISBN = "9780000000019";
const e = (s: string) => new TextEncoder().encode(s);

const chapterCount = 24;
const chapters = Array.from({ length: chapterCount }, (_, i) => {
  const n = i === 4 ? 600 : int(r, 18, 48); // part0005 is the long one
  const paras: string[] = [];
  for (let k = 0; k < n; k++) paras.push(paragraph(r));
  const quotes = i === 4 ? 6 : r() < 0.3 ? 1 : 0;
  return { title: i === 0 ? "One" : `${sentence(r).replace(/[.?]$/, "").split(" ").slice(0, 3).join(" ")}`, paras, quotes };
});

const xhtml = (title: string, body: string) =>
  `<?xml version='1.0' encoding='utf-8'?>\n<html xmlns="http://www.w3.org/1999/xhtml"><head><title>${title}</title><link href="../stylesheet.css" rel="stylesheet" type="text/css"/></head><body class="calibre">${body}</body></html>\n`;

const entries: ZipEntry[] = [{ path: "mimetype", bytes: e("application/epub+zip"), method: 0 }];
entries.push({
  path: "META-INF/container.xml",
  bytes: e(
    `<?xml version="1.0"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>\n`,
  ),
});
const manifest: string[] = [];
const spine: string[] = [];
const nav: string[] = [];
manifest.push(`<item href="stylesheet.css" id="css" media-type="text/css"/>`, `<item href="toc.ncx" id="ncx" media-type="application/x-dtbncx+xml"/>`);
manifest.push(`<item href="text/titlepage.xhtml" id="titlepage" media-type="application/xhtml+xml"/>`);
spine.push(`<itemref idref="titlepage"/>`);
nav.push(`<navPoint id="np-title" playOrder="1"><navLabel><text>${TITLE}</text></navLabel><content src="text/titlepage.xhtml"/></navPoint>`);
entries.push({ path: "stylesheet.css", bytes: e(".calibre{display:block;font-size:1em;margin:0 5pt}.calibre1{display:block;margin:1em 0}h1{font-size:1.5em;margin:2em 0 1em}blockquote{margin:1em 2em}\n") });
entries.push({
  path: "text/titlepage.xhtml",
  bytes: e(xhtml(TITLE, `<div><img src="../images/cover.jpeg" alt="cover"/></div><h1>${TITLE}</h1><p class="calibre1">${AUTHOR}</p>`)),
});
const images: string[] = ["images/cover.jpeg"];
for (let i = 1; i <= 21; i++) images.push(`images/${String(i).padStart(5, "0")}.jpeg`);
images.forEach((p, i) => {
  // a 16×16 raster per image (PNG bytes under a .jpeg name, as calibre-converted books often carry; mime by sniff)
  entries.push({ path: p, bytes: png(16, 16, (x, y) => [(x * 16 + i * 9) & 255, (y * 16 + i * 5) & 255, (i * 37) & 255]), method: 0 });
  manifest.push(`<item href="${p}" id="img${i}" media-type="image/png"/>`);
});
chapters.forEach((c, i) => {
  const id = `part${String(i + 1).padStart(4, "0")}`;
  const body = [`<h1 class="calibre2">${c.title}</h1>`];
  c.paras.forEach((p, k) => {
    if (k > 0 && k % 8 === 0 && c.quotes > 0 && body.filter((b) => b.startsWith("<blockquote")).length < c.quotes)
      body.push(`<blockquote class="calibre3"><p class="calibre1">${sentence(r)}</p></blockquote>`);
    if (i === 4 && k % 90 === 1) body.push(`<div><img src="../images/${String(1 + (k % 21)).padStart(5, "0")}.jpeg" alt=""/></div>`);
    body.push(`<p class="calibre1">${p}</p>`);
  });
  entries.push({ path: `text/${id}.html`, bytes: e(xhtml(c.title, body.join("\n"))) });
  manifest.push(`<item href="text/${id}.html" id="${id}" media-type="application/xhtml+xml"/>`);
  spine.push(`<itemref idref="${id}"/>`);
  nav.push(`<navPoint id="np-${id}" playOrder="${i + 2}"><navLabel><text>${c.title}</text></navLabel><content src="text/${id}.html"/></navPoint>`);
});
entries.push({
  path: "toc.ncx",
  bytes: e(
    `<?xml version='1.0' encoding='utf-8'?>\n<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head><meta content="${UUID}" name="dtb:uid"/><meta content="2" name="dtb:depth"/></head><docTitle><text>${TITLE}</text></docTitle><navMap>${nav.join("")}</navMap></ncx>\n`,
  ),
});
entries.push({
  path: "content.opf",
  bytes: e(
    `<?xml version='1.0' encoding='utf-8'?>\n<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uuid_id" version="2.0" prefix="calibre: https://calibre-ebook.com">\n  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">\n    <dc:title>${TITLE}</dc:title>\n    <dc:creator opf:file-as="Thorn, Ida" opf:role="aut">${AUTHOR}</dc:creator>\n    <dc:date>2024-05-14T00:00:00+00:00</dc:date>\n    <dc:rights>Copyright © 2024 by ${AUTHOR}</dc:rights>\n    <dc:publisher>Athenaeum Press</dc:publisher>\n    <dc:identifier id="uuid_id" opf:scheme="uuid">${UUID}</dc:identifier>\n    <dc:contributor opf:role="bkp">calibre (7.0.0) [https://calibre-ebook.com]</dc:contributor>\n    <dc:language>en</dc:language>\n    <dc:identifier opf:scheme="ISBN">${ISBN}</dc:identifier>\n    <meta name="calibre:title_sort" content="Lantern Room, The"/>\n    <meta name="cover" content="img0"/>\n  </metadata>\n  <manifest>\n    ${manifest.join("\n    ")}\n  </manifest>\n  <spine toc="ncx">\n    ${spine.join("\n    ")}\n  </spine>\n  <guide><reference href="text/titlepage.xhtml" title="Title page" type="cover"/></guide>\n</package>\n`,
  ),
});
const bytes = zip(entries);
writeFileSync(OUT, bytes);
console.log(`wrote ${OUT} (${bytes.length} bytes, ${entries.length} members, ${spine.length} spine items)`);
