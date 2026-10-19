// instance.ingest.test.ts — an instance from init, ingest end to end (§19.5): admission before placement (§9.5), the
// local store and the index (§18.2.3, §18.4), the receipt (§9.3), the record's projection written once and extended
// at every later delivery (§8.1), an extension over a base read from git at its pin (§4), holdings, record,
// provenance through a container (§9.6), check (§19.2.2), reshard (§5.2) and sweep.
import { describe, expect, test } from "bun:test";
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { emitRecord, loadRecord } from "@ath/engine/record/document.ts";
import { hostPaths } from "@ath/kit/xdg.ts";
import { ath, scratch, TESTDATA } from "./harness.ts";

const SYN = join(TESTDATA, "synthetic");
const EXPECTED = join(import.meta.dir, "fixtures", "expected");
const ZIP = "da7b858a7acc71ea1953f162369503c564bce9e6ec59ad1b717c6864ccaf34f0";
const env = { ATH_ACTOR: "reader-a" };
type Env<D> = { ok: boolean; data: D; error?: { code: string; message: string; data?: unknown } };
const json = <D>(r: { json: () => unknown }) => r.json() as Env<D>;
const git = (cwd: string, ...args: string[]) => {
  const r = Bun.spawnSync(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", ...args], {
    cwd,
    stdout: "pipe",
    stderr: "pipe",
  });
  if (r.exitCode !== 0) throw new Error(r.stderr.toString());
  return r.stdout.toString().trim();
};

async function init(dir: string, ...flags: string[]) {
  const r = await ath(["--json", "instance", "init", dir, ...flags], { env });
  expect(r.code, r.stdout + r.stderr).toBe(0);
  return dir;
}

/** A working directory holding copies of fixtures, so testimony beside them is the test's own. */
function stage(...names: string[]): string {
  const d = scratch();
  for (const n of names) copyFileSync(join(SYN, n), join(d, n));
  return d;
}

describe("instance init", () => {
  test("a standalone instance: athenaeum.yaml, the empty directories, the one property the tooling relies on", async () => {
    const root = await init(join(scratch(), "reference"));
    const cfg = readFileSync(join(root, "athenaeum.yaml"), "utf8");
    expect(cfg).toMatch(/^id: [0-9a-f-]{36}\nname: reference\nshard: \{records: 2, entities: 2\}\n$/);
    for (const d of [
      "corpus/forms",
      "corpus/shapes",
      "corpus/records",
      "graph/kinds",
      "graph/properties",
      "graph/entities",
      "stores",
      "policies",
    ])
      expect(existsSync(join(root, d))).toBe(true);
    expect(readFileSync(join(root, "graph/properties/source.jsonl"), "utf8")).toBe(
      '{"pred":"authority","val":true}\n{"pred":"definition","val":"an artifact that is an authoritative source for the entity that carries it"}\n{"pred":"range","val":"artifact"}\n',
    );
    expect((await ath(["instance", "init", root], { env })).code).toBe(73);
  });
});

describe("ingest", () => {
  test("a container with its testimony: admitted, placed, receipted, and its record written with the projection", async () => {
    const root = await init(join(scratch(), "household"));
    const work = stage("drive-folder.zip", "drive-folder.zip.capture.yaml");
    const r = await ath(["--json", "--root", root, "ingest", "drive-folder.zip", "--testimony", "drive-folder.zip.capture.yaml"], {
      env,
      cwd: work,
    });
    expect(r.code, r.stdout).toBe(0);
    const out = json<{ results: { status: string; hash: string; record: string; receipt: string; testimony: { hash: string }[] }[] }>(r)
      .data.results;
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ status: "new", hash: ZIP, record: `corpus/records/da/${ZIP}.yaml` });
    // the record, as the tool writes it: the projection and nothing judged
    const text = readFileSync(join(root, out[0]!.record), "utf8");
    expect(text).toBe(readFileSync(join(EXPECTED, "drive-folder.yaml"), "utf8"));
    // the artifact, its testimony and the receipt are in the local store, by hash
    const host = hostPaths(process.env);
    expect(existsSync(join(host.data, "artifacts", "da", ZIP))).toBe(true);
    const t = out[0]!.testimony[0]!.hash;
    expect(readFileSync(join(host.data, "testimony", t.slice(0, 2), t), "utf8")).toBe(
      readFileSync(join(SYN, "drive-folder.zip.capture.yaml"), "utf8"),
    );
    const receipt = JSON.parse(readFileSync(join(host.data, "testimony", out[0]!.receipt.slice(0, 2), out[0]!.receipt), "utf8"));
    expect(Object.keys(receipt)).toEqual(["actor", "artifact", "instance", "name", "received", "testimony"]);
    expect(receipt).toMatchObject({
      actor: "reader-a",
      artifact: ZIP,
      name: "drive-folder.zip",
      received: "2026-03-20T09:00:00Z",
      testimony: [{ hash: t, name: "drive-folder.zip.capture.yaml" }],
    });

    // met again, with the same testimony: a second receipt, no second origin
    const again = json<{ results: { status: string }[] }>(
      await ath(["--json", "--root", root, "ingest", "drive-folder.zip", "--testimony", "drive-folder.zip.capture.yaml"], {
        env,
        cwd: work,
        wall: () => new Date("2026-03-21T10:00:00Z"),
      }),
    );
    expect(again.data.results[0]!.status).toBe("met again");
    const rec = loadRecord(readFileSync(join(root, out[0]!.record), "utf8"));
    expect(rec.receipts!.map((x) => x.received)).toEqual(["2026-03-20T09:00:00Z", "2026-03-21T10:00:00Z"]);
    expect(rec.origins).toHaveLength(1);

    // holdings, record, provenance of a constituent through its container, by prefix
    const h = json<{ records: { short: string; stage: string | null }[]; assets: number; testimony: number }>(
      await ath(["--json", "holdings"], { env, cwd: root }),
    );
    expect(h.data.records).toEqual([expect.objectContaining({ short: "da7b858a", stage: null })]);
    expect(h.data.assets).toBe(4);
    const csv = "7ce98d2c";
    const rc = json<{ record: string | null; within: { container: string; path: string }[] }>(
      await ath(["--json", "record", csv], { env, cwd: root }),
    );
    expect(rc.data).toMatchObject({ record: null, within: [{ container: ZIP, path: "Harbour plans/Berth list.csv", kind: "asset" }] });
    const pv = json<{ artifact: string; within: { path: string; provenance: { origins: { producer: { tool: string } }[] } }[] }>(
      await ath(["--json", "provenance", csv], { env, cwd: root }),
    );
    expect(pv.data.within![0]!.provenance.origins[0]!.producer.tool).toBe("google-drive-export");
    expect((await ath(["record", "7c"], { env, cwd: root })).code).toBe(64);
    expect((await ath(["record", "ffffffff"], { env, cwd: root })).code).toBe(66);
  });

  test("testimony beside the file is delivered with it; the asset met alone gets a record of its own", async () => {
    const root = await init(join(scratch(), "solo"));
    const work = stage("sign.jpg");
    const sign = (await Bun.file(join(work, "sign.jpg")).bytes()) as Uint8Array;
    const { blake3Hex } = await import("@ath/kit/hash.ts");
    const hash = await blake3Hex(sign);
    writeFileSync(
      join(work, "sign.jpg.testimony.yaml"),
      `subject: b3:${hash}\nproducer: {tool: phone-camera, version: "1", at: "2026-03-19T08:00:00Z"}\nsource: {device: phone}\n`,
    );
    const r = json<{ results: { status: string; testimony: { name: string }[] }[] }>(
      await ath(["--json", "--root", root, "ingest", "sign.jpg"], { env, cwd: work }),
    );
    expect(r.data.results[0]).toMatchObject({ status: "new", testimony: [{ name: "sign.jpg.testimony.yaml" }] });
    const rec = readFileSync(join(root, "corpus/records", hash.slice(0, 2), `${hash}.yaml`), "utf8");
    expect(rec).toBe(
      [
        "intrinsics:",
        "  op: image.intrinsics@1",
        "  mime: image/jpeg",
        "  bytes: 47268",
        "  width: 900",
        "  height: 420",
        "receipts:",
        '  - {actor: reader-a, received: "2026-03-20T09:00:00Z", name: sign.jpg}',
        "origins:",
        '  - {producer: {tool: phone-camera, version: "1", at: "2026-03-19T08:00:00Z"}, source: {device: phone}}',
        "",
      ].join("\n"),
    );
  });

  test("a testimony that does not follow the contract, or is about another artifact, refuses its file and places nothing", async () => {
    const root = await init(join(scratch(), "strict"));
    const work = stage(
      "account-confirmation.pdf",
      "account-confirmation.pdf.capture.yaml",
      "drive-folder.zip.capture.yaml",
      "procedure.pdf",
    );
    const old = await ath(
      ["--json", "--root", root, "ingest", "account-confirmation.pdf", "--testimony", "account-confirmation.pdf.capture.yaml"],
      { env, cwd: work },
    );
    expect(old.code).toBe(73);
    const e = json<never>(old).error!;
    expect(e.code).toBe("CONFLICT");
    expect(e.message).toContain("`producer` is required");
    const other = await ath(["--json", "--root", root, "ingest", "procedure.pdf", "--testimony", "drive-folder.zip.capture.yaml"], {
      env,
      cwd: work,
    });
    expect(other.code).toBe(73);
    expect(json<never>(other).error!.message).toContain("not the artifact it was delivered with");
    expect(existsSync(join(root, "corpus/records/5e"))).toBe(false);
    const host = hostPaths(process.env);
    expect(existsSync(join(host.data, "artifacts", "5e", "5e6e497d934498fc49229ba8c594684114a1213426bc1ad0113718ae72794269"))).toBe(false);
  });

  test("an ingest needs an actor and an instance", async () => {
    const work = stage("sign.jpg");
    expect((await ath(["ingest", "sign.jpg"], { env: { USER: undefined }, cwd: work })).code).toBe(77);
    expect((await ath(["ingest", "sign.jpg"], { env, cwd: work })).code).toBe(78);
  });
});

describe("an extension over a base at its pin", () => {
  test("the base read from git at the pinned commit; the extension's record of a base's artifact holds only its own receipts and origins", async () => {
    const top = scratch();
    const ref = await init(join(top, "reference"));
    const work = stage("drive-folder.zip", "drive-folder.zip.capture.yaml");
    const into = await ath(["--root", ref, "ingest", "drive-folder.zip", "--testimony", "drive-folder.zip.capture.yaml"], {
      env,
      cwd: work,
    });
    expect(into.code, into.stderr).toBe(0);
    git(ref, "init", "-q");
    git(ref, "add", "-A");
    git(ref, "commit", "-q", "-m", "reference");
    const commit = git(ref, "rev-parse", "HEAD");
    const home = await init(join(top, "household"), "--extends", ref);
    expect(readFileSync(join(home, "athenaeum.yaml"), "utf8")).toContain(`extends:\n  path: "../reference"\n  commit: ${commit}\n`);
    const shown = json<{ chain: { name: string; commit: string | null; records: number }[] }>(
      await ath(["--json", "instance", "show"], { env, cwd: home }),
    );
    expect(shown.data.chain.map((c) => [c.name, c.commit, c.records])).toEqual([
      ["household", null, 0],
      ["reference", commit, 1],
    ]);
    // the base moves on after the pin; the extension still reads the pin
    writeFileSync(join(ref, "later.txt"), "after the pin\n");
    git(ref, "add", "-A");
    git(ref, "commit", "-q", "-m", "later");
    const again = json<{ results: { status: string; record: string }[] }>(
      await ath(["--json", "ingest", "drive-folder.zip"], { env: { ...env, ATHENAEUM_ROOT: home }, cwd: work }),
    );
    expect(again.data.results[0]).toMatchObject({ status: "met again", record: `corpus/records/da/${ZIP}.yaml` });
    const own = readFileSync(join(home, again.data.results[0]!.record), "utf8");
    expect(own).toBe('receipts:\n  - {actor: reader-a, received: "2026-03-20T09:00:00Z", name: drive-folder.zip}\n');
    const view = json<{ document: string }>(await ath(["--json", "show", ZIP], { env, cwd: home }));
    expect(loadRecord(view.data.document).receipts).toHaveLength(2);
    expect(loadRecord(view.data.document).intrinsics?.op).toBe("zip.intrinsics@1");
    const held = json<{ records: { instance: string }[] }>(await ath(["--json", "holdings"], { env, cwd: home }));
    expect(held.data.records[0]!.instance).toBe("reference");
    // repin is the owner's: it moves the pin to the base's HEAD
    const rp = json<{ from: string; to: string }>(await ath(["--json", "instance", "repin"], { env, cwd: home }));
    expect(rp.ok).toBe(false); // admin verbs are refused under --json
    const repin = await ath(["instance", "repin"], { env, cwd: home, tty: true, confirm: async () => "instance repin" });
    expect(repin.code, repin.stderr).toBe(0);
    expect(readFileSync(join(home, "athenaeum.yaml"), "utf8")).toContain(`commit: ${git(ref, "rev-parse", "HEAD")}`);
    // a base that is missing, or a cycle, is a configuration error
    writeFileSync(join(home, "athenaeum.yaml"), readFileSync(join(home, "athenaeum.yaml"), "utf8").replace("../reference", "../nowhere"));
    expect((await ath(["instance", "show"], { env, cwd: home })).code).toBe(78);
  });
});

describe("check, reshard, sweep", () => {
  test("check refuses a chain this tool cannot serve; reshard moves files; sweep rewrites what an older op wrote", async () => {
    const root = await init(join(scratch(), "keep"));
    const work = stage("drive-folder.zip");
    await ath(["--root", root, "ingest", "drive-folder.zip"], { env, cwd: work });
    expect((await ath(["instance", "check"], { env, cwd: root })).code).toBe(0);
    const p = join(root, "corpus/records/da", `${ZIP}.yaml`);
    const good = readFileSync(p, "utf8");
    writeFileSync(p, good.replace("zip.intrinsics@1", "zip.intrinsics@9"));
    const bad = await ath(["--json", "instance", "check"], { env, cwd: root });
    expect(bad.code).toBe(78);
    expect(json<never>(bad).error!.message).toContain("newer than this tool's zip.intrinsics@1");
    // a projection an op of another format wrote is stale: sweep lists it, then rewrites it from the local store
    const doc = loadRecord(good);
    writeFileSync(p, emitRecord({ ...doc, intrinsics: { op: "bytes.intrinsics@1", mime: "application/zip", bytes: 13759 } }));
    const listed = json<{ stale: { done: boolean }[] }>(await ath(["--json", "sweep", "--stale"], { env, cwd: root }));
    expect(listed.data.stale).toEqual([expect.objectContaining({ from: "bytes.intrinsics@1", to: "zip.intrinsics@1", done: false })]);
    const swept = json<{ stale: { done: boolean }[] }>(await ath(["--json", "sweep"], { env, cwd: root }));
    expect(swept.data.stale[0]!.done).toBe(true);
    expect(readFileSync(p, "utf8")).toBe(good);
    // reshard to one hex digit, then to none
    writeFileSync(join(root, "athenaeum.yaml"), readFileSync(join(root, "athenaeum.yaml"), "utf8").replace("records: 2", "records: 1"));
    const rs = await ath(["instance", "reshard"], { env, cwd: root, tty: true, confirm: async () => "instance reshard" });
    expect(rs.code, rs.stderr).toBe(0);
    expect(existsSync(join(root, "corpus/records/d", `${ZIP}.yaml`))).toBe(true);
    expect(existsSync(p)).toBe(false);
    mkdirSync(join(root, "corpus/records/da"), { recursive: true });
    expect((await ath(["--json", "holdings"], { env, cwd: root })).code).toBe(0);
  });
});
