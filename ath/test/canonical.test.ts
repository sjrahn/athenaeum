// canonical.test.ts — the forms everything hashes over: a line (§6.4.2), a revision (§6.5), a record's one YAML
// style and its grammar (§8.2.2), a vocabulary's pin (§11.8).
import { describe, expect, test } from "bun:test";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { emitRecord, loadRecord, plainOk } from "@ath/engine/record/document.ts";
import { emptyVocabulary, pin, pinText, serializeTerm, termIdentity } from "@ath/engine/vocab/terms.ts";
import { byCodePoint, canonicalJson, canonicalLine } from "@ath/kit/canonical.ts";
import { blake3Hex, short } from "@ath/kit/hash.ts";

const RECORDS = join(import.meta.dir, "fixtures", "records");

describe("a line (§6.4.2)", () => {
  test("id, pred, every other key in code-point order, ev, the authorship last; nested keys sorted; arrays kept", () => {
    const line = {
      pass: "p1",
      ev: [{ quote: "x", anchor: "ath://a", mode: "stated" }],
      val: { z: 1, a: [3, 1] },
      qual: { as: "X" },
      pred: "total",
      id: "r1",
    };
    expect(canonicalLine(line)).toBe(
      '{"id":"r1","pred":"total","qual":{"as":"X"},"val":{"a":[3,1],"z":1},"ev":[{"anchor":"ath://a","mode":"stated","quote":"x"}],"pass":"p1"}',
    );
    expect(canonicalLine({ by: "owner", date: "2026-01-20", pred: "seek", id: "r7", val: {} })).toBe(
      '{"id":"r7","pred":"seek","date":"2026-01-20","val":{},"by":"owner"}',
    );
  });
  test("non-ASCII unescaped, only quote, backslash and controls escaped; shortest numbers", () => {
    expect(canonicalLine({ pred: "p", val: 'é "q" \\ \n\t' })).toBe('{"pred":"p","val":"é \\"q\\" \\\\ \\n\\t"}');
    expect(canonicalLine({ pred: "p", val: [1.5, 0.1, 100, 1e21, -0] })).toBe('{"pred":"p","val":[1.5,0.1,100,1e+21,0]}');
  });
  test("code-point order, not UTF-16 order", () => {
    expect(["\u{1F600}", "￿"].sort(byCodePoint)).toEqual(["￿", "\u{1F600}"]);
    expect(canonicalJson({ "\u{1F600}": 1, "￿": 2 })).toBe('{"￿":2,"\u{1F600}":1}');
  });
});

describe("a revision (§6.5)", () => {
  test("b3: and 16 hex of the BLAKE3 of a string as UTF-8, or of cells as canonical JSON", async () => {
    expect(await short("Version 02.1")).toBe(`b3:${(await blake3Hex("Version 02.1")).slice(0, 16)}`);
    expect(await short(["Berth", "Vessel"])).toBe(`b3:${(await blake3Hex('["Berth","Vessel"]')).slice(0, 16)}`);
  });
});

describe("a record (§8.2)", () => {
  test("every golden record loads and is written back byte for byte", () => {
    const files = readdirSync(RECORDS);
    expect(files.length).toBe(4);
    for (const f of files) {
      const text = readFileSync(join(RECORDS, f), "utf8");
      expect(emitRecord(loadRecord(text, f)), f).toBe(text);
      expect(Bun.YAML.parse(emitRecord(loadRecord(text, f)))).toEqual(Bun.YAML.parse(text));
    }
  });
  test("keys in the record's order whatever order they were given; passes numerically; readings by address", () => {
    const out = emitRecord({
      passes: {
        p10: { date: "2026-01-02", vocab: "b3:0", verify: "b", by: "a" },
        p2: { by: "a", verify: "b", vocab: "b3:0", date: "2026-01-01", over: ["page=2", "page=1"] },
      },
      readings: {
        "page=2": { text: "two" },
        "page=1&bbox=0.5,0.1,0.1,0.1": { text: "b" },
        "page=1&bbox=0.1,0.1,0.1,0.1": { tex: "x^2", text: "a" },
      },
      receipts: [{ name: "a.pdf", received: "2026-01-01T00:00:00Z", actor: "r" }],
      intrinsics: { op: "pdf.intrinsics@1", mime: "application/pdf", bytes: 3 },
    });
    expect(out).toBe(
      [
        "intrinsics:",
        "  op: pdf.intrinsics@1",
        "  mime: application/pdf",
        "  bytes: 3",
        "receipts:",
        '  - {actor: r, received: "2026-01-01T00:00:00Z", name: a.pdf}',
        "passes:",
        '  p2: {by: a, verify: b, vocab: b3:0, date: "2026-01-01", over: [page=2, page=1]}',
        '  p10: {by: a, verify: b, vocab: b3:0, date: "2026-01-02"}',
        "readings:",
        "  page=1&bbox=0.1,0.1,0.1,0.1:",
        "    tex: x^2",
        "    text: a",
        "  page=1&bbox=0.5,0.1,0.1,0.1:",
        "    text: b",
        "  page=2:",
        "    text: two",
        "",
      ].join("\n"),
    );
  });
  test("a scope: form, at, fields in code-point order, its reading, its children; multi-line bodies as literal blocks", () => {
    const out = emitRecord({
      intrinsics: { mime: "application/pdf" },
      scopes: [
        {
          text: "Baseline\nemissions",
          num: "5.",
          level: 1,
          at: "page=3",
          form: "heading",
          scopes: [{ form: "row", at: "page=3&bbox=0,0,1,0.1", cells: ["a", "b, c"] }],
        },
      ],
    });
    expect(out).toBe(
      [
        "intrinsics:",
        "  mime: application/pdf",
        "scopes:",
        "  - form: heading",
        "    at: page=3",
        "    level: 1",
        '    num: "5."',
        "    text: |-",
        "      Baseline",
        "      emissions",
        "    scopes:",
        "      - form: row",
        "        at: page=3&bbox=0,0,1,0.1",
        '        cells: [a, "b, c"]',
        "",
      ].join("\n"),
    );
  });
  test("plain only where no YAML reader could read anything but the same string", () => {
    for (const v of ["Freehold", "RETURNS ONLY", "b3:5c1e", "https://x.example/a", "bytes=1,2"]) expect(plainOk(v, false), v).toBe(true);
    for (const v of [
      "2026-01-12",
      "4.2",
      "02.1",
      "yes",
      "No",
      "null",
      "~",
      "£313,000",
      "a: b",
      "a #b",
      "trailing ",
      "x:",
      "",
      "- x",
      "'q'",
    ])
      expect(plainOk(v, false), v).toBe(false);
    expect(plainOk("bytes=1,2", true)).toBe(false);
    const tricky = {
      intrinsics: { a: "2026-01-12", b: "on", c: " lead", d: "two\nlines", e: "Page # of #", f: "x\r\ny", g: 1.5, h: true, i: null },
    };
    expect(Bun.YAML.parse(emitRecord(tricky))).toEqual(tricky);
    const body = { intrinsics: {}, readings: { whole: { text: "  indented\nfirst" } } };
    expect(Bun.YAML.parse(emitRecord(body))).toEqual(body);
  });
  test("intrinsics is a block mapping; a list of mappings in it a block list; an empty one stays a mapping", () => {
    const out = emitRecord({
      intrinsics: { op: "zip.intrinsics@1", constituents: [{ path: "a b", blake3: "0f", kind: "asset" }], sizes: [[1, 2]] },
    });
    expect(out).toBe(
      'intrinsics:\n  op: zip.intrinsics@1\n  constituents:\n    - {path: a b, blake3: "0f", kind: asset}\n  sizes: [[1, 2]]\n',
    );
    expect(emitRecord({ intrinsics: {} })).toBe("intrinsics: {}\n");
    expect(emitRecord({ receipts: [{ actor: "a", received: "2026-01-01T00:00:00Z", name: "a.pdf" }] })).toBe(
      'receipts:\n  - {actor: a, received: "2026-01-01T00:00:00Z", name: a.pdf}\n',
    );
  });
  test("loading refuses what the grammar lacks", () => {
    const refuse = (t: string) => expect(() => loadRecord(t)).toThrow();
    refuse("intrinsics: {}\nsummary: no\n");
    refuse("intrinsics: {}\nreadings: {whole: {text: a}}\nscopes: []\n");
    refuse("intrinsics: {}\nreadings: {whole: {gist: a}}\n");
    refuse("intrinsics: {}\nreadings: {whole: {cells: [[a]]}}\n");
    refuse("intrinsics: {}\npasses: {q1: {by: a, verify: b, vocab: c, date: d}}\n");
    refuse("intrinsics: {}\npasses: {p1: {by: a, verify: b, vocab: c, date: d, with: x}}\n");
    refuse("intrinsics: {}\npasses: {p1: {by: a, verify: b, vocab: c, date: d, attests: [correct]}}\n");
    refuse("intrinsics: {}\nscopes: [{form: heading}]\n");
    refuse(": not yaml : [\n");
  });
});

describe("the pin (§11.8)", () => {
  test("term identity: single-valued by pred, named by name or col, every other repeatable by value", () => {
    expect(termIdentity({ pred: "reads", val: "text" })).toBe(termIdentity({ pred: "reads", val: "none" }));
    expect(termIdentity({ pred: "field", val: { name: "num", type: "string" } })).toBe(
      termIdentity({ pred: "field", val: { type: "int", name: "num" } }),
    );
    expect(termIdentity({ pred: "columns", val: { col: 1, form: "x" } })).not.toBe(
      termIdentity({ pred: "columns", val: { col: 2, form: "x" } }),
    );
    expect(termIdentity({ pred: "select", val: { a: 1, b: 2 } })).toBe(termIdentity({ pred: "select", val: { b: 2, a: 1 } }));
    expect(
      serializeTerm([
        { pred: "reads", val: "text" },
        { pred: "definition", val: "a" },
        { pred: "reads", val: "none" },
      ]),
    ).toBe('{"pred":"definition","val":"a"}\n{"pred":"reads","val":"none"}\n');
  });
  test("term files in path order, each preceded by its path; corpus and graph pinned apart", async () => {
    const v = emptyVocabulary();
    v.shapes.set("sheet", [{ pred: "matches", val: { mime: "text/csv" } }]);
    v.forms.set("row", [{ pred: "reads", val: "cells" }]);
    v.forms.set("heading", [
      { pred: "reads", val: "text" },
      { pred: "definition", val: "a title" },
    ]);
    v.kinds.set("vessel", [{ pred: "owes", val: ["length"] }]);
    expect(pinText(v, "corpus")).toBe(
      [
        "corpus/forms/heading.jsonl",
        '{"pred":"definition","val":"a title"}',
        '{"pred":"reads","val":"text"}',
        "corpus/forms/row.jsonl",
        '{"pred":"reads","val":"cells"}',
        "corpus/shapes/sheet.jsonl",
        '{"pred":"matches","val":{"mime":"text/csv"}}',
        "",
      ].join("\n"),
    );
    expect(pinText(v, "graph")).toBe('graph/kinds/vessel.jsonl\n{"pred":"owes","val":["length"]}\n');
    expect(await pin(v, "corpus")).toBe(await short(pinText(v, "corpus")));
    expect(await pin(v, "corpus")).toMatch(/^b3:[0-9a-f]{16}$/);
  });
});
