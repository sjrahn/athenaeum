// corpus.ingest.test.ts — through the CLI: a foundation and an extension, ingest of the fixture bytes, the op lines
// written, members as subjects, idempotence, the foundation read-only from above, sort idempotent, history.
import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { readJsonl } from "../src/lib/jsonl.ts";
import { ath, scratch } from "./harness.ts";
import { extension, foundation } from "./layers.ts";

const FIX = join(import.meta.dir, "fixtures");
const PY = join(import.meta.dir, "fixtures");
const env = { ATH_ACTOR: "tester" };

describe("layer + ingest", () => {
  test("layer init makes a foundation and an extension; show and check see the chain", async () => {
    const base = scratch();
    const f = await ath(["layer", "init", join(base, "pub"), "--name", "public"], { env });
    expect(f.code).toBe(0);
    expect(existsSync(join(base, "pub", "athenaeum.yaml"))).toBe(true);
    expect(readFileSync(join(base, "pub", ".gitignore"), "utf8")).toContain("/corpus/bytes/");
    const e = await ath(["layer", "init", join(base, "mine"), "--extends", join(base, "pub")], { env });
    expect(e.code).toBe(0);
    const bad = await ath(["layer", "init", join(base, "pub")], { env });
    expect(bad.code).toBe(73);
    const show = await ath(["--json", "layer", "show"], { cwd: join(base, "mine"), env });
    const d = (show.json() as { data: { layers: { layer: string; name: string }[]; ontology: string } }).data;
    expect(d.layers.map((l) => l.layer)).toEqual(["foundation", "extension"]);
    expect(d.ontology).toMatch(/^b3:/);
    expect((await ath(["layer", "check"], { cwd: join(base, "mine"), env })).code).toBe(0);
    const notier = await ath(["layer", "init", join(base, "x"), "--tier", "private"], { env });
    expect(notier.code).toBe(64);
  });

  test("ingest writes attests + captured_from, places bytes, mints zip members, and is idempotent", async () => {
    const f = foundation();
    const r = await ath(
      [
        "--json",
        "--now",
        "2026-10-13T00:00:00Z",
        "ingest",
        join(FIX, "small.csv"),
        join(FIX, "small.html"),
        join(FIX, "small.zip"),
        join(PY, "sample.png"),
        "--origin",
        "fixtures",
        "--via",
        "upload",
      ],
      { cwd: f, env },
    );
    expect(r.code).toBe(0);
    const rows = (r.json() as { data: { ingested: { blake3: string; mime: string; members: number; existed: boolean }[] } }).data.ingested;
    expect(rows.map((x) => x.mime)).toEqual(["text/csv", "text/html", "application/zip", "text/plain", "text/csv", "image/png"]);
    expect(rows[2]!.members).toBe(2);
    expect(rows.every((x) => !x.existed)).toBe(true);
    const csv = rows[0]!;
    const lines = readJsonl(join(f, "corpus", `${csv.blake3}.claims.jsonl`));
    expect(lines.map((l) => l.predicate)).toEqual(["attests", "captured_from"]);
    expect(lines[0]).toMatchObject({ at: "whole", value: { mime: "text/csv", rows: 3, cols: 3, bom: true }, by: "ath.ingest@1" });
    expect(lines[1]!.value).toEqual({ origin: "fixtures", via: "upload", received: "2026-10-13" });
    expect(existsSync(join(f, "corpus", "bytes", csv.blake3.slice(0, 2), csv.blake3))).toBe(true);
    // the html banner supplies its own provenance; flags override
    const html = readJsonl(join(f, "corpus", `${rows[1]!.blake3}.claims.jsonl`));
    expect(html[1]!.value).toEqual({
      origin: "fixtures",
      uri: "https://www.example.com/threads/test-thread.123/",
      via: "upload",
      snapshot: "2026-08-15T23:40:36Z",
      received: "2026-10-13",
    });
    // a member names its container
    const member = readJsonl(join(f, "corpus", `${rows[3]!.blake3}.claims.jsonl`));
    expect(member[1]!.value).toEqual({ container: `corpus://${rows[2]!.blake3}`, path: "notes/readme.txt" });
    // again: nothing changes
    const again = await ath(
      ["--json", "ingest", join(FIX, "small.csv"), "--origin", "fixtures", "--via", "upload", "--received", "2026-10-13"],
      { cwd: f, env },
    );
    expect((again.json() as { data: { ingested: { existed: boolean }[] } }).data.ingested[0]!.existed).toBe(true);
    // a different provenance for the same bytes is a second captured_from? no: same op, same identity, different content → refused
    const diff = await ath(["ingest", join(FIX, "small.csv"), "--origin", "elsewhere", "--received", "2026-10-13"], { cwd: f, env });
    expect(diff.code).toBe(73);
    const show = await ath(["ingest", "show", csv.blake3], { cwd: f, env });
    expect(show.stdout).toContain("bytes  ");
    expect((await ath(["ingest", "show", "0".repeat(64)], { cwd: f, env })).code).toBe(66);
    expect((await ath(["ingest", join(FIX, "nope.bin")], { cwd: f, env })).code).toBe(66);
  });

  test("the foundation is read-only from above: same bytes are a no-op, a different line is refused; claims show unions the layers", async () => {
    const f = foundation();
    const e = extension(f);
    const first = await ath(["--json", "ingest", join(FIX, "small.csv"), "--origin", "a", "--received", "2026-10-13"], { cwd: f, env });
    const id = (first.json() as { data: { ingested: { blake3: string }[] } }).data.ingested[0]!.blake3;
    const same = await ath(["--json", "ingest", join(FIX, "small.csv"), "--origin", "a", "--received", "2026-10-13"], { cwd: e, env });
    expect(same.code).toBe(0);
    expect(existsSync(join(e, "corpus", `${id}.claims.jsonl`))).toBe(false);
    const other = await ath(["ingest", join(FIX, "small.csv"), "--origin", "b", "--received", "2026-10-13"], { cwd: e, env });
    expect(other.code).toBe(73);
    expect(other.stderr).toContain("lower layer");
    const show = await ath(["--json", "claims", "show", id], { cwd: e, env });
    const d = (show.json() as { data: { lines: { layer: string }[] } }).data;
    expect(d.lines.map((l) => l.layer)).toEqual(["foundation", "foundation"]);
    const sort = await ath(["--json", "claims", "sort", id], { cwd: f, env });
    expect((sort.json() as { data: { files: { changed: boolean }[] } }).data.files[0]!.changed).toBe(false);
  });

  test("ontology commands over the chain", async () => {
    const f = foundation();
    const list = await ath(["--json", "ontology", "list"], { cwd: f });
    expect((list.json() as { data: { terms: unknown[] } }).data.terms.length).toBe(76);
    const rules = await ath(["ontology", "rules", "heading"], { cwd: f });
    expect(rules.stdout).toContain("reads       text");
    const hash = await ath(["--json", "ontology", "hash"], { cwd: f });
    expect((hash.json() as { data: { terms: number } }).data.terms).toBe(76);
    expect((await ath(["ontology", "show", "nope"], { cwd: f })).code).toBe(66);
    const lint = await ath(["ontology", "lint"], { cwd: f });
    expect(lint.code).toBe(0);
    writeFileSync(join(f, "ontology", "cycle.claims.jsonl"), '{"subject":"cycle","predicate":"refines","value":"cycle"}\n');
    expect((await ath(["ontology", "lint"], { cwd: f })).stdout).toContain("cycle");
  });
});
