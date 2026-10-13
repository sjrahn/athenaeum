// corpus.derive.test.ts — derived trees: markup by select (scopes, placement, ord, attribute fields, designators from
// descendant scopes, html.text@1 readings, declared chrome) and tabular by shape (header, columns, records, cells);
// the positional and designated resolvers; the derivation surface.
import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { resolveQuery } from "../src/engine/corpus/addressing.ts";
import { derivedLines, loadArtifact } from "../src/engine/corpus/derive.ts";
import { ingestFile } from "../src/engine/corpus/ingest.ts";
import { derivationAt, surfaceFor } from "../src/engine/corpus/resolve.ts";
import { loadChain } from "../src/engine/layer/config.ts";
import { loadOntology } from "../src/engine/ontology/load.ts";
import { foundation, TESTDATA } from "./layers.ts";

const FIX = join(import.meta.dir, "fixtures");

describe("derived trees", () => {
  const f = foundation();
  const chain = loadChain(f);
  const o = loadOntology(chain);

  test("markup: select lines derive scopes, placement by containment, ord by document order, fields from attributes", async () => {
    const ing = await ingestFile(chain, join(FIX, "small.html"), { date: "2026-10-13" });
    const a = loadArtifact(chain, o, ing.blake3);
    expect(a.root).toBe("xenforo-thread");
    expect(a.tree).toBe("derived");
    expect(a.rootChain).toEqual(["xenforo-thread", "web-page", "html", "document", "unit"]);
    const title = a.table.find("thread-title")!;
    expect(title.readings[0]!.body).toBe("Idle/stall — ✓ 𝑃𝐸");
    expect(title.readings[0]!.rev).toBe("derived:html.text@1");
    const post = a.table.find("post")!;
    expect(post.parent).toBe("whole");
    expect(post.fields).toEqual({ id: "post-1", position: "#1" });
    const kids = a.table.children(post.at);
    expect(kids.map((k) => k.terms[0])).toEqual(["author", "author-link", "post-number", "timestamp", "post-body"]);
    expect(kids.map((k) => k.ord)).toEqual([0, 1, 2, 3, 4]);
    const link = a.table.find("author-link")!;
    expect(link.fields).toEqual({ user_id: "42" });
    expect(link.readings[0]!.body).toBe("alice");
    const ts = a.table.find("timestamp")!;
    expect(ts.fields).toEqual({ datetime: "2026-04-03T23:48:07Z" });
    expect(ts.readings[0]!.body).toBe("Apr 3, 2026");
    const body = a.table.find("post-body")!;
    expect(body.readings[0]!.body).toBe("héllo wörld\nline two");
    expect(a.table.unreachable()).toEqual([]);
    expect(a.table.walk().map((s) => s.terms[0])).toEqual([
      "xenforo-thread",
      "thread-title",
      "post",
      "author",
      "author-link",
      "post-number",
      "timestamp",
      "post-body",
    ]);
    // derived lines, as they would be written
    const lines = derivedLines(post);
    expect(lines).toEqual([
      { at: post.at, predicate: "in", value: { at: "whole", ord: 1 }, derived: "tree" },
      {
        at: post.at,
        predicate: "manifests",
        term: "post",
        id: "post-1",
        position: "#1",
        derived: "xenforo-thread.select article.message--post",
      },
    ]);
    // surfaces
    expect(derivationAt(a, post.at)!.text).toContain("alice");
    expect(surfaceFor(a, "whole", { kind: "derived", op: "html.attr@1", arg: "data-site" })).toBeNull();
    expect(surfaceFor(a, link.at, { kind: "derived", op: "html.attr@1", arg: "data-user-id" })!.text).toBe("42");
    expect(surfaceFor(a, "whole", { kind: "line", predicate: "captured_from", field: "uri" })!.text).toBe(
      "https://www.example.com/threads/test-thread.123/",
    );
    expect(surfaceFor(a, "whole", { kind: "derived", op: "html.title@1" })!.text).toBe("Ünïcode · thread | Example Forum");
    expect(surfaceFor(a, post.at, { kind: "line", predicate: "manifests", field: "id" })!.text).toBe("post-1");
  });

  test("tabular: the twin CSV classifies by header fingerprint; header, columns, records and cells derive", async () => {
    const ing = await ingestFile(chain, join(TESTDATA, "synthetic", "amazon-twin.csv"), { date: "2026-10-13" });
    const a = loadArtifact(chain, o, ing.blake3);
    expect(a.root).toBe("amazon-order-history");
    expect(a.tree).toBe("derived");
    expect(a.rootChain).toContain("csv");
    expect(a.table.get("row=0")!.terms).toEqual(["header"]);
    expect(a.table.get("row=0")!.parent).toBe("whole");
    expect(a.table.get("col=3")!.terms).toEqual(["currency-code"]);
    expect(a.table.get("col=3")!.fields).toEqual({ name: "Currency" });
    expect(a.table.get("col=0")!.fields).toEqual({ name: "ASIN", scheme: "asin" });
    const r1 = a.table.get("row=1")!;
    expect(r1.terms).toEqual(["record"]);
    expect(r1.ord).toBe(1);
    expect((r1.readings[0]!.body as string[])[10]).toBe("700-0000001-0000001");
    expect(a.table.walk().length).toBe(6); // whole + header + 4 records
    expect(a.table.unreachable().length).toBe(29); // the column axis
    expect(derivationAt(a, "row=1&col=10")!.text).toBe("700-0000001-0000001");
    expect(derivationAt(a, "row=2&col=25")!.text).toBe("'-2.00'");
    expect(resolveQuery(o, a.table, "col=Currency")).toBe("col=3");
    expect(resolveQuery(o, a.table, "0")).toBe("row=0");
    expect(resolveQuery(o, a.table, "2")).toBe("row=2");
    expect(() => resolveQuery(o, a.table, "col=Nope")).toThrow("nothing matches");
    expect(() => resolveQuery(o, a.table, "sec=5")).toThrow("no term declares");
  });

  test("markup: designated addresses by post number", async () => {
    const ing = await ingestFile(chain, join(FIX, "small.html"), { date: "2026-10-13" });
    const a = loadArtifact(chain, o, ing.blake3);
    expect(resolveQuery(o, a.table, "post=1")).toBe(a.table.find("post")!.at);
    expect(() => resolveQuery(o, a.table, "post=2")).toThrow("nothing matches");
    expect(resolveQuery(o, a.table, "1/0")).toBe(a.table.find("author")!.at);
  });
});
