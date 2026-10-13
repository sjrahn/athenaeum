// model.line.test.ts — the claim line: validation per tree, identity keys, file order, canonical serialisation.
import { describe, expect, test } from "bun:test";
import { identityKey, sortLines, validateLine } from "../src/engine/model/line.ts";
import { canonicalLine, parseJsonl } from "../src/lib/jsonl.ts";

const at = "page=3&bbox=0.1192,0.6933,0.4851,0.019";
const L = {
  attests: { at: "whole", predicate: "attests", value: { mime: "application/pdf", bytes: 10 }, by: "ath.ingest@1" },
  pass: { at: "whole", predicate: "pass", value: { id: "p1", by: "a", verify: "b", ontology: "b3:0123456789abcdef", date: "2026-10-13" } },
  walked: { at: "whole", predicate: "walked", pass: "p1" },
  manifests: { at, predicate: "manifests", term: "heading", num: "5.", level: 1, pass: "p1" },
  in: { at, predicate: "in", value: { at: "whole", ord: 11 }, pass: "p1" },
  reads: { at, predicate: "reads_as", aspect: "text", rev: "b3:9f86d081884c7d65", body: "Baseline emissions", pass: "p1" },
};

describe("line", () => {
  test("validates each artifact predicate and refuses what the grammar does not know", () => {
    for (const l of Object.values(L)) expect(validateLine("corpus", l)).toBeNull();
    expect(validateLine("corpus", { at, predicate: "reads_as", aspect: "none", pass: "p1" })).not.toBeNull();
    expect(validateLine("corpus", { at, predicate: "structure", value: {}, pass: "p1" })).not.toBeNull();
    expect(validateLine("corpus", { ...L.in, by: "x@1" })).not.toBeNull();
    expect(validateLine("corpus", { at, predicate: "reads_as", aspect: "text", rev: "b3:short", body: "x", pass: "p1" })).not.toBeNull();
    expect(
      validateLine("owner", {
        at,
        predicate: "inspected",
        value: { rev: "b3:9f86d081884c7d65", diverges: "accepted", why: "2-D math" },
        by: "owner",
        date: "2026-10-12",
      }),
    ).toBeNull();
    expect(validateLine("ledger", { subject: "cdm-tool-03", predicate: "term", value: "methodological-tool" })).toBeNull();
    expect(validateLine("ledger", { subject: "Bad Slug", predicate: "term", value: "x" })).not.toBeNull();
    expect(validateLine("ledger", { subject: "s", predicate: "name", value: "x", by: "harvest:xenforo-thread@36c40a" })).toBeNull();
    expect(validateLine("ledger", { subject: "s", predicate: "name", value: "x", by: "claude-opus-4-8" })).not.toBeNull();
    expect(validateLine("ontology", { subject: "heading", predicate: "reads", value: "text" })).toBeNull();
  });

  test("identity keys collide where the contract says they do", () => {
    expect(identityKey("corpus", L.manifests)).toBe(`${at}|manifests|heading`);
    expect(identityKey("corpus", { ...L.manifests, num: "6." })).toBe(identityKey("corpus", L.manifests));
    expect(identityKey("corpus", { ...L.manifests, term: "paragraph" })).not.toBe(identityKey("corpus", L.manifests));
    expect(identityKey("corpus", L.in)).toBe(`${at}|in`);
    expect(identityKey("corpus", L.reads)).toBe(`${at}|reads_as|text`);
    expect(identityKey("corpus", { ...L.reads, body: "other", rev: "b3:0000000000000000" })).toBe(identityKey("corpus", L.reads));
    expect(identityKey("corpus", { ...L.manifests, at: "page=3&bbox=0.11920,0.69330,0.48510,0.01900" })).toBe(
      identityKey("corpus", L.manifests),
    );
    expect(identityKey("ledger", { subject: "s", predicate: "version", value: "03.0" })).toBe('s|version|v:"03.0"');
    expect(identityKey("ledger", { subject: "s", predicate: "cites", object: "o", qualifiers: { volume: 2 } })).toBe(
      's|cites|o:o|{"volume":2}',
    );
    expect(identityKey("ontology", { subject: "heading", predicate: "field", value: { name: "num", kind: "designator" } })).toBe(
      "heading|field|num",
    );
    expect(identityKey("ontology", { subject: "heading", predicate: "reads", value: "text" })).toBe("heading|reads");
    expect(identityKey("ontology", { subject: "x", predicate: "select", value: { selector: "h1", term: "heading" } })).toBe("x|select|h1");
  });

  test("file order is address, then predicate rank, then identity; serialisation is canonical", () => {
    const shuffled = [L.reads, L.walked, L.in, L.attests, L.manifests, L.pass];
    expect(sortLines("corpus", shuffled).map((l) => l.predicate)).toEqual(["attests", "pass", "walked", "manifests", "in", "reads_as"]);
    expect(canonicalLine({ pass: "p1", term: "heading", predicate: "manifests", at, num: "5." })).toBe(
      `{"at":"${at}","predicate":"manifests","term":"heading","num":"5.","pass":"p1"}`,
    );
    expect(canonicalLine({ body: "é", at: "whole", predicate: "x" })).toContain('"é"');
    expect(parseJsonl('{"a":1}\n\n{"b":2}\n').length).toBe(2);
    expect(() => parseJsonl("[1]")).toThrow("JSON object");
  });
});
