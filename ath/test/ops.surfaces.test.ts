// ops.surfaces.test.ts — the surface ops (§10.5) and the hint ops (§10.6) over committed fixtures: what each yields at
// a span, the units a hint keeps with their own addresses, one parse per family, and the arguments an op refuses.
import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { hintAt, opProblem, Parses, surfaceAt } from "@ath/engine/formats/index.ts";
import { type JsonDoc, parseJson } from "@ath/engine/formats/json/json.ts";
import { parseMarkdown } from "@ath/engine/formats/markdown/markdown.ts";
import { bindRecogniser } from "@ath/engine/formats/media/hints.ts";
import { parseVcard } from "@ath/engine/formats/vcard/vcard.ts";
import { TESTDATA } from "./harness.ts";

const SYN = join(TESTDATA, "synthetic");
const read = async (f: string) => new Uint8Array(await Bun.file(join(SYN, f)).arrayBuffer());
const enc = (s: string) => new TextEncoder().encode(s);
const dec = (b: Uint8Array) => new TextDecoder().decode(b);

describe("surface ops", () => {
  test("json.text@1: the scalars inside a span in document order, strings unescaped; a value's span holds its quotes", async () => {
    const b = enc('{"a": "x\\ny", "n": [1, 2.5e3, true, null], "k": {"s": "\\u00e9"}}');
    const d = parseJson(b);
    const s = d.roots[0]!.children!.find((c) => c.key === "a")!.node;
    expect(dec(b.subarray(s.start, s.end))).toBe('"x\\ny"');
    expect(await surfaceAt(new Parses(b), "json.text@1", [{ whole: true }])).toBe("x\ny\n1\n2.5e3\ntrue\nnull\né");
    const k = d.roots[0]!.children!.find((c) => c.key === "k")!.node;
    expect(await surfaceAt(new Parses(b), "json.text@1", [{ bytes: [k.start, k.end] }])).toBe("é");
    const thread = await read("facebook-thread.json");
    const msg = parseJson(thread).roots[0]!.children!.find((c) => c.key === "messages")!.node.children![0]!.node;
    expect(await surfaceAt(new Parses(thread), "json.text@1", [{ bytes: [msg.start, msg.end] }])).toBe(
      "Eli Hale\n1774715268000\nGreen kettle map walked harbour bread while water carried.\nfalse",
    );
  });
  test("json.text@1 lines: one document per line; a union of regions joined by a newline", async () => {
    const b = enc('{"x": 1}\n{"x": "two"}\n');
    const d = parseJson(b, true);
    expect(d.roots).toHaveLength(2);
    const r = d.roots.map((n) => ({ bytes: [n.start, n.end] as const }));
    expect(await surfaceAt(new Parses(b), "json.text@1 lines", r)).toBe("1\ntwo");
    expect(() => parseJson(b)).toThrow();
  });
  test("yaml.text@1: as json.text@1 over the YAML parse; keys are not values", async () => {
    const b = await read("drive-folder.zip.capture.yaml");
    expect(await surfaceAt(new Parses(b), "yaml.text@1", [{ whole: true }])).toBe(
      "b3:da7b858a7acc71ea1953f162369503c564bce9e6ec59ad1b717c6864ccaf34f0\ngoogle-drive-export\n2026.03\n2026-03-18T16:00:00Z\nada.abbott@example.invalid\nHarbour plans\nexport\nthe folder, whole\n001",
    );
  });
  test("vcard.text@1: content lines unfolded, values unescaped, a structured value's components joined by a space", async () => {
    const b = enc(
      "BEGIN:VCARD\r\nVERSION:4.0\r\nN:Calder;Bo;;;\r\nNOTE:one\\, two\\nthree and a long\r\n  folded tail\r\nitem1.EMAIL;TYPE=work:bo@example.invalid\r\nEND:VCARD\r\n",
    );
    const d = parseVcard(b);
    expect(d.cards).toHaveLength(1);
    expect(d.lines.map((l) => [l.group ?? null, l.name, l.params])).toEqual([
      [null, "BEGIN", {}],
      [null, "VERSION", {}],
      [null, "N", {}],
      [null, "NOTE", {}],
      ["item1", "EMAIL", { TYPE: "work" }],
      [null, "END", {}],
    ]);
    const note = d.lines[3]!;
    expect(dec(b.subarray(note.start, note.end))).toBe("NOTE:one\\, two\\nthree and a long\r\n  folded tail");
    expect(await surfaceAt(new Parses(b), "vcard.text@1", [{ whole: true }])).toBe(
      "4.0\nCalder Bo\none, two\nthree and a long folded tail\nbo@example.invalid",
    );
  });
  test("markdown.text@1: blocks with their spans, markers removed, inline markup verbatim", async () => {
    const b = enc(
      "---\ntitle: x\n---\n# Heading *one*\n\nA paragraph\nover two lines.\n\n> quoted\n> more\n\n- first\n- second\n  continued\n\n```sh\nrun --it\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n***\nSetext\n===\n",
    );
    const d = parseMarkdown(b);
    expect(d.blocks.map((x) => [x.kind, x.level ?? null])).toEqual([
      ["front-matter", null],
      ["heading", 1],
      ["paragraph", null],
      ["quote", null],
      ["list", null],
      ["code", null],
      ["table", null],
      ["break", null],
      ["heading", 1],
    ]);
    expect(d.blocks[4]!.children!.map((i) => i.text)).toEqual(["first", "second\ncontinued"]);
    const h = d.blocks[1]!;
    expect(dec(b.subarray(h.start, h.end))).toBe("# Heading *one*");
    expect(await surfaceAt(new Parses(b), "markdown.text@1", [{ bytes: [h.start, d.blocks[3]!.end] }])).toBe(
      "Heading *one*\nA paragraph\nover two lines.\nquoted\nmore",
    );
  });
  test("text.text@1 and csv.parse@1; an op an instance names but the tool lacks, or an argument it refuses", async () => {
    expect(await surfaceAt(new Parses(enc("abc\ndef")), "text.text@1", [{ bytes: [4, 7] }])).toBe("def");
    const csv = await read("amazon-twin.csv");
    expect(await surfaceAt(new Parses(csv), "csv.parse@1", [{ row: 1, col: 0 }])).not.toBeNull();
    expect(opProblem("json.text@1 lines")).toBeNull();
    expect(opProblem("json.text@1 rows")).toContain("takes `lines`");
    expect(opProblem("text.text@1 x")).toContain("takes no argument");
    expect(opProblem("pdf.ocr@1")).toContain("not an op");
    expect(opProblem("not an op")).toContain("not an op reference");
    await expect(surfaceAt(new Parses(enc("x")), "html.text@1", [{ whole: true }])).rejects.toThrow("hint");
  });
  test("one parse per family per artifact", async () => {
    const p = new Parses(enc('{"a": 1}'));
    const a = await p.get({ name: "json.text@1", kind: "surface", family: "json", parse: (b) => parseJson(b) }, undefined);
    const b = await p.get({ name: "x.y@1", kind: "surface", family: "json", parse: (): JsonDoc => ({ roots: [] }) }, undefined);
    expect(b).toBe(a);
  });
});

describe("hint ops", () => {
  test("html.text@1: the text of the elements in a span; every run keeps the byte span of its source text", async () => {
    const b = await read("cottage-listing.html");
    const h = (await hintAt(new Parses(b), "html.text@1", [{ bytes: [800, 967] }]))!;
    expect(h.text).toBe("12 Quay Street, Port Ellen");
    for (const u of h.units) {
      const [a, z] = u.at.slice(6).split(",").map(Number) as [number, number];
      expect(dec(b.subarray(a, z)).replace(/\s+/g, " ").trim()).toBe(u.text);
    }
    const attr = await hintAt(new Parses(enc('<html lang="en"><img alt="A quay" src="x"></html>')), "html.attr@1 lang", [{ whole: true }]);
    expect(attr?.text).toBe("en");
  });
  test("pdf.words@1: words in a box banded into lines, each word at its own page and box", async () => {
    const b = await read("procedure.pdf");
    const h = (await hintAt(new Parses(b), "pdf.words@1", [{ page: 1, bbox: [0.1, 0.4, 0.8, 0.2] }]))!;
    expect(h.text).toBe("Calculation procedure\nProcedure to estimate heat loss from\ninsulated pipework over a reporting\nperiod");
    expect(h.units[0]).toEqual({ text: "Calculation", at: "page=1&bbox=0.144,0.4271,0.1579,0.0153" });
  });
  test("eml.text@1 and epub.text@1 at path&bytes: a part's span, decoded", async () => {
    const eml = await read("synthetic-message.eml");
    expect((await hintAt(new Parses(eml), "eml.text@1", [{ path: "1", bytes: [0, 27] }]))!.text).toBe("This is the reply-text body");
    const epub = await read("lantern-novel.epub");
    const ch = (await hintAt(new Parses(epub), "epub.text@1", [{ path: "text/titlepage.xhtml" }]))!;
    expect(ch.text.length).toBeGreaterThan(0);
    expect(ch.units.every((u) => u.at.startsWith("path=text/titlepage.xhtml&bytes="))).toBe(true);
  });
  test("media.subtitles@1: candidate regions t=a,b with an embedded track's text; audio.speech@1 through a bound recogniser", async () => {
    const mp4 = await read("subtitled.mp4");
    const h = (await hintAt(new Parses(mp4), "media.subtitles@1", [{ whole: true }]))!;
    expect(h.units).toEqual([
      { text: "High water at the quay", at: "t=0,0.8" },
      { text: "Berth A2 is free", at: "t=1,1.8" },
    ]);
    expect((await hintAt(new Parses(mp4), "media.subtitles@1", [{ t: [0.9, 2] }]))!.text).toBe("Berth A2 is free");
    expect(await hintAt(new Parses(mp4), "audio.speech@1", [{ whole: true }])).toBeNull();
    bindRecogniser(async () => [{ start: 0.25, end: 0.75, text: "ahoy" }]);
    try {
      expect((await hintAt(new Parses(mp4), "audio.speech@1", [{ whole: true }]))!.units).toEqual([{ text: "ahoy", at: "t=0.25,0.75" }]);
    } finally {
      bindRecogniser(null);
    }
  });
});
