// lint.test.ts — the generic and per-file lints against hand-written defects: a reading under the wrong aspect (G1),
// an in that names no scope and a non-contiguous ord (G2), walked on a derived tree (G3/D-F4), undeclared and derived
// fields, a stray `scope:` in evidence (D-F8), a ledger claim with no attestation (D-F1), a stated value outside its
// quote (D-D4), a quote not in its surface (G4).
import { describe, expect, test } from "bun:test";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { ath } from "./harness.ts";
import { foundation } from "./layers.ts";

const FIX = join(import.meta.dir, "fixtures");
const env = { ATH_ACTOR: "tester" };
const PASS =
  '{"at":"whole","predicate":"pass","value":{"id":"p1","by":"a","verify":"b","ontology":"b3:0123456789abcdef","date":"2026-10-13"}}';

async function withLines(extra: string[]): Promise<{ f: string; id: string; codes: string[]; out: string }> {
  const f = foundation();
  const ing = await ath(["--json", "ingest", join(FIX, "small.html"), "--received", "2026-10-13"], { cwd: f, env });
  const id = (ing.json() as { data: { ingested: { blake3: string }[] } }).data.ingested[0]!.blake3;
  const p = join(f, "corpus", `${id}.claims.jsonl`);
  const current = await Bun.file(p).text();
  writeFileSync(p, current + [PASS, ...extra].map((l) => `${l}\n`).join(""));
  const r = await ath(["--json", "lint", id], { cwd: f, env });
  const d = (r.json() as { data: { findings: { code: string; msg: string }[] } }).data;
  return { f, id, codes: d.findings.map((x) => x.code), out: d.findings.map((x) => `${x.code} ${x.msg}`).join("\n") };
}

describe("lints", () => {
  test("a clean derived tree lints clean (G1–G3 pass, no file findings)", async () => {
    const r = await withLines([]);
    expect(r.codes.filter((c) => c.startsWith("G") || (c.startsWith("F-") && c !== "F-stale"))).toEqual([]);
    // the added pass line is pinned at a fake hash: listed as stale, not blocking
    expect(r.codes).toContain("F-stale");
  });

  test("G1: a reads_as under an aspect its term does not read", async () => {
    const r = await withLines([
      '{"at":"bytes=0,10","predicate":"manifests","term":"figure","pass":"p1"}',
      '{"at":"bytes=0,10","predicate":"in","value":{"at":"whole","ord":2},"pass":"p1"}',
      '{"at":"bytes=0,10","predicate":"reads_as","aspect":"text","rev":"b3:0123456789abcdef","body":"x","pass":"p1"}',
    ]);
    expect(r.out).toContain("G1 reads_as text but figure reads none");
  });

  test("G2: an in that names no scope; ord not contiguous; unreachable", async () => {
    const r = await withLines([
      '{"at":"bytes=0,10","predicate":"manifests","term":"paragraph","pass":"p1"}',
      '{"at":"bytes=0,10","predicate":"in","value":{"at":"bytes=1,2","ord":0},"pass":"p1"}',
      '{"at":"bytes=20,30","predicate":"manifests","term":"paragraph","pass":"p1"}',
      '{"at":"bytes=20,30","predicate":"in","value":{"at":"whole","ord":7},"pass":"p1"}',
    ]);
    expect(r.out).toContain("in names bytes=1,2, which is no scope");
    expect(r.out).toContain("not contiguous");
    expect(r.out).toContain("not reachable from whole");
  });

  test("G3: walked on a derived tree attests nothing (D-F4)", async () => {
    const r = await withLines(['{"at":"whole","predicate":"walked","pass":"p1"}']);
    expect(r.codes).toContain("G3");
  });

  test("per-file: undeclared field, derived field stored, unknown term, unresolved pass ref", async () => {
    const r = await withLines([
      '{"at":"bytes=0,10","predicate":"manifests","term":"heading","level":1,"scope":"h1","pass":"p1"}',
      '{"at":"bytes=0,10","predicate":"in","value":{"at":"whole","ord":2},"pass":"p1"}',
      '{"at":"bytes=20,30","predicate":"manifests","term":"page","number":1,"pass":"p1"}',
      '{"at":"bytes=20,30","predicate":"in","value":{"at":"whole","ord":3},"pass":"p1"}',
      '{"at":"bytes=40,50","predicate":"manifests","term":"nonesuch","pass":"p9"}',
      '{"at":"bytes=40,50","predicate":"in","value":{"at":"whole","ord":4},"pass":"p1"}',
    ]);
    expect(r.out).toContain("undeclared field 'scope'");
    expect(r.out).toContain("field 'number' is derived from the address and is never stored");
    expect(r.out).toContain("manifests unknown term 'nonesuch'");
    expect(r.out).toContain("names pass p9, which is not in the file");
  });

  test("ledger: attestation required (D-F1), stray keys refused (D-F8), G4 quote in surface, stated value in quote (D-D4)", async () => {
    const f = foundation();
    const ing = await ath(["--json", "ingest", join(FIX, "small.html"), "--received", "2026-10-13"], { cwd: f, env });
    const id = (ing.json() as { data: { ingested: { blake3: string }[] } }).data.ingested[0]!.blake3;
    const title = `corpus://${id}?bytes=`;
    const t = await ath(["--json", "tree", id], { cwd: f, env });
    const scopes = (t.json() as { data: { scopes: { at: string; terms: string[] }[] } }).data.scopes;
    const h1 = scopes.find((s) => s.terms[0] === "thread-title")!.at;
    writeFileSync(
      join(f, "ledger", "t.claims.jsonl"),
      [
        '{"subject":"t","predicate":"term","value":"forum-thread"}',
        `{"subject":"t","predicate":"title","value":"Idle/stall — ✓ 𝑃𝐸","evidence":[{"anchor":"corpus://${id}?${h1}&text","quote":"Idle/stall","kind":"direct","mode":"stated","reading":"derived:html.text@1"}],"by":"ath.test@1"}`,
        `{"subject":"t","predicate":"nope","value":"x","evidence":[{"anchor":"corpus://${id}?${h1}&text","quote":"not there","kind":"direct","mode":"stated","reading":"derived:html.text@1"}],"by":"ath.test@1"}`,
        `{"subject":"t","predicate":"bad","value":"x","evidence":[{"anchor":"corpus://${id}?${h1}&text","quote":"Idle/stall","scope":"h1","kind":"direct","mode":"stated","reading":"derived:html.text@1"}],"by":"ath.test@1"}`,
        `{"subject":"t","predicate":"unattested","value":"x","evidence":[]}`,
        `{"subject":"t","predicate":"split","value":"Pontiac Forum","evidence":[{"anchor":"corpus://${id}?whole","quote":"Ünïcode · thread | Example Forum","kind":"direct","mode":"stated","reading":"derived:html.title@1"}],"by":"ath.test@1"}`,
        `{"subject":"t","predicate":"held","value":"x","evidence":[{"anchor":"corpus://${id}?whole","quote":"x","kind":"direct","mode":"stated","reading":null}],"by":"ath.test@1"}`,
      ]
        .map((l) => `${l}\n`)
        .join(""),
    );
    expect(title).toBeTruthy();
    const r = await ath(["--json", "lint", "t"], { cwd: f, env });
    const out = (r.json() as { data: { findings: { code: string; msg: string }[] } }).data.findings
      .map((x) => `${x.code} ${x.msg}`)
      .join("\n");
    expect(r.code).toBe(1);
    expect(out).toContain("G4 nope entry 0: quote not in surface");
    expect(out).toContain('Unrecognized key: "scope"');
    expect(out).toContain("F-attest unattested: a ledger claim carries by (an op) or pass (D-F1)");
    expect(out).toContain("G4 split entry 0: a stated value is not in its quote (D-D4)");
    expect(out).not.toContain("title entry");
    const v = await ath(["--json", "verify", "t"], { cwd: f, env });
    const vd = (v.json() as { data: { claims: { predicate: string; status: string }[]; counts: { held: number; flagged: number } } }).data;
    expect(vd.counts.held).toBe(1);
    expect(vd.claims.find((c) => c.predicate === "held")!.status).toBe("unsupported");
    expect(vd.claims.find((c) => c.predicate === "title")!.status).toBe("provisional");
  });
});
