// export.test.ts — the markdown proxy (header, blocks in ord, render rules) and the N-Quads round trip.
import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { quadToLine, roundTrips, toNQuads } from "../src/engine/export/nquads.ts";
import { ath } from "./harness.ts";
import { foundation } from "./layers.ts";

const FIX = join(import.meta.dir, "fixtures");
const env = { ATH_ACTOR: "tester" };

describe("export", () => {
  test("markdown: header names the authority, pin and remainder; blocks carry their at in ord; heading renders", async () => {
    const f = foundation();
    const ing = await ath(["--json", "ingest", join(FIX, "small.html"), "--received", "2026-10-13"], { cwd: f, env });
    const id = (ing.json() as { data: { ingested: { blake3: string }[] } }).data.ingested[0]!.blake3;
    const r = await ath(["export", "markdown", id], { cwd: f, env });
    expect(r.code).toBe(0);
    const md = r.stdout;
    expect(md).toContain("authority  the bytes");
    expect(md).toMatch(/ontology {3}b3:[0-9a-f]{16}/);
    expect(md).toMatch(/remainder {2}\d+ of \d+ text characters/);
    expect(md).toContain("# Slip/berth — ✓ 𝑃𝐸");
    const blocks = [...md.matchAll(/<!-- (bytes=\d+,\d+) -->/g)].map((m) => m[1]);
    expect(blocks.length).toBe(6); // title, author, author-link, post-number, timestamp, body (the post itself has no reading)
    expect(md).toContain("héllo wörld\nline two");
  });

  test("nquads: every tree round-trips byte-for-byte", () => {
    const corpus = [
      { at: "whole", predicate: "attests", value: { mime: "text/csv", bytes: 1 }, by: "ath.ingest@1" },
      { at: "page=3&bbox=0.1192,0.6933,0.4851,0.019", predicate: "manifests", term: "heading", num: "5.", level: 1, pass: "p1" },
      {
        at: "page=3&bbox=0.1192,0.6933,0.4851,0.019",
        predicate: "reads_as",
        aspect: "text",
        rev: "b3:0123456789abcdef",
        body: 'Base "line"\nemissions',
        pass: "p1",
      },
    ];
    expect(roundTrips("corpus", "ab".repeat(32), corpus)).toBe(true);
    const ledger = [
      { subject: "cdm-tool-03", predicate: "term", value: "methodological-tool" },
      {
        subject: "cdm-tool-03",
        predicate: "version",
        value: "03.0",
        evidence: [
          {
            anchor: "corpus://x?page=1&text",
            quote: "Version 03.0",
            kind: "authoritative",
            mode: "stated",
            reading: "b3:0123456789abcdef",
          },
        ],
        pass: "p1",
      },
      { subject: "cdm-tool-03", predicate: "cites", object: "ipcc", qualifiers: { volume: 2 }, evidence: [], by: "harvest:x@abcdef" },
    ];
    expect(roundTrips("ledger", "cdm-tool-03", ledger)).toBe(true);
    const ontology = [{ subject: "heading", predicate: "field", value: { name: "num", kind: "designator", pattern: "^\\d+\\.$" } }];
    expect(roundTrips("ontology", "heading", ontology)).toBe(true);
    const q = toNQuads("ledger", "cdm-tool-03", ledger).split("\n")[1]!;
    expect(q).toContain("<pass://cdm-tool-03#p1>");
    expect(quadToLine(q).line.pass).toBe("p1");
    expect(() => quadToLine("garbage")).toThrow();
  });

  test("nquads over the CLI: one subject, then the public plane", async () => {
    const f = foundation();
    const ing = await ath(["--json", "ingest", join(FIX, "small.csv"), "--received", "2026-10-13"], { cwd: f, env });
    const id = (ing.json() as { data: { ingested: { blake3: string }[] } }).data.ingested[0]!.blake3;
    const one = await ath(["--json", "export", "nquads", id], { cwd: f, env });
    expect((one.json() as { data: { quads: number } }).data.quads).toBe(2);
    const all = await ath(["--json", "export", "nquads"], { cwd: f, env });
    expect((all.json() as { data: { quads: number } }).data.quads).toBeGreaterThan(200);
    const owner = await ath(["export", "nquads", "--plane", "owner"], { cwd: f, env });
    expect(owner.code).toBe(77);
  });
});
