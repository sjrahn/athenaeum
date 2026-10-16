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
    // the same bytes from elsewhere is a second captured_from (D-captures: one line per capture); the same capture
    // with different content is still refused
    const diff = await ath(["--json", "ingest", join(FIX, "small.csv"), "--origin", "elsewhere", "--received", "2026-10-13"], {
      cwd: f,
      env,
    });
    expect(diff.code, diff.stderr).toBe(0);
    expect((diff.json() as { data: { ingested: { existed: boolean }[] } }).data.ingested[0]!.existed).toBe(false);
    const two = readJsonl(join(f, "corpus", `${csv.blake3}.claims.jsonl`)).filter((l) => l.predicate === "captured_from");
    expect(two.map((l) => (l.value as { origin: string }).origin).sort()).toEqual(["elsewhere", "fixtures"]);
    const redo = await ath(["ingest", join(FIX, "small.csv"), "--origin", "elsewhere", "--received", "2026-10-14"], { cwd: f, env });
    expect(redo.code).toBe(73);
    const show = await ath(["ingest", "show", csv.blake3], { cwd: f, env });
    expect(show.stdout).toContain("bytes  ");
    expect((await ath(["ingest", "show", "0".repeat(64)], { cwd: f, env })).code).toBe(66);
    expect((await ath(["ingest", join(FIX, "nope.bin")], { cwd: f, env })).code).toBe(66);
  });

  test("a producer's <file>.capture.yaml beside the bytes folds into captured_from (D-sidecar); flags still win", async () => {
    const f = foundation();
    const dir = scratch();
    const page = join(dir, "20261013T120000Z-thread.html");
    writeFileSync(page, readFileSync(join(FIX, "small.html")));
    writeFileSync(
      `${page}.capture.yaml`,
      [
        "source_url: https://www.example.com/threads/test-thread.123/",
        "fetched_at: 2026-10-13T12:00:00Z",
        'snapshot_engine: "singlefile@2026-08-21 blake3:49d2223068ad8c86afecf297ed5b37fb965ccc244ec87e8fc100baffc8e81b7b"',
        "capture_issues:",
        "  - {id: feed-partial, subtype: feed, severity: warn, detector: ita-web-capture@1, fields: {seen: 3}}",
        "origin_fields:",
        "  pagination: {pages: 2, form: query, posts: 40, page_urls: [https://www.example.com/threads/test-thread.123/, https://www.example.com/threads/test-thread.123/page-2]}",
        "capture_context: {host: arbre, actor: ita, trigger: request, session_id: s1}",
        "",
      ].join("\n"),
    );
    const r = await ath(["--json", "ingest", page, "--note", "R-0079"], { cwd: f, env });
    expect(r.code, r.stderr).toBe(0);
    const id = (r.json() as { data: { ingested: { blake3: string }[] } }).data.ingested[0]!.blake3;
    const lines = readJsonl(join(f, "corpus", `${id}.claims.jsonl`));
    expect(lines[1]!.value).toEqual({
      origin: "example.com",
      uri: "https://www.example.com/threads/test-thread.123/",
      via: "capture",
      snapshot: "2026-10-13T12:00:00Z",
      engine: "singlefile@2026-08-21 blake3:49d2223068ad8c86afecf297ed5b37fb965ccc244ec87e8fc100baffc8e81b7b",
      aliases: ["https://www.example.com/threads/test-thread.123/page-2"],
      fields: {
        pagination: {
          pages: 2,
          form: "query",
          posts: 40,
          page_urls: ["https://www.example.com/threads/test-thread.123/", "https://www.example.com/threads/test-thread.123/page-2"],
        },
      },
      issues: [{ id: "feed-partial", subtype: "feed", severity: "warn", detector: "ita-web-capture@1", fields: { seen: 3 } }],
      context: { host: "arbre", actor: "ita", trigger: "request", session_id: "s1" },
      note: "R-0079",
    });
    expect(existsSync(`${page}.capture.yaml`)).toBe(true); // the sidecar and the bytes stay where the producer put them
    // the banner in the bytes names the same uri, so this is the same capture described differently: refused, never
    // silently merged (D-captures keys a capture by its uri; another uri or origin would be a second line)
    const ignored = await ath(["--json", "ingest", page, "--no-sidecar", "--origin", "x", "--received", "2026-10-13"], { cwd: f, env });
    expect(ignored.code).toBe(73);
  });

  test("the foundation is read-only from above: same bytes are a no-op, the same capture restated is refused, another capture is the extension's own line; claims show unions the layers", async () => {
    const f = foundation();
    const e = extension(f);
    const first = await ath(["--json", "ingest", join(FIX, "small.csv"), "--origin", "a", "--received", "2026-10-13"], { cwd: f, env });
    const id = (first.json() as { data: { ingested: { blake3: string }[] } }).data.ingested[0]!.blake3;
    const same = await ath(["--json", "ingest", join(FIX, "small.csv"), "--origin", "a", "--received", "2026-10-13"], { cwd: e, env });
    expect(same.code).toBe(0);
    expect(existsSync(join(e, "corpus", `${id}.claims.jsonl`))).toBe(false);
    const restated = await ath(["ingest", join(FIX, "small.csv"), "--origin", "a", "--received", "2026-10-14"], { cwd: e, env });
    expect(restated.code).toBe(73);
    expect(restated.stderr).toContain("lower layer");
    const other = await ath(["ingest", join(FIX, "small.csv"), "--origin", "b", "--received", "2026-10-13"], { cwd: e, env });
    expect(other.code, other.stderr).toBe(0);
    const show = await ath(["--json", "claims", "show", id], { cwd: e, env });
    const d = (show.json() as { data: { lines: { layer: string }[] } }).data;
    expect(d.lines.map((l) => l.layer).sort()).toEqual(["foundation", "foundation", "mine"]);
    const sort = await ath(["--json", "claims", "sort", id], { cwd: f, env });
    expect((sort.json() as { data: { files: { changed: boolean }[] } }).data.files[0]!.changed).toBe(false);
  });

  test("ontology commands over the chain", async () => {
    const f = foundation();
    const list = await ath(["--json", "ontology", "list"], { cwd: f });
    expect((list.json() as { data: { terms: unknown[] } }).data.terms.length).toBe(162);
    const rules = await ath(["ontology", "rules", "heading"], { cwd: f });
    expect(rules.stdout).toContain("reads       text");
    const hash = await ath(["--json", "ontology", "hash"], { cwd: f });
    expect((hash.json() as { data: { terms: number } }).data.terms).toBe(162);
    expect((await ath(["ontology", "show", "nope"], { cwd: f })).code).toBe(66);
    const lint = await ath(["ontology", "lint"], { cwd: f });
    expect(lint.code).toBe(0);
    writeFileSync(join(f, "ontology", "cycle.claims.jsonl"), '{"subject":"cycle","predicate":"refines","value":"cycle"}\n');
    expect((await ath(["ontology", "lint"], { cwd: f })).stdout).toContain("cycle");
  });
});
