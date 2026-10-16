// ops.test.ts — the byte-fact ops: sniff, csv.parse@1 with byte spans, html attest and the capture banner, image
// headers, the zip roster, pdf attest.
import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { csvSurface, parseCsv } from "../src/engine/ops/csv/parse.ts";
import { byteMap, parseHtml, select, spanOf } from "../src/engine/ops/html/dom.ts";
import { attest } from "../src/engine/ops/index.ts";
import { sniffMime } from "../src/engine/ops/sniff.ts";
import { TESTDATA } from "./layers.ts";

const FIX = join(import.meta.dir, "fixtures");
const PY = join(import.meta.dir, "fixtures");
const read = async (p: string) => new Uint8Array(await Bun.file(p).arrayBuffer());

describe("sniff", () => {
  test("magic first, then the name", async () => {
    expect(sniffMime(await read(join(PY, "born_text.pdf")))).toBe("application/pdf");
    expect(sniffMime(await read(join(PY, "sample.png")))).toBe("image/png");
    expect(sniffMime(await read(join(FIX, "small.zip")), "x.zip")).toBe("application/zip");
    expect(sniffMime(await read(join(FIX, "small.zip")), "x.epub")).toBe("application/zip"); // no OCF mimetype member: not an epub
    expect(sniffMime(await read(join(FIX, "small.epub")))).toBe("application/epub+zip");
    expect(sniffMime(await read(join(FIX, "small.mbox")))).toBe("application/mbox");
    expect(sniffMime(await read(join(TESTDATA, "synthetic", "synthetic-message.eml")))).toBe("message/rfc822");
    expect(sniffMime(await read(join(FIX, "small.vcf")))).toBe("text/vcard");
    expect(sniffMime(await read(join(FIX, "small.json")))).toBe("application/json");
    expect(sniffMime(await read(join(FIX, "small.ndjson")))).toBe("application/x-ndjson");
    expect(sniffMime(await read(join(FIX, "small.p21")))).toBe("application/p21");
    expect(sniffMime(await read(join(FIX, "small.md")), "small.md")).toBe("text/markdown");
    expect(sniffMime(await read(join(FIX, "small.tsv")), "small.tsv")).toBe("text/tab-separated-values");
    expect(sniffMime(await read(join(FIX, "small.gif")))).toBe("image/gif");
    expect(sniffMime(await read(join(FIX, "small.webp")))).toBe("image/webp");
    expect(sniffMime(await read(join(FIX, "small.svg")))).toBe("image/svg+xml");
    expect(sniffMime(await read(join(TESTDATA, "synthetic", "synthetic-audio.m4a")))).toBe("audio/mp4");
    expect(sniffMime(await read(join(TESTDATA, "synthetic", "synthetic-image.heic")))).toBe("image/heic");
    expect(sniffMime(await read(join(FIX, "small.html")))).toBe("text/html");
    expect(sniffMime(await read(join(FIX, "small.csv")), "small.csv")).toBe("text/csv");
    expect(sniffMime(new TextEncoder().encode("plain words"), "notes")).toBe("text/plain");
    expect(sniffMime(new Uint8Array([0, 1, 2, 3, 0, 0, 0, 9]), "blob")).toBe("application/octet-stream");
  });
});

describe("csv.parse@1", () => {
  test("BOM, CRLF, quoted newline, doubled quotes, empty cells, byte spans", async () => {
    const bytes = await read(join(FIX, "small.csv"));
    const p = parseCsv(bytes);
    expect(p.bom).toBe(true);
    expect(p.rows.length).toBe(4);
    expect(p.cols).toBe(3);
    expect(p.rows[0]!.cells.map((c) => c.value)).toEqual(["id", "name", "note"]);
    expect(p.rows[1]!.cells.map((c) => c.value)).toEqual(["1", "Smith, J", "multi\nline"]);
    expect(p.rows[2]!.cells.map((c) => c.value)).toEqual(["2", "OBrien", 'say "hi"']);
    expect(p.rows[3]!.cells.map((c) => c.value)).toEqual(["3", "", ""]);
    const raw = new TextDecoder().decode(bytes.subarray(p.rows[1]!.cells[1]!.start, p.rows[1]!.cells[1]!.end));
    expect(raw).toBe('"Smith, J"');
    expect(p.rows[0]!.start).toBe(3); // after the BOM
    expect(csvSurface(p, 2, 2)).toBe('say "hi"');
    expect(csvSurface(p, 1)).toBe("1\tSmith, J\tmulti\nline");
    expect(csvSurface(p, 9)).toBeNull();
  });
  test("attests rows (data), cols, header_row 0, bom", async () => {
    const a = await attest(await read(join(FIX, "small.csv")), "text/csv");
    expect(a.value).toEqual({ mime: "text/csv", bytes: 72, rows: 3, header_row: 0, cols: 3, encoding: "utf-8", bom: true });
  });
  test("a tab-separated file is the same parse with the tab as the delimiter", async () => {
    const p = parseCsv(await read(join(FIX, "small.tsv")), "\t");
    expect(p.rows.map((r) => r.cells.map((c) => c.value))).toEqual([
      ["id", "name"],
      ["1", "Ada"],
      ["2", "Bo"],
    ]);
    const a = await attest(await read(join(FIX, "small.tsv")), "text/tab-separated-values");
    expect(a.value).toMatchObject({ mime: "text/tab-separated-values", rows: 2, cols: 2 });
  });
});

describe("html", () => {
  test("byte map and spans on a multibyte document", async () => {
    const bytes = await read(join(FIX, "small.html"));
    const d = parseHtml(bytes);
    expect(d.map[d.text.length]).toBe(bytes.length);
    const h1 = select(d, "h1.p-title-value")[0]!;
    const s = spanOf(d, h1)!;
    expect(s.implied).toBe(false);
    expect(new TextDecoder().decode(bytes.subarray(s.start, s.end))).toBe('<h1 class="p-title-value">Idle/stall — ✓ 𝑃𝐸</h1>');
    const body = select(d, "div.bbWrapper")[0]!;
    const bs = spanOf(d, body)!;
    expect(new TextDecoder().decode(bytes.subarray(bs.start, bs.end))).toBe('<div class="bbWrapper">héllo <b>wörld</b><br>line two</div>');
    expect(byteMap("a𝑃b")).toEqual(new Uint32Array([0, 1, 5, 5, 6]));
  });
  test("attests title, generator from the XenForo root, and the capture banner as captured_from", async () => {
    const a = await attest(await read(join(FIX, "small.html")), "text/html");
    expect(a.value).toMatchObject({
      mime: "text/html",
      encoding: "utf-8",
      title: "Ünïcode · thread | Example Forum",
      generator: "XF (data-app public, data-version abc123)",
    });
    expect(a.capturedFrom).toEqual({
      origin: "example.com",
      uri: "https://www.example.com/threads/test-thread.123/",
      via: "capture",
      snapshot: "2026-06-07T14:03:19Z",
    });
  });
});

describe("image, zip, pdf", () => {
  test("png dims", async () => {
    const a = await attest(await read(join(PY, "sample.png")), "image/png");
    expect(a.value.mime).toBe("image/png");
    expect(typeof a.value.width).toBe("number");
    expect(typeof a.value.height).toBe("number");
  });
  test("zip roster lists files, not directories, each with its blake3", async () => {
    const a = await attest(await read(join(FIX, "small.zip")), "application/zip");
    const members = a.value.members as { path: string; bytes: number; blake3: string }[];
    expect(members.map((m) => m.path)).toEqual(["notes/readme.txt", "data/rows.csv"]);
    expect(members[0]!.bytes).toBe(13);
    expect(members[0]!.blake3).toMatch(/^[0-9a-f]{64}$/);
    expect(a.members?.length).toBe(2);
    expect(new TextDecoder().decode(a.members![0]!.bytes)).toBe("hello member\n");
  });
  test("pdf attests page count, version, size, info, sha256", async () => {
    const a = await attest(await read(join(PY, "born_text.pdf")), "application/pdf");
    expect(a.value).toMatchObject({ mime: "application/pdf", page_count: 2, page_size_pt: [612, 792] });
    expect(String(a.value.pdf_version)).toMatch(/^1\.\d$/);
    expect(String(a.value.sha256)).toMatch(/^[0-9a-f]{64}$/);
  });
});
