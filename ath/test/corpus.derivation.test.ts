// corpus.derivation.test.ts — the ontology names the op (D-derivation): a term's `derivation` line is `<op>@<v>[ <arg>]`,
// looked up in the registry at resolve time; a scope's own terms name it before the root chain; the arg rides to the
// op (a delimiter, an attribute); an op the engine lacks is an ontology lint and a CONFIG error, never a silent husk;
// a root with no derivation has no surface and says so (D-roots).
import { describe, expect, test } from "bun:test";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { loadArtifact } from "../src/engine/corpus/derive.ts";
import { ingestFile } from "../src/engine/corpus/ingest.ts";
import { derivationAt, derivationFor, surfaceFor } from "../src/engine/corpus/resolve.ts";
import { loadChain } from "../src/engine/layer/config.ts";
import { parseOpRef } from "../src/engine/model/line.ts";
import { lintOntology } from "../src/engine/ontology/lint.ts";
import { loadOntology } from "../src/engine/ontology/load.ts";
import { opFor, opNames } from "../src/engine/ops/index.ts";
import { ath } from "./harness.ts";
import { foundation } from "./layers.ts";

const FIX = join(import.meta.dir, "fixtures");
const env = { ATH_ACTOR: "tester" };
const term = (dir: string, name: string, lines: Record<string, unknown>[]) =>
  writeFileSync(join(dir, "ontology", `${name}.claims.jsonl`), lines.map((l) => `${JSON.stringify({ subject: name, ...l })}\n`).join(""));

describe("the grammar and the registry", () => {
  test("<op>@<v>[ <arg>] parses; prose does not; the registry holds every op the regression ontology names", () => {
    expect(parseOpRef("html.attr@1 datetime")).toEqual({ op: "html.attr@1", arg: "datetime" });
    expect(parseOpRef("csv.parse@1")).toEqual({ op: "csv.parse@1" });
    expect(parseOpRef("csv.parse@1 (RFC 4180)")).toEqual({ op: "csv.parse@1", arg: "(RFC 4180)" }); // an arg is opaque to the grammar
    expect(parseOpRef("the datetime attribute")).toBeNull();
    expect(parseOpRef("html.text")).toBeNull();
    expect(opNames()).toEqual(["csv.parse@1", "eml.text@1", "html.attr@1", "html.text@1", "html.title@1", "pdf.words@1"]);
    expect(opFor("foo.bar@1")).toBeNull();
    const o = loadOntology(loadChain(foundation()));
    expect(lintOntology(o).filter((f) => f.code === "O10-derivation")).toEqual([]);
  });
});

describe("dispatch by name", () => {
  test("a scope's own terms name the op before the root chain; the arg reaches it; whole on markup is the text", async () => {
    const f = foundation();
    const chain = loadChain(f);
    const o = loadOntology(chain);
    const ing = await ingestFile(chain, join(FIX, "small.html"), { date: "2026-10-15" });
    const a = await loadArtifact(chain, o, ing.blake3);
    const ts = a.table.find("timestamp")!;
    expect(derivationFor(a, ts.at)).toMatchObject({ op: "html.attr@1", arg: "datetime", by: "timestamp", source: "html.attr@1 datetime" });
    expect(derivationAt(a, ts.at)).toEqual({ source: "html.attr@1 datetime", text: "2026-04-03T23:48:07Z" });
    const body = a.table.find("post-body")!;
    expect(derivationFor(a, body.at)).toMatchObject({ op: "html.text@1", by: "html" });
    expect(derivationAt(a, "whole")!.source).toBe("html.text@1");
    expect(derivationAt(a, "whole")!.text).toContain("héllo wörld");
    // the title is reached by name, as a binding names it
    expect(surfaceFor(a, "whole", { kind: "derived", op: "html.title@1" })!.text).toBe("Ünïcode · thread | Example Forum");
    // a binding naming an op the engine lacks is flagged (null), not fatal
    expect(surfaceFor(a, "whole", { kind: "derived", op: "foo.bar@1" })).toBeNull();
    const r = await ath(["--json", "resolve", `corpus://${ing.blake3}?${ts.at}`], { cwd: f, env });
    expect(r.code, r.stderr).toBe(0);
    expect((r.json() as { data: { source: string; text: string } }).data).toMatchObject({
      source: "html.attr@1 datetime",
      text: "2026-04-03T23:48:07Z",
    });
  });

  test("a dialect is an ontology edit: a term refining csv with `csv.parse@1 tab` parses the tab-separated bytes", async () => {
    const f = foundation();
    const chain = loadChain(f);
    const o = loadOntology(chain);
    const ing = await ingestFile(chain, join(FIX, "small.tsv"), { date: "2026-10-15" });
    expect(ing.mime).toBe("text/tab-separated-values");
    const a = await loadArtifact(chain, o, ing.blake3);
    expect(a.root).toBe("tsv");
    expect(derivationFor(a, "row=1")).toMatchObject({ op: "csv.parse@1", arg: "tab", by: "tsv" });
    expect(a.csv!.cols).toBeGreaterThan(1);
    expect(a.table.get("row=0")!.readings[0]).toMatchObject({ aspect: "cells", rev: "derived:csv.parse@1 tab" });
    expect(derivationAt(a, "row=1&col=0")!.source).toBe("csv.parse@1 tab");
    expect(derivationAt(a, "row=1&col=0")!.text).not.toContain("\t");
  });

  test("a root naming an op the engine lacks: O10 in ontology lint, CONFIG at resolve, named loudly", async () => {
    const f = foundation();
    term(f, "markdown", [
      { predicate: "refines", value: "document" },
      { predicate: "matches", value: { mime: "text/markdown" } },
      { predicate: "axes", value: ["bytes"] },
      { predicate: "derivation", value: "md.blocks@1" },
    ]);
    term(f, "prose", [
      { predicate: "refines", value: "document" },
      { predicate: "derivation", value: "blocks over the bytes" },
    ]);
    term(f, "ssv", [
      { predicate: "refines", value: "csv" },
      { predicate: "derivation", value: "csv.parse@1 (RFC 4180)" },
    ]);
    term(f, "bare-attr", [
      { predicate: "refines", value: "unit" },
      { predicate: "derivation", value: "html.attr@1" },
    ]);
    term(f, "argued-text", [
      { predicate: "refines", value: "unit" },
      { predicate: "derivation", value: "html.text@1 trimmed" },
    ]);
    const lint = await ath(["--json", "ontology", "lint"], { cwd: f, env });
    const findings = (lint.json() as { data: { findings: { term: string; code: string; msg: string }[] } }).data.findings;
    const o10 = findings.filter((x) => x.code === "O10-derivation");
    expect(o10.map((x) => x.term).sort()).toEqual(["argued-text", "bare-attr", "markdown", "prose", "ssv"]);
    expect(o10.find((x) => x.term === "markdown")!.msg).toContain("md.blocks@1, not an op of this engine (csv.parse@1");
    expect(o10.find((x) => x.term === "prose")!.msg).toContain("<op>@<v>[ <arg>]");
    expect(o10.find((x) => x.term === "ssv")!.msg).toContain("'tab' or one character, not '(RFC 4180)'");
    expect(o10.find((x) => x.term === "bare-attr")!.msg).toContain("needs the attribute name");
    expect(o10.find((x) => x.term === "argued-text")!.msg).toContain("takes no argument, got 'trimmed'");
    const ing = await ath(["--json", "ingest", join(FIX, "small.md"), "--origin", "fixtures", "--via", "upload"], { cwd: f, env });
    expect(ing.code, ing.stderr).toBe(0);
    const id = (ing.json() as { data: { ingested: { blake3: string }[] } }).data.ingested[0]!.blake3;
    const r = await ath(["resolve", `corpus://${id}?whole`], { cwd: f, env });
    expect(r.code).toBe(78);
    expect(r.stderr).toContain("markdown names md.blocks@1, not an op of this engine");
    const show = await ath(["ontology", "rules", "markdown"], { cwd: f, env });
    expect(show.stdout).toContain("derivation  md.blocks@1  (not an op of this engine)");
    // every reader of the artifact says the same thing; lint --all blocks the subject and goes on
    const tree = await ath(["tree", id], { cwd: f, env });
    expect(tree.code).toBe(78);
    expect(tree.stderr).toContain("markdown names md.blocks@1");
    const all = await ath(["--json", "lint", "--all"], { cwd: f, env });
    expect(all.code).toBe(1);
    const fs = (all.json() as { data: { findings: { code: string; subject: string; severity: string }[] } }).data.findings;
    expect(fs.filter((x) => x.code === "T-derivation")).toEqual([expect.objectContaining({ subject: id, severity: "block" })]);
  });

  test("a root with no derivation has no surface, quietly (D-roots)", async () => {
    const f = foundation();
    const ing = await ath(["--json", "ingest", join(FIX, "small.md"), "--origin", "fixtures", "--via", "upload"], { cwd: f, env });
    const id = (ing.json() as { data: { ingested: { blake3: string }[] } }).data.ingested[0]!.blake3;
    const r = await ath(["resolve", `corpus://${id}?whole`], { cwd: f, env });
    expect(r.code).toBe(66);
    expect(r.stderr).toContain("no derivation surface");
    expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
  });
});
