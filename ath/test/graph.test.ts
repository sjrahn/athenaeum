// graph.test.ts — the graph end to end (§14, §13.5, §17): entity passes bind their evidence — a reading's revision, a
// sheet's cell through `csv.parse@1`, a scope's field, a testimony's surface — and refuse a quote not in its body;
// status by the table: provisional from one artifact, confirmed from two that are not one source, provisional again
// when `manifests` makes them one, confirmed by grounded authority, disputed and refuted by challenges, conflicting on
// a functional property; a re-read holds the entry and owes a re-bind; a distrusted testimony holds what cites it;
// rulings steer demand; split, merge and rename rewrite every reference; check finds what the citation check does.
import { describe, expect, test } from "bun:test";
import { copyFileSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { ath, scratch, TESTDATA } from "./harness.ts";

const SYN = join(TESTDATA, "synthetic");
const A = { ATH_ACTOR: "reader-a" };
const B = { ATH_ACTOR: "reader-b" };
const OWNER = { ATH_ACTOR: "owner" };
const LISTING = "7684234e970a2940ac15d0974c20cded566641eefa6c5bcd5dd2ac45b1e396cc";
const ZIP = "da7b858a7acc71ea1953f162369503c564bce9e6ec59ad1b717c6864ccaf34f0";
const CSV = "7ce98d2c8bf71eae6ce2ac944cca99c1a84e8bf5c4d64d2a653aab11f6780964";
const SIGN = "6aa934e58bc0dff94e8cb1281ccb0066ff98c9346baca2c72d8764cce6244471";
const PROC = "5e6e497d934498fc49229ba8c594684114a1213426bc1ad0113718ae72794269";
const ADDR = "bytes=800,967";
const PRICE = "bytes=985,1022";
type R = { code: number; stdout: string; stderr: string; json: () => unknown };
const data = <D>(r: R) => (r.json() as { data: D }).data;

async function world() {
  const root = join(scratch(), "household");
  expect((await ath(["instance", "init", root], { env: A })).code).toBe(0);
  const run = (argv: string[], env: Record<string, string> = A) => ath(["--json", ...argv], { env, cwd: root });
  const owner = (argv: string[]) => ath(argv, { env: OWNER, tty: true, cwd: root, confirm: async () => argv.slice(0, 2).join(" ") });
  const vocab = async (v: string, t: string, ...lines: object[]) =>
    expect((await owner(["vocab", "add", v, t, ...lines.map((l) => JSON.stringify(l))])).code).toBe(0);
  await vocab("properties", "address", { pred: "range", val: "string" }, { pred: "functional", val: true });
  await vocab("properties", "price", { pred: "range", val: "amount" }, { pred: "functional", val: true });
  await vocab("properties", "display-name", { pred: "range", val: "string" });
  await vocab("properties", "fetched-from", { pred: "range", val: "uri" });
  await vocab("properties", "version", { pred: "range", val: "string" });
  await vocab("kinds", "residence", { pred: "owes", val: ["address", "price"] });
  await vocab("kinds", "vessel", { pred: "owes", val: ["display-name"] });
  await vocab("kinds", "standard", { pred: "owes", val: [] });
  const work = scratch();
  for (const f of ["cottage-listing.html", "drive-folder.zip", "drive-folder.zip.capture.yaml", "sign.jpg", "procedure.pdf"])
    copyFileSync(join(SYN, f), join(work, f));
  writeFileSync(
    join(work, "cottage-listing.html.testimony.yaml"),
    `subject: b3:${LISTING}\nproducer: {tool: page-capture, version: "4.2", at: "2026-03-19T21:40:00Z"}\nsource:\n  uri: https://homes.example.invalid/listing/12-quay-street\n`,
  );
  expect((await ath(["--root", root, "ingest", "cottage-listing.html", "sign.jpg", "procedure.pdf"], { env: A, cwd: work })).code).toBe(0);
  expect(
    (await ath(["--root", root, "ingest", "drive-folder.zip", "--testimony", "drive-folder.zip.capture.yaml"], { env: A, cwd: work })).code,
  ).toBe(0);
  const read = async (subject: string, readings: [string, string][], by = A, ver = B) => {
    const { id } = data<{ id: string }>(await run(["pass", "open", subject.slice(0, 8)], by));
    for (const [at, text] of readings) await run(["pass", "stage", subject.slice(0, 8), id, "--at", at, "--text", text], by);
    const s = await run(["pass", "sign", subject.slice(0, 8), id], ver);
    expect(s.code, s.stdout).toBe(0);
  };
  const claim = async (entity: string, lines: object[], by = A, ver = B) => {
    const { id } = data<{ id: string }>(await run(["pass", "open", entity], by));
    for (const l of lines) await run(["pass", "stage", entity, id, "--line", JSON.stringify(l)], by);
    return run(["pass", "sign", entity, id], ver);
  };
  return { root, work, run, owner, vocab, read, claim };
}

const ev = (anchor: string, quote: string, extra: object = {}) => ({ anchor, mode: "stated", quote, ...extra });
const status = (claims: { entity: string; pred: string; status: string }[], entity: string, pred: string) =>
  claims.filter((c) => c.entity === entity && c.pred === pred).map((c) => c.status);

describe("binding", () => {
  test("a pass binds a reading's revision, a cell through its surface, a testimony's surface; it refuses a quote not in its body", async () => {
    const w = await world();
    await w.read(LISTING, [
      [ADDR, "12 Quay Street, Port Ellen"],
      [PRICE, "£313,000"],
    ]);
    const s = await w.claim("quay-street-12", [
      { pred: "is", val: "residence" },
      { pred: "address", val: "12 Quay Street, Port Ellen", ev: [ev(`ath://${LISTING}?${ADDR}&text`, "12 Quay Street, Port Ellen")] },
      { pred: "price", val: "£313,000", ev: [ev(`ath://${LISTING}?${PRICE}`, "£313,000")] },
    ]);
    expect(s.code, s.stdout).toBe(0);
    const file = readFileSync(join(w.root, "graph/entities/qu/quay-street-12.jsonl"), "utf8")
      .split("\n")
      .filter(Boolean)
      .map((l) => JSON.parse(l));
    expect(file[0]).toEqual({
      pred: "address",
      val: "12 Quay Street, Port Ellen",
      ev: [
        {
          anchor: `ath://${LISTING}?${ADDR}&text`,
          binding: expect.stringMatching(/^b3:[0-9a-f]{16}$/),
          mode: "stated",
          quote: "12 Quay Street, Port Ellen",
        },
      ],
      pass: "p1",
    });
    expect(file.find((l) => l.pred === "pass")).toMatchObject({ val: { id: "p1", by: "reader-a", verify: "reader-b" } });
    expect(Object.keys(file[0])).toEqual(["pred", "val", "ev", "pass"]);
    // a sheet's cell, inside the zip, by its own id; the testimony's surface by its hash, with a prefix
    const t = data<{ results: { testimony: { hash: string }[] }[] }>(
      await w.run(["--root", w.root, "ingest", join(w.work, "cottage-listing.html")]),
    );
    const testimony = t.results[0]!.testimony[0]!.hash;
    const v = await w.claim("lantern", [
      { pred: "is", val: "vessel" },
      { pred: "display-name", val: "Lantern", ev: [ev(`ath://${ZIP}?path=Harbour plans/Berth list.csv&row=1&col=1`, "Lantern")] },
    ]);
    expect(v.code, v.stdout).toBe(0);
    expect(readFileSync(join(w.root, "graph/entities/la/lantern.jsonl"), "utf8")).toContain(
      `"anchor":"ath://${ZIP}?path=Harbour plans/Berth list.csv&row=1&col=1","binding":"derived:csv.parse@1"`,
    );
    const f = await w.claim(
      "quay-street-12",
      [
        {
          pred: "fetched-from",
          val: "https://homes.example.invalid/listing/12-quay-street",
          ev: [ev(`ath://${testimony}?bytes=0,400`, "https://homes.example.invalid/listing/12-quay-street", { prefix: "" })],
        },
      ],
      B,
      A,
    );
    expect(f.code, f.stdout).toBe(0);
    expect(readFileSync(join(w.root, "graph/entities/qu/quay-street-12.jsonl"), "utf8")).toContain('"binding":"derived:yaml.text@1"');
    // refusals: a quote not in the reading, an unread region, a value the quote does not hold, a property the graph lacks
    const bad = async (lines: object[], text: string) => {
      const r = await w.claim("quay-street-12", lines);
      expect(r.code).toBe(73);
      expect((r.json() as { error: { message: string } }).error.message).toContain(text);
      await w.run([
        "pass",
        "abandon",
        "quay-street-12",
        data<{ open: { id: string }[] }>(await w.run(["pass", "show", "quay-street-12"])).open[0]!.id,
      ]);
    };
    await bad(
      [{ pred: "address", val: "12 Quay Street", ev: [ev(`ath://${LISTING}?${ADDR}`, "13 Quay Street")] }],
      "the quote is not in the reading",
    );
    await bad(
      [{ pred: "address", val: "x", ev: [ev(`ath://${LISTING}?bytes=1088,1120`, "2 bedrooms")] }],
      "there is no reading at bytes=1088,1120",
    );
    await bad(
      [{ pred: "address", val: "Port Ellen harbour", ev: [ev(`ath://${LISTING}?${ADDR}`, "Port Ellen")] }],
      "a stated entry's quote holds the value",
    );
    await bad([{ pred: "colour", val: "white" }], "colour is not a property");
    await bad(
      [{ pred: "price", val: "£313,000", ev: [ev(`ath://${LISTING}?${PRICE}`, "£313,000", { mode: "inferred" })] }],
      "carries a reason",
    );
  });
});

describe("status", () => {
  test("one artifact provisional; two artifacts confirmed; one source when they manifest one entity; a challenge disputes; a functional conflict", async () => {
    const w = await world();
    await w.read(LISTING, [[ADDR, "12 Quay Street, Port Ellen"]]);
    await w.read(SIGN, [["bbox=0.0667,0.4643,0.4556,0.1024", "12 Quay Street, Port Ellen"]]);
    const one = await w.claim("quay-street-12", [
      { pred: "is", val: "residence" },
      { pred: "address", val: "12 Quay Street, Port Ellen", ev: [ev(`ath://${LISTING}?${ADDR}`, "12 Quay Street, Port Ellen")] },
    ]);
    expect(one.code).toBe(0);
    const v1 = data<{ claims: { entity: string; pred: string; status: string }[] }>(await w.run(["verify"]));
    expect(status(v1.claims, "quay-street-12", "address")).toEqual(["provisional"]);
    await w.claim(
      "quay-street-12",
      [
        {
          pred: "address",
          val: "12 Quay Street, Port Ellen",
          ev: [ev(`ath://${SIGN}?bbox=0.0667,0.4643,0.4556,0.1024`, "12 Quay Street, Port Ellen")],
        },
      ],
      B,
      A,
    );
    expect(
      status(
        data<{ claims: { entity: string; pred: string; status: string }[] }>(await w.run(["verify"])).claims,
        "quay-street-12",
        "address",
      ),
    ).toEqual(["confirmed"]);
    // the two artifacts manifest one listing: one source, so provisional again
    await w.claim("quay-listing", [
      {
        pred: "manifests",
        val: `ath://${LISTING}`,
        ev: [{ anchor: `ath://${LISTING}`, mode: "inferred", reason: "the page itself", binding: "observed" }],
      },
      {
        pred: "manifests",
        val: `ath://${SIGN}`,
        ev: [{ anchor: `ath://${SIGN}`, mode: "inferred", reason: "a photograph of the same notice", binding: "observed" }],
      },
    ]);
    expect(
      status(
        data<{ claims: { entity: string; pred: string; status: string }[] }>(await w.run(["verify"])).claims,
        "quay-street-12",
        "address",
      ),
    ).toEqual(["provisional"]);
    // a functional property with two bound values conflicts
    await w.read(LISTING, [[PRICE, "£313,000"]]);
    await w.claim("quay-street-12", [{ pred: "address", val: "£313,000", ev: [ev(`ath://${LISTING}?${PRICE}`, "£313,000")] }]);
    const v3 = data<{ claims: { entity: string; pred: string; status: string }[] }>(await w.run(["verify"]));
    expect(status(v3.claims, "quay-street-12", "address").sort()).toEqual(["conflicting", "conflicting"]);
    // a challenge with a bound entry disputes the claim it names
    await w.claim(
      "quay-street-12",
      [
        {
          pred: "challenges",
          val: { pred: "address", val: "£313,000" },
          ev: [
            ev(`ath://${LISTING}?${ADDR}`, "12 Quay Street, Port Ellen", {
              mode: "inferred",
              reason: "the address is printed in the heading, not the price",
            }),
          ],
        },
      ],
      B,
      A,
    );
    const v4 = data<{ claims: { entity: string; pred: string; val: unknown; status: string }[] }>(await w.run(["verify"]));
    expect(v4.claims.find((c) => c.pred === "address" && c.val === "£313,000")!.status).toBe("disputed");
  });

  test("authority is grounded: an artifact cannot vouch for itself; confirmed by others, its source claim confers it", async () => {
    const w = await world();
    const head = "page=1&bbox=0.1429,0.6906,0.0901,0.0087";
    const code = "page=1&bbox=0.1433,0.1928,0.0591,0.0103";
    await w.read(PROC, [
      [head, "Version 02.1"],
      [code, "HL-02"],
    ]);
    await w.read(LISTING, [[ADDR, "12 Quay Street, Port Ellen"]]);
    await w.claim("hl-02", [
      { pred: "is", val: "standard" },
      { pred: "version", val: "02.1", ev: [ev(`ath://${PROC}?${head}`, "Version 02.1")] },
      {
        pred: "source",
        val: `ath://${PROC}`,
        ev: [ev(`ath://${PROC}?${code}`, "HL-02", { mode: "inferred", reason: "it prints the standard's designation" })],
      },
    ]);
    const v1 = data<{ claims: { entity: string; pred: string; status: string }[]; rounds: number }>(await w.run(["verify"]));
    expect(status(v1.claims, "hl-02", "source")).toEqual(["inferred"]);
    expect(status(v1.claims, "hl-02", "version")).toEqual(["provisional"]);
    // two independent artifacts confirm the source claim; its authority then confirms what the procedure says
    await w.read(SIGN, [["bbox=0.0667,0.1786,0.6022,0.1548", "HL-02"]]);
    await w.claim(
      "hl-02",
      [
        {
          pred: "source",
          val: `ath://${PROC}`,
          ev: [ev(`ath://${SIGN}?bbox=0.0667,0.1786,0.6022,0.1548`, "HL-02", { mode: "inferred", reason: "the notice names it" })],
        },
      ],
      B,
      A,
    );
    const v2 = data<{ claims: { entity: string; pred: string; status: string; entries: { standing?: string }[] }[]; rounds: number }>(
      await w.run(["verify"]),
    );
    expect(status(v2.claims, "hl-02", "source")).toEqual(["confirmed"]);
    expect(status(v2.claims, "hl-02", "version")).toEqual(["confirmed"]);
    expect(v2.claims.find((c) => c.pred === "version")!.entries[0]!.standing).toBe("authoritative");
    expect(v2.rounds).toBeGreaterThan(1);
  });
});

describe("held evidence, rulings and demand", () => {
  test("a re-read holds the entry and owes a re-bind; a later pass's own line re-binds; a distrusted testimony holds what cites it", async () => {
    const w = await world();
    await w.read(LISTING, [[ADDR, "12 Quay Street, Port Ellen"]]);
    await w.claim("quay-street-12", [
      { pred: "is", val: "residence" },
      { pred: "address", val: "12 Quay Street", ev: [ev(`ath://${LISTING}?${ADDR}`, "12 Quay Street", { mode: "stated" })] },
    ]);
    await w.read(LISTING, [[ADDR, "12 Quay Street, Port Ellen, Islay"]], B, A);
    const v = data<{ claims: { pred: string; entries: { state: string; rebind?: boolean }[] }[]; demand: { kind: string }[] }>(
      await w.run(["verify"]),
    );
    expect(v.claims.find((c) => c.pred === "address")!.entries).toEqual([expect.objectContaining({ state: "held", rebind: true })]);
    expect(v.demand.map((d) => d.kind)).toContain("re-bind");
    await w.claim(
      "quay-street-12",
      [{ pred: "address", val: "12 Quay Street", ev: [ev(`ath://${LISTING}?${ADDR}`, "12 Quay Street")] }],
      B,
      A,
    );
    const v2 = data<{ claims: { pred: string; status: string; entries: { state: string }[] }[] }>(await w.run(["verify"]));
    expect(
      v2.claims
        .find((c) => c.pred === "address")!
        .entries.map((e) => e.state)
        .sort(),
    ).toEqual(["bound", "held"]);
    expect(v2.claims.find((c) => c.pred === "address")!.status).toBe("provisional");
    // the drive export's testimony, distrusted, holds a claim that cites it
    const zipRec = readFileSync(join(w.root, "corpus/records/da", `${ZIP}.yaml`), "utf8");
    expect(zipRec).toContain("google-drive-export");
    const r = await w.owner(["rule", "distrust", ZIP.slice(0, 8), "--why", "the export was re-run"]);
    expect(r.code, r.stderr).toBe(0);
    await w.claim("lantern", [
      { pred: "is", val: "vessel" },
      { pred: "display-name", val: "Lantern", ev: [ev(`ath://${CSV}?row=1&col=1`, "Lantern")] },
    ]);
    const v3 = data<{ claims: { entity: string; entries: { state: string }[] }[] }>(await w.run(["verify", "lantern"]));
    expect(v3.claims.find((c) => c.entity === "lantern")!.entries[0]!.state).toBe("bound"); // the CSV is its own artifact
    expect((await w.owner(["rule", "distrust", CSV.slice(0, 8)])).code).toBe(0);
    const v4 = data<{ claims: { entity: string; entries: { state: string; reason?: string }[] }[] }>(await w.run(["verify", "lantern"]));
    expect(v4.claims.find((c) => c.entity === "lantern")!.entries[0]).toMatchObject({
      state: "held",
      reason: "it relies on what a ruling distrusts",
    });
    const rl = data<{ rulings: { id: string; pred: string; affects: string[] }[] }>(await w.run(["rulings"]));
    expect(rl.rulings.map((x) => x.id)).toEqual(["r1", "r2"]);
    expect((await w.owner(["rule", "revoke", "r2"])).code).toBe(0);
    expect(data<{ rulings: unknown[] }>(await w.run(["rulings"])).rulings).toHaveLength(1);
  });

  test("an unmet owes is a search; seek demands what it names and makes it relevant; decline removes demand", async () => {
    const w = await world();
    await w.read(LISTING, [[ADDR, "12 Quay Street, Port Ellen"]]);
    await w.claim("quay-street-12", [
      { pred: "is", val: "residence" },
      { pred: "address", val: "12 Quay Street, Port Ellen", ev: [ev(`ath://${LISTING}?${ADDR}`, "12 Quay Street, Port Ellen")] },
    ]);
    const d1 = data<{ demand: { kind: string; subject: string; detail: string }[] }>(await w.run(["verify"]));
    expect(d1.demand).toContainEqual({ kind: "search", subject: "quay-street-12", detail: "price" });
    await w.vocab("properties", "tenure", { pred: "range", val: "string" });
    expect((await w.owner(["rule", "seek", "--kind", "residence", "--owes", "tenure", "--why", "compare running costs"])).code).toBe(0);
    const d2 = data<{ demand: { kind: string; subject: string; detail: string; ruling?: string }[] }>(await w.run(["verify"]));
    expect(d2.demand).toContainEqual({ kind: "seek", subject: "quay-street-12", detail: "tenure", ruling: "r1" });
    const rel = data<{ relevant: { ruling: string; subject: string }[] }>(await w.run(["relevant"]));
    expect(rel.relevant.map((r) => r.subject)).toEqual(expect.arrayContaining(["quay-street-12", LISTING]));
    expect((await w.owner(["rule", "decline", "search:quay-street-12:price"])).code).toBe(0);
    const d3 = data<{ demand: { kind: string; detail: string }[] }>(await w.run(["verify"]));
    expect(d3.demand.some((d) => d.kind === "search" && d.detail === "price")).toBe(false);
  });
});

describe("entity verbs and check", () => {
  test("rename, merge and split rewrite every reference; check finds a line the sorts refuse", async () => {
    const w = await world();
    await w.read(LISTING, [[ADDR, "12 Quay Street, Port Ellen"]]);
    await w.vocab("properties", "same-street", { pred: "range", val: "residence" });
    await w.claim("quay-street-12", [
      { pred: "is", val: "residence" },
      { pred: "address", val: "12 Quay Street, Port Ellen", ev: [ev(`ath://${LISTING}?${ADDR}`, "12 Quay Street, Port Ellen")] },
    ]);
    await w.claim("quay-street-14", [
      { pred: "is", val: "residence" },
      { pred: "same-street", val: "ath://quay-street-12" },
    ]);
    expect((await w.run(["entity", "rename", "quay-street-12", "twelve-quay-street"])).code).toBe(0);
    expect(readFileSync(join(w.root, "graph/entities/qu/quay-street-14.jsonl"), "utf8")).toContain('"val":"ath://twelve-quay-street"');
    expect((await w.run(["entity", "merge", "quay-street-14", "twelve-quay-street"])).code).toBe(0);
    const merged = readFileSync(join(w.root, "graph/entities/tw/twelve-quay-street.jsonl"), "utf8");
    expect(merged.match(/"pred":"pass"/g)).toHaveLength(2);
    expect(merged).toContain('"id":"p2"');
    expect((await w.run(["entity", "split", "twelve-quay-street", "quay-street-14", "--claim", "same-street"])).code).toBe(0);
    expect(readFileSync(join(w.root, "graph/entities/qu/quay-street-14.jsonl"), "utf8")).toContain('"pred":"same-street"');
    expect((await w.run(["check"])).code).toBe(0);
    // a hand-written line the sorts refuse, and a file out of canonical order
    const p = join(w.root, "graph/entities/qu/quay-street-14.jsonl");
    writeFileSync(p, `${readFileSync(p, "utf8")}{"pred":"colour","val":"red","pass":"p2"}\n`);
    const c = await w.run(["check", "quay-street-14"]);
    expect(c.code).toBe(1);
    const msgs = data<{ findings: { check: string; message: string }[] }>(c).findings.map((f) => `${f.check}: ${f.message}`);
    expect(msgs).toEqual(
      expect.arrayContaining([
        "sorts: colour is not a property",
        "per file: the file is not sorted by identity in canonical form: `ath sort` it",
      ]),
    );
  });
});
