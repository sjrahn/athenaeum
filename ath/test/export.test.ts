// export.test.ts — export (§15) and serving (§16): the markdown proxy through `renders` templates, every block
// prefixed by its address, its header naming the authority, the passes, the chrome and the remainder; an unformed
// record's readings in address order; the graph projection and back, byte-identical, rulings never projected; a
// served instance read-only over HTTP, re-read per request; `invoke` refusing an admin verb and an unknown argument.
import { describe, expect, test } from "bun:test";
import { copyFileSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { buildRegistry } from "@ath/cli/main.ts";
import { entityQuads, judgmentsFromQuads, linesFromQuads, parseQuad, recordQuads, termQuads } from "@ath/engine/export/nquads.ts";
import { passOf } from "@ath/engine/pass/coverage.ts";
import { emitRecord, loadRecord } from "@ath/engine/record/document.ts";
import { canonicalLine } from "@ath/kit/canonical.ts";
import { invoke } from "@ath/kit/invoke.ts";
import { startServer } from "@ath/verbs/serve.ts";
import { ath, scratch, TESTDATA } from "./harness.ts";

const SYN = join(TESTDATA, "synthetic");
const RECORDS = join(import.meta.dir, "fixtures", "records");
const A = { ATH_ACTOR: "reader-a" };
const B = { ATH_ACTOR: "reader-b" };
const PROC = "5e6e497d934498fc49229ba8c594684114a1213426bc1ad0113718ae72794269";
const SIGN = "6aa934e58bc0dff94e8cb1281ccb0066ff98c9346baca2c72d8764cce6244471";
type R = { code: number; stdout: string; json: () => unknown };
const data = <D>(r: R) => (r.json() as { data: D }).data;

async function setup() {
  const root = join(scratch(), "reference");
  expect((await ath(["instance", "init", root], { env: A })).code).toBe(0);
  const owner = (argv: string[]) =>
    ath(argv, { env: { ATH_ACTOR: "owner" }, tty: true, cwd: root, confirm: async () => argv.slice(0, 2).join(" ") });
  for (const [t, ...ls] of [
    ["cover-page", { pred: "reads", val: "none" }],
    [
      "heading",
      { pred: "reads", val: "text" },
      { pred: "renders", val: { md: "{level+1} {num} {text}" } },
      { pred: "field", val: { name: "level", type: "int" } },
      { pred: "field", val: { name: "num", type: "designator", where: "leading" } },
    ],
    ["label", { pred: "reads", val: "text" }],
  ] as [string, ...object[]][])
    expect((await owner(["vocab", "add", "forms", t, ...ls.map((l) => JSON.stringify(l))])).code).toBe(0);
  const work = scratch();
  for (const f of ["procedure.pdf", "sign.jpg"]) copyFileSync(join(SYN, f), join(work, f));
  expect((await ath(["--root", root, "ingest", "procedure.pdf", "sign.jpg"], { env: A, cwd: work })).code).toBe(0);
  const run = (argv: string[], env = A) => ath(["--json", ...argv], { env, cwd: root });
  return { root, work, run, owner };
}

describe("the markdown proxy", () => {
  test("a formed record: each scope through its template, every block prefixed by its address, the header in full", async () => {
    const { root, work, run } = await setup();
    await run(["pass", "open", PROC.slice(0, 8)]);
    const f = join(work, "tree.yaml");
    writeFileSync(
      f,
      Bun.YAML.stringify({
        scopes: [
          {
            form: "cover-page",
            at: "page=1",
            scopes: [
              { form: "label", at: "page=1&bbox=0.1432,0.1007,0.2526,0.0081", text: "HARBOUR STANDARDS OFFICE" },
              {
                form: "heading",
                at: "page=1&bbox=0.1435,0.5031,0.6121,0.0975",
                level: 0,
                num: "1.",
                text: "Procedure to estimate heat loss from insulated pipework over a reporting period",
              },
            ],
          },
        ],
        attests: ["structure"],
      }),
    );
    await ath(["pass", "stage", PROC.slice(0, 8), "p1", "--file", f], { env: A, cwd: root });
    expect((await run(["pass", "sign", PROC.slice(0, 8), "p1"], B)).code).toBe(0);
    const md = data<{ markdown: string; provenance: { receipts: unknown[] } }>(await run(["export", "markdown", PROC.slice(0, 8)]));
    expect(md.markdown).toContain(`authority: ath://${PROC}`);
    expect(md.markdown).toMatch(/pass: p1 by reader-a, verified by reader-b, 2026-03-20, vocabulary b3:[0-9a-f]{16}, attests structure/);
    expect(md.markdown).toMatch(/remainder: \d+ hint units outside every reading and chrome/);
    expect(md.markdown).toContain(
      "<!-- at page=1 -->\n<!-- at page=1&bbox=0.1432,0.1007,0.2526,0.0081 -->\nHARBOUR STANDARDS OFFICE\n\n<!-- at page=1&bbox=0.1435,0.5031,0.6121,0.0975 -->\n# 1. Procedure to estimate heat loss",
    );
    expect(md.provenance.receipts).toHaveLength(1);
  });

  test("an unformed record exports its readings in address order, under no form", async () => {
    const { run } = await setup();
    await run(["pass", "open", SIGN.slice(0, 8)]);
    await run(["pass", "stage", SIGN.slice(0, 8), "p1", "--at", "bbox=0.0667,0.6976,0.6467,0.1071", "--text", "No parking 7am to 6pm"]);
    await run(["pass", "stage", SIGN.slice(0, 8), "p1", "--at", "bbox=0.0667,0.1786,0.6022,0.1548", "--text", "RETURNS ONLY"]);
    await run(["pass", "sign", SIGN.slice(0, 8), "p1"], B);
    const md = data<{ markdown: string }>(await run(["export", "markdown", SIGN.slice(0, 8)])).markdown;
    expect(md.slice(md.indexOf("---\n\n") + 5)).toBe(
      "<!-- at bbox=0.0667,0.1786,0.6022,0.1548 -->\nRETURNS ONLY\n\n<!-- at bbox=0.0667,0.6976,0.6467,0.1071 -->\nNo parking 7am to 6pm\n",
    );
  });
});

describe("the graph projection", () => {
  test("terms, entity lines and a record's judgments go out as N-Quads and come back byte-identical", () => {
    const entity = readFileSync(join(RECORDS, "formed.yaml"), "utf8");
    const lines = [
      { pred: "pass", val: { by: "a", date: "2026-01-01", id: "p1", verify: "b", vocab: "b3:0000000000000000" } },
      { pred: "is", val: "vessel", pass: "p1" },
      {
        pred: "length",
        val: "8.2",
        ev: [{ anchor: `ath://${"7".repeat(64)}?row=1&col=2`, binding: "derived:csv.parse@1", mode: "stated", quote: "8.2" }],
        pass: "p1",
      },
      { pred: "display-name", val: 'Lantern "the second"\nof Port Ellen', qual: { as: "LANTERN" }, pass: "p1" },
    ];
    const q = entityQuads("lantern", "0f4c2a8e-7b1d-4e5a-9c3f-6d2e8b1a4c70", lines).map((x) =>
      parseQuad(
        `<${x.s}> <${x.p}> ${"iri" in x.o ? `<${x.o.iri}>` : `"${x.o.literal.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n")}"^^<${x.o.datatype}>`} <${x.g}> .`,
      ),
    );
    expect(q.some((x) => x.p === "http://www.w3.org/1999/02/22-rdf-syntax-ns#type" && "iri" in x.o && x.o.iri === "ath://vessel")).toBe(
      true,
    );
    expect(linesFromQuads(q).map((x) => canonicalLine(x.line))).toEqual(lines.map((l) => canonicalLine(l)));
    const term = [
      { pred: "reads", val: "text" },
      { pred: "aligns", val: "http://schema.org/Text" },
    ];
    expect(linesFromQuads(termQuads("forms", "line", term)).map((x) => x.line)).toEqual(term);
    // a formed record's passes, scopes and readings
    const rec = loadRecord(entity);
    const back = judgmentsFromQuads(
      PROC,
      recordQuads(PROC, "x", rec, (w) => passOf(rec, w)),
    );
    const { passes: _p, scopes: _s, readings: _r, ...projection } = rec;
    expect(emitRecord({ ...projection, ...back })).toBe(entity);
    const read = loadRecord(readFileSync(join(RECORDS, "read.yaml"), "utf8"));
    const backRead = judgmentsFromQuads(
      "76".repeat(32),
      recordQuads("76".repeat(32), "x", read, (w) => passOf(read, w)),
    );
    expect(backRead.readings).toEqual(read.readings);
  });

  test("export graph projects the chain and never a ruling", async () => {
    const { run, owner } = await setup();
    expect((await owner(["rule", "seek", "--kind", "standard", "--why", "a private note"])).code).toBe(0);
    const g = data<{ nquads: string; statements: number }>(await run(["export", "graph"]));
    expect(g.statements).toBeGreaterThan(5);
    expect(g.nquads).toContain("<ath:form/heading> <ath:pred/renders>");
    expect(g.nquads).not.toContain("a private note");
    expect(g.nquads).not.toContain("seek");
  });
});

describe("serving", () => {
  test("read verbs over HTTP, read-only, re-read per request; invoke refuses an admin verb and an unknown argument", async () => {
    const { root, work, run } = await setup();
    const s = startServer({ registry: buildRegistry(), root, env: process.env, cwd: root, port: 0, hostname: "127.0.0.1" });
    try {
      const index = (await (await fetch(`${s.url}/`)).json()) as { verbs: { verb: string }[] };
      expect(index.verbs.map((v) => v.verb)).toContain("holdings");
      expect(index.verbs.map((v) => v.verb)).not.toContain("ingest");
      const h = await fetch(`${s.url}/v1/holdings`);
      expect(h.status).toBe(200);
      expect(((await h.json()) as { data: { records: unknown[] } }).data.records).toHaveLength(2);
      const rec = await fetch(`${s.url}/v1/record?subject=${PROC.slice(0, 8)}`);
      expect(((await rec.json()) as { data: { stage: string } }).data.stage).toBe("unread");
      expect((await fetch(`${s.url}/v1/ingest`)).status).toBe(400);
      expect((await fetch(`${s.url}/v1/holdings`, { method: "POST" })).status).toBe(405);
      expect((await fetch(`${s.url}/v1/record?subject=ffffffff`)).status).toBe(404);
      // the server holds no state: what is ingested after it starts is served at once
      copyFileSync(join(SYN, "cottage-listing.html"), join(work, "listing.html"));
      await ath(["--root", root, "ingest", "listing.html"], { env: A, cwd: work });
      expect(((await (await fetch(`${s.url}/v1/holdings`)).json()) as { data: { records: unknown[] } }).data.records).toHaveLength(3);
    } finally {
      s.stop();
    }
    const agent = { profile: "agent" as const, kind: "script" as const, session: null, basis: [], actor: "reader-a", tty: false };
    const adm = await invoke({
      registry: buildRegistry(),
      verb: "rule-seek",
      args: {},
      caller: agent,
      root,
      env: process.env,
      cwd: root,
      via: "over the socket",
    });
    expect(adm.exit).toBe(64); // hidden from an agent, as at the terminal
    const own = await invoke({
      registry: buildRegistry(),
      verb: "vocab-add",
      args: {},
      caller: { ...agent, profile: "owner" },
      root,
      env: process.env,
      cwd: root,
      via: "over the socket",
    });
    expect(own).toMatchObject({ exit: 77, envelope: { ok: false, error: { code: "DENIED" } } });
    const bad = await invoke({
      registry: buildRegistry(),
      verb: "holdings",
      args: { colour: "red" },
      caller: agent,
      root,
      env: process.env,
      cwd: root,
      via: "over the socket",
    });
    expect(bad).toMatchObject({ exit: 64, envelope: { error: { message: "unrecognized argument: colour" } } });
    const ok = await invoke({
      registry: buildRegistry(),
      verb: "record",
      args: { subject: PROC.slice(0, 8) },
      caller: agent,
      root,
      env: process.env,
      cwd: root,
      via: "over the socket",
    });
    expect(ok.exit).toBe(0);
    void run;
  });
});
