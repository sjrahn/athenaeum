// corpus.pass.test.ts — the asserted tree through the CLI on a fixture PDF: open a pass, stage lines (revs stamped),
// sign (lints gate), L7 agrees; a divergent reading is listed, the owner accepts it, revokes it; a second append at
// an existing identity is a correction with a lineage row; walked + G3; staleness after a term edit; tree at sec=1;
// the export renders the heading.
import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { allPages, wordsInBox, wordsText } from "../src/engine/ops/pdf/words.ts";
import { bodyRev } from "../src/lib/hash.ts";
import { readJsonl } from "../src/lib/jsonl.ts";
import { ath } from "./harness.ts";
import { foundation } from "./layers.ts";

const PDF = join(import.meta.dir, "fixtures/geometry_pages.pdf");
const env = { ATH_ACTOR: "tester" };

async function lineBox(pageIndex: number, startsWith: string): Promise<{ at: string; text: string }> {
  const pages = await allPages(new Uint8Array(await Bun.file(PDF).arrayBuffer()));
  const p = pages[pageIndex]!;
  const l = p.lines.find((x) => x.text.startsWith(startsWith))!;
  const box: [number, number, number, number] = [l.x0, l.y, Math.round((l.x1 - l.x0) * 1e4) / 1e4, l.h];
  return { at: `page=${p.page}&bbox=${box.join(",")}`, text: wordsText(wordsInBox(p.words, box)) };
}

describe("passes on an asserted tree", () => {
  test("open → append → sign → inspect → accept → correct → walked → stale", async () => {
    const f = foundation();
    const ing = await ath(["--json", "ingest", PDF, "--received", "2026-10-13"], { cwd: f, env });
    const id = (ing.json() as { data: { ingested: { blake3: string }[] } }).data.ingested[0]!.blake3;
    const same = await ath(["pass", "open", id, "--by", "a", "--verify", "a"], { cwd: f, env });
    expect(same.code).toBe(73);
    const open = await ath(
      ["--json", "--now", "2026-10-13T00:00:00Z", "pass", "open", id, "--by", "claude-opus", "--verify", "claude-sonnet"],
      { cwd: f, env },
    );
    expect(open.code).toBe(0);
    expect((open.json() as { data: { id: string } }).data.id).toBe("p1");
    const h = await lineBox(0, "1. Introduction");
    const b = await lineBox(0, "Body text on page one");
    const lines = [
      { at: "page=1", predicate: "manifests", term: "page" },
      { at: "page=1", predicate: "manifests", term: "cover-page" },
      { at: "page=1", predicate: "in", value: { at: "whole", ord: 0 } },
      { at: h.at, predicate: "manifests", term: "heading", num: "1.", level: 1 },
      { at: h.at, predicate: "in", value: { at: "page=1", ord: 0 } },
      { at: h.at, predicate: "reads_as", aspect: "text", body: "Introduction" },
      { at: b.at, predicate: "manifests", term: "paragraph" },
      { at: b.at, predicate: "in", value: { at: h.at, ord: 0 } },
      { at: b.at, predicate: "reads_as", aspect: "text", body: "Body text on page one only." },
    ];
    const file = join(f, "p1.jsonl");
    writeFileSync(file, lines.map((l) => `${JSON.stringify(l)}\n`).join(""));
    const app = await ath(["--json", "claims", "append", id, "--pass", "p1", "--from", file], { cwd: f, env });
    expect(app.code).toBe(0);
    expect((app.json() as { data: { staged: number } }).data.staged).toBe(9);
    // a wrong rev is refused
    writeFileSync(file, `${JSON.stringify({ at: b.at, predicate: "reads_as", aspect: "text", rev: "b3:0000000000000000", body: "x" })}\n`);
    expect((await ath(["claims", "append", id, "--pass", "p1", "--from", file], { cwd: f, env })).code).toBe(73);
    // an op line is refused
    writeFileSync(file, `${JSON.stringify({ at: "whole", predicate: "attests", value: {}, by: "x@1" })}\n`);
    expect((await ath(["claims", "append", id, "--pass", "p1", "--from", file], { cwd: f, env })).code).toBe(73);
    const list = await ath(["pass", "list", id], { cwd: f, env });
    expect(list.stdout).toContain("open   p1");
    expect(list.stdout).toContain("9 staged lines");
    // sign: G3 lists the uncovered words (pages 2 and 3), not blocking without walked
    const sign = await ath(["--json", "pass", "sign", id, "p1"], { cwd: f, env });
    expect(sign.code).toBe(0);
    const sd = (sign.json() as { data: { signed: boolean; added: number; findings: { code: string; severity: string }[] } }).data;
    expect(sd.signed).toBe(true);
    expect(sd.added).toBe(10); // 9 + the pass line
    expect(sd.findings.filter((x) => x.code === "G3")[0]!.severity).toBe("list");
    expect(existsSync(join(f, ".ath", "passes", id, "p1.jsonl"))).toBe(false);
    const stored = readJsonl(join(f, "corpus", `${id}.claims.jsonl`));
    expect(stored.map((l) => l.predicate)).toEqual([
      "attests",
      "captured_from",
      "pass",
      "manifests",
      "manifests",
      "in",
      "manifests",
      "in",
      "reads_as",
      "manifests",
      "in",
      "reads_as",
    ]);
    const reading = stored.find((l) => l.predicate === "reads_as" && l.at === b.at)!;
    expect(reading.rev).toBe(await bodyRev("Body text on page one only."));
    expect(reading.pass).toBe("p1");
    // L7: both readings agree with pdf.words (the heading's designator "1." is stripped from the derivation)
    const insp = await ath(["--json", "inspect", id, "--all"], { cwd: f, env });
    expect(insp.code).toBe(0);
    expect((insp.json() as { data: { counts: Record<string, number> } }).data.counts).toEqual({ ok: 2 });
    // tree, tree at, export
    const at = await ath(["tree", "at", id, "sec=1"], { cwd: f, env });
    expect(at.stdout.trim()).toBe(`${h.at}  (heading)`);
    const md = await ath(["export", "markdown", id], { cwd: f, env });
    expect(md.stdout).toContain("## 1. Introduction");
    expect(md.stdout).toContain("Body text on page one only.");
    expect(md.stdout).toMatch(/chrome\s+3 lines by repetition/);
    expect(md.stdout).toMatch(/remainder\s+\d+ of \d+ words/);
    // a second pass corrects the paragraph's reading (a whitespace slip: L7 still agrees): a lineage row, the old rev gone
    const open2 = await ath(["--json", "pass", "open", id, "--by", "claude-sonnet", "--verify", "claude-opus"], { cwd: f, env });
    expect((open2.json() as { data: { id: string } }).data.id).toBe("p2");
    writeFileSync(file, `${JSON.stringify({ at: b.at, predicate: "reads_as", aspect: "text", body: "Body text on page one  only." })}\n`);
    expect((await ath(["claims", "append", id, "--pass", "p2", "--from", file], { cwd: f, env })).code).toBe(0);
    const sign2 = await ath(["--json", "pass", "sign", id, "p2"], { cwd: f, env });
    expect((sign2.json() as { data: { corrected: number; added: number } }).data).toMatchObject({ corrected: 1, added: 1 });
    const lineage = readJsonl(join(f, "corpus", "lineage.jsonl"));
    expect(lineage.length).toBe(1);
    expect(lineage[0]).toMatchObject({ op: "correct", subject: id, by: "pass:p2" });
    expect((lineage[0]!.was as { rev: string }).rev).toBe(await bodyRev("Body text on page one only."));
    const after = readJsonl(join(f, "corpus", `${id}.claims.jsonl`)).filter((l) => l.predicate === "reads_as" && l.at === b.at);
    expect(after.length).toBe(1);
    expect(after[0]!.pass).toBe("p2");
    // a divergent reading: the owner accepts it, then revokes
    const open3 = await ath(["--json", "pass", "open", id, "--by", "claude-opus", "--verify", "claude-sonnet"], { cwd: f, env });
    expect((open3.json() as { data: { id: string } }).data.id).toBe("p3");
    writeFileSync(file, `${JSON.stringify({ at: h.at, predicate: "reads_as", aspect: "text", body: "Intro" })}\n`);
    await ath(["claims", "append", id, "--pass", "p3", "--from", file], { cwd: f, env });
    expect((await ath(["pass", "sign", id, "p3"], { cwd: f, env })).code).toBe(0);
    const div = await ath(["--json", "inspect", id], { cwd: f, env });
    expect(div.code).toBe(1);
    const dd = (div.json() as { data: { rows: { at: string; state: string; rev: string; detail: string }[] } }).data;
    expect(dd.rows.length).toBe(1);
    expect(dd.rows[0]).toMatchObject({ at: h.at, state: "diverges" });
    const rev = dd.rows[0]!.rev;
    const noTty = await ath(["inspect", "accept", id, "--at", h.at, "--rev", rev, "--why", "test"], { cwd: f, env });
    expect(noTty.code).toBe(64); // hidden from an agent
    const acc = await ath(["inspect", "accept", id, "--at", h.at, "--rev", rev, "--why", "short form on purpose"], {
      cwd: f,
      env,
      tty: true,
      confirm: async () => "inspect accept",
    });
    expect(acc.code).toBe(0);
    const owner = readJsonl(join(f, "corpus", `${id}.owner.jsonl`));
    expect(owner[0]).toMatchObject({
      at: h.at,
      predicate: "inspected",
      value: { rev, diverges: "accepted", why: "short form on purpose" },
      by: "owner",
    });
    expect((await ath(["inspect", id], { cwd: f, env })).code).toBe(0);
    expect((await ath(["inspect", id], { cwd: f, env })).stdout).toContain("accepted");
    const rev1 = await ath(["inspect", "revoke", id, "--at", h.at, "--rev", rev], {
      cwd: f,
      env,
      tty: true,
      confirm: async () => "inspect revoke",
    });
    expect(rev1.code).toBe(0);
    expect(readFileSync(join(f, "corpus", `${id}.owner.jsonl`), "utf8")).toBe("");
    expect((await ath(["inspect", id], { cwd: f, env })).code).toBe(1);
    // walked makes G3 block
    const open4 = await ath(["--json", "pass", "open", id, "--by", "a", "--verify", "b"], { cwd: f, env });
    expect((open4.json() as { data: { id: string } }).data.id).toBe("p4");
    const w = await ath(["--json", "pass", "sign", id, "p4", "--walked"], { cwd: f, env });
    expect(w.code).toBe(1);
    expect(
      (w.json() as { data: { signed: boolean; findings: { code: string; severity: string }[] } }).data.findings.find(
        (x) => x.code === "G3",
      )!.severity,
    ).toBe("block");
    expect((await ath(["pass", "abandon", id, "p4"], { cwd: f, env })).code).toBe(0);
    // staleness: edit a term the tree uses, every pass is pinned to the old hash
    writeFileSync(
      join(f, "ontology", "paragraph.claims.jsonl"),
      `${readFileSync(join(f, "ontology", "paragraph.claims.jsonl"), "utf8")}{"subject":"paragraph","predicate":"definition","value":"a block of prose"}\n`,
    );
    const stale = await ath(["--json", "verify", "--stale"], { cwd: f, env });
    expect(stale.code).toBe(1);
    expect((stale.json() as { data: { stale: { pass: string }[] } }).data.stale.map((s) => s.pass).sort()).toEqual(["p1", "p2", "p3"]);
  });
});
