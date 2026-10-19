// vocab.test.ts — the selector languages (§10.7), the vocabulary check (§17.4), classification (§11.5), derived
// structure (§11.7) and chrome by declared rules (§8.4.6), over committed fixtures and small vocabularies built here.
import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { allPages } from "@ath/engine/formats/pdf/words.ts";
import { select, selectorProblem, selectParse } from "@ath/engine/select/select.ts";
import { chromeOf, deriveTree } from "@ath/engine/structure/derive.ts";
import { vocabularyCheck } from "@ath/engine/vocab/check.ts";
import { classify, type Probe } from "@ath/engine/vocab/classify.ts";
import { effectiveRules } from "@ath/engine/vocab/rules.ts";
import { emptyVocabulary, type Vocab, type Vocabulary } from "@ath/engine/vocab/terms.ts";
import { TESTDATA } from "./harness.ts";

const SYN = join(TESTDATA, "synthetic");
const read = async (f: string) => new Uint8Array(await Bun.file(join(SYN, f)).arrayBuffer());
const enc = (s: string) => new TextEncoder().encode(s);

function vocabulary(terms: Partial<Record<Vocab, Record<string, [string, unknown][]>>>): Vocabulary {
  const v = emptyVocabulary();
  for (const [k, ts] of Object.entries(terms))
    for (const [name, lines] of Object.entries(ts!))
      v[k as Vocab].set(
        name,
        lines.map(([pred, val]) => ({ pred, val })),
      );
  return v;
}
const check = (v: Vocabulary) =>
  vocabularyCheck({ vocab: v, holders: { forms: new Map(), shapes: new Map(), kinds: new Map(), properties: new Map() } }, "t");

describe("selector languages", () => {
  test("css for html; a JSON pointer with * for json; card or a property for vcard; a block kind for markdown", async () => {
    const html = selectParse(await read("cottage-listing.html"), "text/html")!;
    expect(select(html, "h1.listing-title").map((n) => n.text)).toEqual(["12 Quay Street, Port Ellen"]);
    const json = selectParse(enc('{"messages": [{"s": "a", "c": "x"}, {"s": "b"}]}'), "application/json")!;
    expect(select(json, "/messages/*/s").map((n) => n.text)).toEqual(["a", "b"]);
    expect(select(json, "/messages/*")[0]!.attr("c")).toBe("x");
    const vc = selectParse(await read("contact-card.vcf"), "text/vcard")!;
    expect(select(vc, "card")).toHaveLength(1);
    expect(select(vc, "FN").map((n) => n.text)).toEqual(["Bo Calder"]);
    const md = selectParse(enc("# A\n\npara\n\n## B\n"), "text/markdown")!;
    expect(select(md, "heading").map((n) => [n.text, n.level])).toEqual([
      ["A", 1],
      ["B", 2],
    ]);
  });
  test("a message: its header block, a part by type, line rules inside a decoded text/plain part", async () => {
    const m = selectParse(
      enc("Subject: hi\r\nFrom: a@b\r\n\r\nHello there.\r\n> quoted\r\n> more\r\n\r\n-- \r\nSig\r\n"),
      "message/rfc822",
    )!;
    expect(select(m, "header")[0]!.text).toBe("Subject: hi\r\nFrom: a@b");
    expect(select(m, { lines: "^>" }).map((n) => n.text)).toEqual(["> quoted\r\n> more"]);
    expect(select(m, { from: "^-- $" }).map((n) => n.text.trim())).toEqual(["-- \r\nSig"]);
    expect(select(m, { blank: true })).toHaveLength(2);
    const multi = selectParse(await read("synthetic-message.eml"), "message/rfc822")!;
    expect(select(multi, "part[type=image/*]").map((n) => n.at)).toEqual(["path=3"]);
  });
  test("a container's constituents by path pattern; each language refuses what it does not read", () => {
    const zip = selectParse(new Uint8Array(), "application/zip", [{ path: "a/one.csv" }, { path: "a/two.json" }, { path: "b.csv" }])!;
    expect(select(zip, "a/*.csv").map((n) => n.at)).toEqual(["path=a/one.csv"]);
    expect(selectorProblem("html", "div[")).toContain("CSS");
    expect(selectorProblem("json", "messages")).toContain("pointer");
    expect(selectorProblem("markdown", "section")).toContain("block kind");
    expect(selectorProblem("rfc822", { lines: "(" })).toContain("regular expression");
    expect(selectorProblem("rfc822", "part[type=text/plain]")).toBeNull();
  });
});

describe("the vocabulary check", () => {
  test("a clean vocabulary checks clean", () => {
    const v = vocabulary({
      forms: {
        heading: [
          ["reads", "text"],
          ["field", { name: "num", type: "designator", where: "leading", pattern: "^(\\d+)\\.$", address: "sec" }],
        ],
        paragraph: [
          ["reads", "text"],
          ["refines", "heading"],
        ],
      },
      shapes: {
        page: [
          ["matches", { mime: "text/html", selector: "h1" }],
          ["select", { selector: "h1", form: "heading" }],
        ],
      },
      kinds: { vessel: [["owes", ["length"]]] },
      properties: {
        length: [
          ["range", "decimal"],
          ["functional", true],
        ],
      },
    });
    expect(check(v)).toEqual([]);
  });
  test("refuses each thing §17.4 lists", () => {
    const v = vocabulary({
      forms: {
        pdf: [["reads", "text"]],
        row: [
          ["reads", "rows"],
          ["refines", "vessel"],
          ["convention", { quotes: "curly" }],
          ["field", { name: "n", type: "int", where: "aside" }],
          ["colour", "red"],
        ],
        loop: [["refines", "loop2"]],
        loop2: [["refines", "loop"]],
      },
      shapes: {
        bad: [
          ["matches", { selector: "/x" }],
          ["select", { selector: "div[", form: "row" }],
          ["surface", { form: "row", op: "pdf.words@1" }],
        ],
        site: [
          ["matches", { mime: "text/html", origin: { "source/uri": "x" } }],
          ["surface", { form: "row", op: "json.text@1 rows" }],
        ],
        page: [
          ["matches", { mime: "text/html" }],
          ["surface", { form: "row", op: "text.text@1" }],
        ],
      },
      kinds: { vessel: [["owes", ["length"]]] },
      properties: { size: [["range", "colour"]] },
    });
    const problems = check(v).map((f) => `${f.vocab}/${f.term}: ${f.problem}`);
    const has = (s: string) =>
      expect(
        problems.some((p) => p.includes(s)),
        `${s}\n${problems.join("\n")}`,
      ).toBe(true);
    has("forms/pdf: a form names structure, never a format");
    has("forms/row: reads: is one of text, cells, tex, none");
    has("forms/row: refines: 'vessel' is not a term of forms (it is another vocabulary's)");
    has("forms/row: convention");
    has("forms/row: field: `where` is leading, trailing, margin or a form");
    has("forms/row: `colour` is not a predicate of forms");
    has("forms/loop: refines in a cycle");
    has("shapes/bad: matches: has a `mime`");
    has("shapes/site: matches: origin: 'source/uri' is not a JSON pointer");
    has("shapes/site: surface: json.text@1 takes `lines` or nothing");
    has("shapes/page: surface: text.text@1 reaches text/html, a rendered format");
    has("kinds/vessel: owes: 'length' is not a property");
    has("properties/size: range: names a type, `artifact` or a kind");
    expect(
      vocabularyCheck(
        {
          vocab: vocabulary({ kinds: { harbour: [["owes", []]] } }),
          holders: { forms: new Map(), shapes: new Map(), kinds: new Map(), properties: new Map() },
        },
        "t",
        ["harbour"],
      )[0]!.problem,
    ).toContain("an entity and a kind share the name");
  });
  test("effective rules: a form's chain, inherited conventions, the shape's surface line", () => {
    const v = vocabulary({
      forms: {
        block: [
          ["reads", "text"],
          ["convention", { hyphens: "rejoin" }],
        ],
        message: [
          ["refines", "block"],
          ["field", { name: "sender", type: "string" }],
        ],
      },
      shapes: {
        thread: [
          ["matches", { mime: "application/json" }],
          ["surface", { form: "block", op: "json.text@1" }],
        ],
      },
    });
    const r = effectiveRules(v, "message", [{ bullets: "drop" }], "thread");
    expect(r.reads).toBe("text");
    expect(r.fields.map((f) => f.name)).toEqual(["sender"]);
    expect(r.conventions).toEqual([{ bullets: "drop" }, { hyphens: "rejoin" }]);
    expect(r.surface).toBe("json.text@1");
  });
});

describe("classification", () => {
  const probe = (o: Partial<Probe> & { mime: string }): Probe => ({
    intrinsics: {},
    origins: [],
    within: [],
    bytes: async () => null,
    shapeOf: async () => null,
    ...o,
  });
  test("every matches line holds; the most conditions win, then the longer chain, then the name; a stored shape overrides", async () => {
    const v = vocabulary({
      shapes: {
        export: [["matches", { mime: "application/zip" }]],
        "drive-export": [
          ["refines", "export"],
          ["matches", { mime: "application/zip", origin: { "/producer/tool": "google-drive-export" } }],
        ],
        "any-zip": [["matches", { mime: "application/zip" }]],
        nested: [["matches", { mime: "text/csv", path: "Harbour plans/*", container: "export" }]],
      },
    });
    const zip = probe({ mime: "application/zip", origins: [{ producer: { tool: "google-drive-export" } }] });
    expect(await classify(v, zip)).toEqual({ shape: "drive-export", by: "matches", matched: ["drive-export", "any-zip", "export"] });
    expect((await classify(v, probe({ mime: "application/zip" }))).shape).toBe("any-zip");
    expect((await classify(v, zip, "any-zip")).shape).toBe("any-zip");
    const csv = probe({
      mime: "text/csv",
      within: [{ container: "z", path: "Harbour plans/Berth list.csv" }],
      shapeOf: async () => "drive-export",
    });
    expect((await classify(v, csv)).shape).toBe("nested");
    expect(
      (
        await classify(
          v,
          probe({ mime: "text/csv", within: [{ container: "z", path: "elsewhere.csv" }], shapeOf: async () => "drive-export" }),
        )
      ).shape,
    ).toBeNull();
  });
  test("first_row, selector and magic read the bytes", async () => {
    const v = vocabulary({
      shapes: {
        sheet: [["matches", { mime: "text/csv", first_row: ["Berth", "Vessel"] }]],
        thread: [["matches", { mime: "application/json", selector: "/participants" }]],
        pdf17: [["matches", { mime: "application/pdf", magic: "%PDF-1.7" }]],
      },
    });
    expect(
      (await classify(v, probe({ mime: "text/csv", bytes: async () => enc("Berth,Vessel,Length (m)\nA1,Lantern,8.2\n") }))).shape,
    ).toBe("sheet");
    expect((await classify(v, probe({ mime: "application/json", bytes: async () => read("facebook-thread.json") }))).shape).toBe("thread");
    expect((await classify(v, probe({ mime: "application/pdf", bytes: async () => read("procedure.pdf") }))).shape).toBe("pdf17");
  });
});

describe("derived structure", () => {
  test("a thread: a scope per message, its fields filled, its reading the node the shape names", async () => {
    const v = vocabulary({
      forms: {
        message: [
          ["reads", "text"],
          ["field", { name: "sender", type: "string" }],
          ["field", { name: "sent", type: "datetime" }],
        ],
      },
      shapes: {
        thread: [
          ["matches", { mime: "application/json", selector: "/participants" }],
          ["select", { selector: "/messages/*", form: "message" }],
          ["select", { selector: "/messages/*/sender_name", form: "message", field: "sender" }],
          ["select", { selector: "/messages/*/timestamp_ms", form: "message", field: "sent" }],
          ["select", { selector: "/messages/*/content", form: "message", reads: "text" }],
        ],
      },
    });
    const b = await read("facebook-thread.json");
    const tree = deriveTree(v, "thread", "application/json", b, selectParse(b, "application/json"), {});
    expect(tree.length).toBeGreaterThan(3);
    const first = tree[0]!;
    expect(first).toMatchObject({
      form: "message",
      fields: { sender: "Eli Hale", sent: "1774715268000" },
      reads: { aspect: "text", text: "Green kettle map walked harbour bread while water carried." },
    });
    expect(first.at).toBe("bytes=160,356");
  });
  test("a sheet: the declared header row first, then every other row of the rows form; a column is never a scope", () => {
    const v = vocabulary({
      forms: { header: [["reads", "cells"]], row: [["reads", "cells"]] },
      shapes: {
        berths: [
          ["matches", { mime: "text/csv" }],
          ["columns", { header: 0, form: "header" }],
          ["columns", { rows: "row" }],
        ],
      },
    });
    const b = enc("Berth,Vessel\nA1,Lantern\nA2,Gull\n");
    expect(deriveTree(v, "berths", "text/csv", b, null, {}).map((s) => [s.form, s.at, s.text])).toEqual([
      ["header", "row=0", "Berth\tVessel"],
      ["row", "row=1", "A1\tLantern"],
      ["row", "row=2", "A2\tGull"],
    ]);
  });
  test("nesting by `in`, siblings in byte order, two forms on one node", () => {
    const v = vocabulary({
      forms: { section: [["reads", "none"]], heading: [["reads", "text"]], paragraph: [["reads", "text"]] },
      shapes: {
        doc: [
          ["matches", { mime: "text/html" }],
          ["select", { selector: "section", form: "section" }],
          ["select", { selector: "section > p", form: "paragraph", in: "section" }],
          ["select", { selector: "h2", form: "heading" }],
          ["select", { selector: "h2", form: "section" }],
        ],
      },
    });
    const b = enc("<html><body><section><h2>A</h2><p>one</p><p>two</p></section><section><p>three</p></section></body></html>");
    const t = deriveTree(v, "doc", "text/html", b, selectParse(b, "text/html"), {});
    expect(t.map((s) => [s.form, s.scopes.map((c) => c.text)])).toEqual([
      ["section", ["one", "two"]],
      [["heading", "section"], []],
      ["section", ["three"]],
    ]);
  });
  test("chrome by a repetition rule over a PDF's lines, with its role by pattern; by a selector over markup", async () => {
    const pages = await allPages(await read("procedure.pdf"));
    const runs = chromeOf(
      [{ repeats: { pages: 8, share: 1 }, mask: "digits", box: 2, roles: { "page-number": "Page # of #" } }],
      null,
      pages,
    );
    expect(runs.length).toBe(16);
    expect(runs.filter((r) => r.role === "page-number").map((r) => r.text)).toEqual(
      [1, 2, 3, 4, 5, 6, 7, 8].map((n) => `Version 02.1 Page ${n} of 8`),
    );
    expect(runs.filter((r) => r.role === "running-header")).toHaveLength(8);
    const b = await read("cottage-listing.html");
    expect(chromeOf([{ selector: ".site-footer" }], selectParse(b, "text/html"), null).length).toBe(1);
    expect(chromeOf([{ repeats: { pages: 9, share: 1 }, mask: "digits", box: 2 }], null, pages)).toEqual([]);
  });
});
