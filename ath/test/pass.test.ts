// pass.test.ts — passes end to end (§13, §8.3–§8.5): an author stages, a different verifier signs, signing lays the
// pass over the record and runs the checks; a pass covers what it names and its attestations stand while it is the
// latest; ids are never reused once signed and free again once abandoned; a record changed since a pass was opened
// refuses it; a forming pass replaces the tree whole and adopts every reading; a partial pass over a formed record
// mints nothing; the reading check advises and never blocks.
import { describe, expect, test } from "bun:test";
import { copyFileSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { loadRecord } from "@ath/engine/record/document.ts";
import { ath, scratch, TESTDATA } from "./harness.ts";

const SYN = join(TESTDATA, "synthetic");
const SIGN = "6aa934e58bc0dff94e8cb1281ccb0066ff98c9346baca2c72d8764cce6244471";
const PROC = "5e6e497d934498fc49229ba8c594684114a1213426bc1ad0113718ae72794269";
const A = { ATH_ACTOR: "reader-a" };
const B = { ATH_ACTOR: "reader-b" };
type R = { code: number; stdout: string; stderr: string; json: () => unknown };
const data = <D>(r: R) => (r.json() as { data: D }).data;

async function setup() {
  const root = join(scratch(), "household");
  expect((await ath(["instance", "init", root], { env: A })).code).toBe(0);
  const vocab = async (v: string, t: string, ...lines: object[]) => {
    const r = await ath(["vocab", "add", v, t, ...lines.map((l) => JSON.stringify(l))], {
      env: { ATH_ACTOR: "owner" },
      tty: true,
      cwd: root,
      confirm: async () => "vocab add",
    });
    expect(r.code, r.stderr).toBe(0);
  };
  await vocab("forms", "line", { pred: "reads", val: "text" });
  await vocab("forms", "cover-page", { pred: "reads", val: "none" });
  await vocab(
    "forms",
    "heading",
    { pred: "reads", val: "text" },
    { pred: "field", val: { name: "num", type: "designator", where: "leading", pattern: "^(\\d+)\\.$", address: "sec" } },
    { pred: "field", val: { name: "level", type: "int" } },
  );
  const work = scratch();
  for (const f of ["sign.jpg", "procedure.pdf", "facebook-thread.json"]) copyFileSync(join(SYN, f), join(work, f));
  expect((await ath(["--root", root, "ingest", "sign.jpg", "procedure.pdf", "facebook-thread.json"], { env: A, cwd: work })).code).toBe(0);
  return { root, work, run: (argv: string[], env = A) => ath(["--json", ...argv], { env, cwd: root }) };
}

const record = (root: string, h: string) => loadRecord(readFileSync(join(root, "corpus/records", h.slice(0, 2), `${h}.yaml`), "utf8"));

describe("a reading pass", () => {
  test("staged by its author, signed by another; covers what it read; the stage follows the latest pass's attestation", async () => {
    const { root, run } = await setup();
    const o = data<{ id: string }>(await run(["pass", "open", SIGN.slice(0, 8)]));
    expect(o.id).toBe("p1");
    for (const [at, text] of [
      ["bbox=0.0667,0.1786,0.6022,0.1548", "RETURNS ONLY"],
      ["bbox=0.0667,0.4643,0.4556,0.1024", "Bay 12 - Depot 7"],
      ["bbox=0.0667,0.6976,0.6467,0.1071", "No parking 7am to 6pm"],
    ])
      expect((await run(["pass", "stage", SIGN.slice(0, 8), "p1", "--at", at!, "--text", text!])).code).toBe(0);
    expect((await run(["pass", "stage", SIGN.slice(0, 8), "p1", "--attests", "readings"])).code).toBe(0);
    expect((await run(["pass", "stage", SIGN.slice(0, 8), "p1", "--attests", "readings"], B)).code).toBe(77); // not reader-b's to stage
    expect((await run(["pass", "sign", SIGN.slice(0, 8), "p1"])).code).toBe(77); // the author does not verify
    const s = await run(["pass", "sign", SIGN.slice(0, 8), "p1"], B);
    expect(s.code, s.stdout).toBe(0);
    const r = record(root, SIGN);
    expect(r.passes!.p1).toMatchObject({ by: "reader-a", verify: "reader-b", date: "2026-03-20", attests: ["readings"] });
    expect(r.passes!.p1!.over).toHaveLength(3);
    expect(Object.values(r.readings!).map((x) => x.text)).toEqual(["RETURNS ONLY", "Bay 12 - Depot 7", "No parking 7am to 6pm"]);
    expect(data<{ stage: string }>(await run(["record", SIGN.slice(0, 8)])).stage).toBe("transcribed");
    // a correction re-reads one region: it answers for that region alone, and the attestation lapses with it
    await run(["pass", "open", SIGN.slice(0, 8)], B);
    await run(["pass", "stage", SIGN.slice(0, 8), "p2", "--at", "bbox=0.0667,0.4643,0.4556,0.1024", "--text", "Bay 12 – Depot 7"], B);
    expect((await run(["pass", "sign", SIGN.slice(0, 8), "p2"])).code).toBe(0);
    const shown = data<{ signed: { id: string; answers: string[]; superseded: boolean }[] }>(await run(["pass", "show", SIGN.slice(0, 8)]));
    expect(shown.signed.map((p) => [p.id, p.answers.length, p.superseded])).toEqual([
      ["p1", 2, false],
      ["p2", 1, false],
    ]);
    expect(data<{ stage: string }>(await run(["record", SIGN.slice(0, 8)])).stage).toBe("read");
  });

  test("ids: a signed id is never reused, an abandoned one is free again; a record changed since opening refuses the pass", async () => {
    const { run } = await setup();
    expect(data<{ id: string }>(await run(["pass", "open", SIGN.slice(0, 8)])).id).toBe("p1");
    expect(data<{ id: string }>(await run(["pass", "open", SIGN.slice(0, 8)], B)).id).toBe("p2");
    await run(["pass", "stage", SIGN.slice(0, 8), "p2", "--at", "bbox=0.1,0.1,0.2,0.1", "--text", "RETURNS"], B);
    expect((await run(["pass", "sign", SIGN.slice(0, 8), "p2"])).code).toBe(0);
    await run(["pass", "stage", SIGN.slice(0, 8), "p1", "--at", "bbox=0.1,0.5,0.2,0.1", "--text", "Bay"]);
    const stale = await run(["pass", "sign", SIGN.slice(0, 8), "p1"], B);
    expect(stale.code).toBe(73);
    expect((stale.json() as { error: { message: string } }).error.message).toContain("changed since p1 was opened");
    expect((await run(["pass", "abandon", SIGN.slice(0, 8), "p1"])).code).toBe(0);
    // p2 is signed: the next is p3, and an abandoned p3 is free again
    expect(data<{ id: string }>(await run(["pass", "open", SIGN.slice(0, 8)])).id).toBe("p3");
    await run(["pass", "abandon", SIGN.slice(0, 8), "p3"]);
    expect(data<{ id: string }>(await run(["pass", "open", SIGN.slice(0, 8)])).id).toBe("p3");
    expect(data<{ id: string }>(await run(["pass", "open", SIGN.slice(0, 8)], B)).id).toBe("p4");
  });

  test("a structured artifact holds no reading; an empty pass stages nothing", async () => {
    const { run } = await setup();
    const thread = "b3387f88";
    await run(["pass", "open", thread]);
    await run(["pass", "stage", thread, "p1", "--at", "bytes=0,10", "--text", "x"]);
    const r = await run(["pass", "sign", thread, "p1"], B);
    expect(r.code).toBe(73);
    expect((r.json() as { error: { message: string } }).error.message).toContain("class");
    await run(["pass", "open", SIGN.slice(0, 8)]);
    expect((await run(["pass", "sign", SIGN.slice(0, 8), "p1"], B)).code).toBe(73);
  });
});

describe("forming", () => {
  const head = "page=1&bbox=0.1435,0.5031,0.6121,0.0975";
  const version = "page=1&bbox=0.1429,0.6906,0.0901,0.0087";
  test("a forming pass replaces the tree whole, adopts every reading or retires it, and attests structure", async () => {
    const { root, work, run } = await setup();
    await run(["pass", "open", PROC.slice(0, 8)]);
    await run(["pass", "stage", PROC.slice(0, 8), "p1", "--at", version, "--text", "Version 02.1"]);
    expect((await run(["pass", "sign", PROC.slice(0, 8), "p1"], B)).code).toBe(0);
    const tree = (extra: object = {}) =>
      Bun.YAML.stringify({
        scopes: [
          {
            form: "cover-page",
            at: "page=1",
            scopes: [
              {
                form: "heading",
                at: head,
                level: 0,
                text: "Procedure to estimate heat loss from insulated pipework over a reporting period",
                ...extra,
              },
            ],
          },
        ],
        attests: ["structure"],
      });
    await run(["pass", "open", PROC.slice(0, 8)], B);
    const f = join(work, "tree.yaml");
    writeFileSync(f, tree());
    expect((await ath(["--json", "pass", "stage", PROC.slice(0, 8), "p2", "--file", f], { env: B, cwd: root })).code).toBe(0);
    // the reading p1 signed is in no scope of the new tree and not retired
    const refused = await run(["pass", "sign", PROC.slice(0, 8), "p2"]);
    expect(refused.code).toBe(73);
    expect((refused.json() as { error: { message: string } }).error.message).toContain(`the reading at ${version} is adopted by no scope`);
    writeFileSync(f, Bun.YAML.stringify({ ...(Bun.YAML.parse(tree()) as object), retire: [version] }));
    await ath(["pass", "stage", PROC.slice(0, 8), "p2", "--file", f], { env: B, cwd: root });
    const ok = await run(["pass", "sign", PROC.slice(0, 8), "p2"]);
    expect(ok.code, ok.stdout).toBe(0);
    const r = record(root, PROC);
    expect(r.readings).toBeUndefined();
    expect(r.passes!.p2).toMatchObject({ by: "reader-b", verify: "reader-a", attests: ["structure"] });
    expect(r.passes!.p2!.over).toBeUndefined();
    expect(data<{ stage: string }>(await run(["record", PROC.slice(0, 8)])).stage).toBe("formed");
    // a partial pass re-reads a scope at its address and mints nothing
    await run(["pass", "open", PROC.slice(0, 8)]);
    await run(["pass", "stage", PROC.slice(0, 8), "p3", "--at", "page=2&bbox=0.1,0.1,0.5,0.1", "--text", "new"]);
    expect((await run(["pass", "sign", PROC.slice(0, 8), "p3"], B)).code).toBe(73);
    await run(["pass", "abandon", PROC.slice(0, 8), "p3"]);
    await run(["pass", "open", PROC.slice(0, 8)]);
    await run([
      "pass",
      "stage",
      PROC.slice(0, 8),
      "p3",
      "--at",
      head,
      "--text",
      "Procedure to estimate heat loss from insulated pipework over a reporting period",
    ]);
    expect((await run(["pass", "sign", PROC.slice(0, 8), "p3"], B)).code).toBe(0);
    expect(record(root, PROC).passes!.p3!.over).toEqual([head]);
  });

  test("the checks refuse a tree: a scope with no reading its form reads, an undeclared field, a designator its pattern denies, an unknown form", async () => {
    const { root, work, run } = await setup();
    const attempt = async (scopes: object[]) => {
      await run(["pass", "open", PROC.slice(0, 8)]);
      const f = join(work, "t.yaml");
      writeFileSync(f, Bun.YAML.stringify({ scopes, attests: ["structure"] }));
      await ath(["pass", "stage", PROC.slice(0, 8), "p1", "--file", f], { env: A, cwd: root });
      const r = await run(["pass", "sign", PROC.slice(0, 8), "p1"], B);
      await run(["pass", "abandon", PROC.slice(0, 8), "p1"]);
      return r.code ? (r.json() as { error: { message: string } }).error.message : "";
    };
    expect(await attempt([{ form: "heading", at: head }])).toContain("reads text, but the scope has no reading under it");
    expect(await attempt([{ form: "heading", at: head, text: "x", colour: "red" }])).toContain("`colour` is not a field");
    expect(await attempt([{ form: "heading", at: head, text: "x", num: "five" }])).toContain("is not as its pattern says");
    expect(await attempt([{ form: "chapter", at: head, text: "x" }])).toContain("chapter is not a form");
    expect(await attempt([{ form: "line", at: "page=9", text: "x" }])).toContain("past its 8 pages");
    expect(
      await attempt([
        { form: "line", at: head, text: "a" },
        { form: "line", at: head, text: "b" },
      ]),
    ).toContain("two scopes share this address");
  });
});

describe("the reading check", () => {
  test("advises where a reading diverges from the hint at its address, and never blocks", async () => {
    const { root, run } = await setup();
    await run(["pass", "open", PROC.slice(0, 8)]);
    await run(["pass", "stage", PROC.slice(0, 8), "p1", "--at", "page=1&bbox=0.1429,0.6906,0.0901,0.0087", "--text", "Version 02.1"]);
    await run(["pass", "stage", PROC.slice(0, 8), "p1", "--at", "page=1&bbox=0.1433,0.1928,0.0591,0.0103", "--text", "HL-03"]);
    const s = await run(["pass", "sign", PROC.slice(0, 8), "p1"], B);
    expect(s.code, s.stdout).toBe(0);
    const adv = data<{ advisories: { at: string; state: string; detail?: string }[] }>(s).advisories;
    expect(adv).toEqual([expect.objectContaining({ at: "page=1&bbox=0.1433,0.1928,0.0591,0.0103", state: "diverges" })]);
    const rd = data<{ advisories: { state: string; at: string; rev: string }[]; unread: unknown[] }>(
      await run(["readings", PROC.slice(0, 8)]),
    );
    expect(rd.advisories.map((x) => x.state).sort()).toEqual(["agrees", "diverges"]);
    // the owner accepts the divergence: known, and it no longer recurs as one
    const d = rd.advisories.find((x) => x.state === "diverges")!;
    const acc = await ath(["rule", "accept", `ath://${PROC}?${d.at}`, "--rev", d.rev, "--why", "the cover misprints it"], {
      env: { ATH_ACTOR: "owner" },
      tty: true,
      cwd: root,
      confirm: async () => "rule accept",
    });
    expect(acc.code, acc.stderr).toBe(0);
    expect(
      data<{ advisories: { state: string }[] }>(await run(["readings", PROC.slice(0, 8)]))
        .advisories.map((x) => x.state)
        .sort(),
    ).toEqual(["accepted", "agrees"]);
    expect(rd.unread.length).toBeGreaterThan(100);
    const img = data<{ advisories: { state: string }[] }>(
      await (async () => {
        await run(["pass", "open", SIGN.slice(0, 8)]);
        await run(["pass", "stage", SIGN.slice(0, 8), "p1", "--at", "bbox=0.0667,0.1786,0.6022,0.1548", "--text", "RETURNS ONLY"]);
        await run(["pass", "sign", SIGN.slice(0, 8), "p1"], B);
        return run(["readings", SIGN.slice(0, 8)]);
      })(),
    );
    expect(img.advisories.map((x) => x.state)).toEqual(["no hint"]);
  });
});

describe("an extension", () => {
  test("never judges its base's artifacts: reading one is demand on the base", async () => {
    const { root: base, run } = await setup();
    void run;
    const git = (...a: string[]) =>
      Bun.spawnSync(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", ...a], { cwd: base });
    git("init", "-q");
    git("add", "-A");
    git("commit", "-q", "-m", "base");
    const ext = join(scratch(), "private");
    expect((await ath(["instance", "init", ext, "--extends", base], { env: A })).code).toBe(0);
    const r = await ath(["--json", "pass", "open", SIGN.slice(0, 8)], { env: A, cwd: ext });
    expect(r.code).toBe(73);
    expect((r.json() as { error: { message: string } }).error.message).toContain("demand on the base");
  });
});
