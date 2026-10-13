// ontology.test.ts — the regression ontology loads, chains, classifies, resolves effective rules, pins
// deterministically, and lints; an extension adds but never redefines.
import { describe, expect, test } from "bun:test";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { loadChain } from "../src/engine/layer/config.ts";
import { classOf, descendants, refinesChain } from "../src/engine/ontology/chain.ts";
import { effectiveRules } from "../src/engine/ontology/effective.ts";
import { checkFields } from "../src/engine/ontology/fields.ts";
import { harvestPin, ontologyPin, termPins } from "../src/engine/ontology/hash.ts";
import { lintOntology } from "../src/engine/ontology/lint.ts";
import { loadOntology } from "../src/engine/ontology/load.ts";
import { classify, matches } from "../src/engine/ontology/match.ts";
import { extension, foundation } from "./layers.ts";

describe("ontology", () => {
  const f = foundation();
  const o = loadOntology(loadChain(f));

  test("loads the 66 regression terms; chains and classes resolve", () => {
    expect(o.terms.size).toBe(69);
    expect(refinesChain(o, "methodological-tool")).toEqual(["methodological-tool", "regulation", "document", "unit"]);
    expect(refinesChain(o, "xenforo-thread")).toEqual(["xenforo-thread", "web-page", "html", "document", "unit"]);
    expect(classOf(o, "pdf")).toBe("document");
    expect(classOf(o, "amazon-order-history")).toBe("data");
    expect(classOf(o, "heading")).toBeNull();
    expect(refinesChain(o, "cover-page")).toEqual(["cover-page", "unit"]); // D-F2
    expect(descendants(o, "table")).toEqual(expect.arrayContaining(["table", "parameter-table", "revision-history"]));
  });

  test("effective rules: reads along the chain, fields, conventions inherited from ancestors", () => {
    const h = effectiveRules(o, ["heading"], [["document"]]);
    expect(h.reads).toBe("text");
    expect(h.fields.map((x) => x.name)).toEqual(["num", "level"]);
    expect(h.renders).toEqual({ md: "#{level+1} {num} {body}" });
    expect(h.conventions).toContain("sub/superscripts flattened outside math");
    const pt = effectiveRules(o, ["parameter-table"]);
    expect(pt.expects).toEqual(["caption", "row"]); // inherited from table
    expect(pt.reads).toBeNull();
    const mt = effectiveRules(o, ["methodological-tool"]);
    expect(mt.owes).toContain("entered_into_force");
    expect(mt.axes).toBeNull(); // pdf is the mime root, not the expression term
    const pdf = effectiveRules(o, ["pdf"]);
    expect(pdf.axes).toEqual(["page", "bbox"]);
    expect(pdf.derivation).toBe("pdf.words@1");
    expect(pdf.tree).toContain("asserted");
  });

  test("matches: most specific term wins; a header fingerprint beats the bare mime", () => {
    expect(classify(o, { mime: "application/pdf" })).toBe("pdf");
    expect(classify(o, { mime: "text/csv" })).toBe("csv");
    const header = ["ASIN", "Billing Address", "Carrier Name & Tracking Number", "Currency", "Department", "x"];
    expect(classify(o, { mime: "text/csv", header })).toBe("amazon-order-history");
    expect(matches(o, { mime: "text/csv", header }).map((m) => m.term)).toEqual(["amazon-order-history", "csv"]);
    expect(classify(o, { mime: "text/html", selectorMatches: (s) => s.startsWith("html#XF") })).toBe("xenforo-thread");
    expect(classify(o, { mime: "text/html", selectorMatches: () => false })).toBe("html");
    expect(classify(o, { mime: "image/jpeg" })).toBeNull();
  });

  test("fields: undeclared refused, derived never stored, kinds checked", () => {
    const heading = effectiveRules(o, ["heading"]).fields;
    expect(checkFields({ at: "x", predicate: "manifests", term: "heading", num: "5.", level: 1, pass: "p1" }, heading)).toEqual([]);
    expect(checkFields({ at: "x", predicate: "manifests", term: "heading", level: "one", pass: "p1" }, heading)[0]!.why).toContain(
      "not a int",
    );
    expect(checkFields({ at: "x", predicate: "manifests", term: "heading", scope: "h1", level: 1, pass: "p1" }, heading)[0]!.why).toContain(
      "undeclared",
    );
    expect(checkFields({ at: "x", predicate: "manifests", term: "heading", pass: "p1" }, heading)[0]!.why).toContain(
      "required field 'level'",
    );
    const page = effectiveRules(o, ["page"]).fields;
    expect(checkFields({ at: "page=1", predicate: "manifests", term: "page", number: 1, pass: "p1" }, page)[0]!.why).toContain(
      "never stored",
    );
  });

  test("the pin is deterministic and changes when a term changes; per-term pins", async () => {
    const pin = await ontologyPin(o);
    expect(pin).toMatch(/^b3:[0-9a-f]{16}$/);
    expect(await ontologyPin(loadOntology(loadChain(f)))).toBe(pin);
    expect(harvestPin(pin)).toHaveLength(6);
    const pins = await termPins(o);
    expect(pins.size).toBe(69);
    const f2 = foundation();
    writeFileSync(
      join(f2, "ontology", "heading.claims.jsonl"),
      '{"subject":"heading","predicate":"refines","value":"unit"}\n{"subject":"heading","predicate":"reads","value":"text"}\n',
    );
    const o2 = loadOntology(loadChain(f2));
    expect(await ontologyPin(o2)).not.toBe(pin);
    const pins2 = await termPins(o2);
    expect(pins2.get("heading")).not.toBe(pins.get("heading"));
    expect(pins2.get("paragraph")).toBe(pins.get("paragraph"));
  });

  test("lint: the regression ontology is clean; a concept map naming a selector is D-F7", () => {
    expect(lintOntology(o)).toEqual([]);
    const f2 = foundation();
    writeFileSync(
      join(f2, "ontology", "x.claims.jsonl"),
      '{"subject":"x","predicate":"refines","value":"unit"}\n{"subject":"x","predicate":"concept","value":{"term":"member","key":"a.username[data-user-id]","claims":{"title":".userTitle","name":"author"}}}\n',
    );
    const findings = lintOntology(loadOntology(loadChain(f2)));
    expect(findings.map((x) => x.code)).toEqual(["O7-concept-select", "O7-concept-select"]);
  });

  test("an extension adds terms and lines but may not redefine a foundation line", () => {
    const e = extension(f);
    writeFileSync(join(e, "ontology", "biography.claims.jsonl"), '{"subject":"biography","predicate":"refines","value":"paragraph"}\n');
    writeFileSync(
      join(e, "ontology", "heading.claims.jsonl"),
      '{"subject":"heading","predicate":"field","value":{"name":"anchor","kind":"string"}}\n',
    );
    const oe = loadOntology(loadChain(e));
    expect(oe.terms.size).toBe(70);
    expect(refinesChain(oe, "biography")).toEqual(["biography", "paragraph", "unit"]);
    expect(effectiveRules(oe, ["heading"]).fields.map((x) => x.name)).toEqual(["num", "level", "anchor"]);
    writeFileSync(join(e, "ontology", "heading.claims.jsonl"), '{"subject":"heading","predicate":"reads","value":"cells"}\n');
    expect(() => loadOntology(loadChain(e))).toThrow("never redefines");
  });
});
