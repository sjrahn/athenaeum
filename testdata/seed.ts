#!/usr/bin/env bun
// seed.ts — builds the regression instance pair with the tool itself: a public standalone instance `reference` and a
// private extension `household` built on it at a pinned commit, and the host state they share, all from committed
// fixtures under testdata/synthetic/, testdata/passes/ and the regression ontology (testdata/ontology/). Every file
// in them is written by an `ath` verb — ingest, vocab, pass, rule, store — except what the owner authors by hand:
// the ontology copied in, the policies, and the instance ids pinned so the output is the same on every machine.
//
// The pair shows the stages (§8.5): the procedure PDF is formed (readings and a tree, both complete), the listing page
// and the mooring plan inside the drive export are read where an entity cites them, the sign photograph is
// transcribed, the sheet and the thread are structured and stay at their projection, the clip lists its tracks as
// parts. Entities cite readings, a sheet's cells, a scope's field and a testimony's surface; the owner's rulings seek,
// accept and decline; stores and policies keep it all.
//
//   bun testdata/seed.ts [OUT]       (default testdata/instance/, gitignored; rebuilt from scratch)
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { buildRegistry } from "../ath/packages/cli/src/main.ts";
import { intrinsicsOf } from "../ath/packages/engine/src/formats/index.ts";
import { allPages } from "../ath/packages/engine/src/formats/pdf/words.ts";
import { runCli } from "../ath/packages/kit/src/dispatch.ts";
import { blake3Hex, short } from "../ath/packages/kit/src/hash.ts";
import { captureIo } from "../ath/packages/kit/src/io.ts";

const HERE = import.meta.dir;
const SYN = join(HERE, "synthetic");
const FAKE_RCLONE = join(HERE, "..", "ath", "test", "fixtures", "bin");
const WALL = new Date("2026-03-20T09:00:00Z");
const DATE = "2026-03-20";
type J = Record<string, unknown>;

export interface RunOut {
  code: number;
  stdout: string;
  stderr: string;
}
export type Runner = (argv: string[], o?: { actor?: string; cwd?: string; owner?: boolean }) => Promise<RunOut>;

/** The tool in this process, over a host of its own, at a fixed wall clock. */
export function inProcess(host: string): Runner {
  const registry = buildRegistry();
  const env = {
    HOME: host,
    XDG_DATA_HOME: join(host, "data"),
    XDG_STATE_HOME: join(host, "state"),
    XDG_CONFIG_HOME: join(host, "config"),
    XDG_CACHE_HOME: join(host, "cache"),
    XDG_RUNTIME_DIR: join(host, "run"),
    USER: "seed",
    PATH: process.env.PATH,
  };
  return async (argv, o = {}) => {
    const io = captureIo();
    const code = await runCli(argv, {
      registry,
      io,
      env: { ...env, ATH_ACTOR: o.actor ?? "reader-a" },
      cwd: o.cwd ?? host,
      tty: o.owner ?? false,
      session: () => null,
      confirm: o.owner ? async () => argv.filter((w) => !w.startsWith("-")).slice(0, 2).join(" ") : undefined,
      history: false,
      wall: () => WALL,
    });
    return { code, stdout: io.stdout, stderr: io.stderr };
  };
}

const A = (full: string) => `ath://${full}`;
const r4 = (n: number) => Math.round(n * 1e4) / 1e4;
const write = (path: string, text: string | Uint8Array) => {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, text);
};

/** A capture sidecar in the contract's shape (§9.4). */
const sidecar = (hash: string, uri: string, at: string, context: string) =>
  ["subject: b3:" + hash, "producer:", "  tool: page-capture", '  version: "4.2"', `  at: "${at}"`, "  host: capture-box", "source:", `  uri: ${uri}`, `context: ${context}`, ""].join("\n");

/** The byte span of an element, start tag to end tag (§10.4.5). */
function htmlSpan(bytes: Uint8Array, open: string, tag: string) {
  const text = new TextDecoder("latin1").decode(bytes);
  const a = text.indexOf(open);
  if (a < 0) throw new Error(`no ${open}`);
  return `bytes=${a},${text.indexOf(`</${tag}>`, a) + tag.length + 3}`;
}

/** The span of the JSON object that holds a key and value: the message, not the value (§11.7.1). */
function jsonObjectSpan(bytes: Uint8Array, key: string, value: string) {
  const buf = Buffer.from(bytes);
  const at = buf.indexOf(Buffer.from(`"${key}": ${JSON.stringify(value)}`));
  if (at < 0) throw new Error(`no ${key}: ${value}`);
  const a = buf.lastIndexOf(Buffer.from("{"), at);
  let depth = 0;
  for (let i = a; i < buf.length; i++) {
    if (buf[i] === 0x7b) depth++;
    else if (buf[i] === 0x7d && --depth === 0) return `bytes=${a},${i + 1}`;
  }
  throw new Error("unterminated object");
}

const ev = (anchor: string, quote: string, extra: J = {}) => ({ anchor, mode: "stated", quote, ...extra });

/** Build the pair under `out`: reference/, household/ and host/. */
export async function seed(out: string, run: Runner = inProcess(join(out, "host"))): Promise<{ reference: string; household: string; host: string }> {
  rmSync(out, { recursive: true, force: true });
  const host = join(out, "host");
  const work = join(out, "work");
  const ref = join(out, "reference");
  const home = join(out, "household");
  mkdirSync(work, { recursive: true });
  const ok = async (argv: string[], o: Parameters<Runner>[1] = {}) => {
    const r = await run(["--json", ...argv], o);
    if (r.code !== 0) throw new Error(`ath ${argv.join(" ")} → ${r.code}\n${r.stdout}${r.stderr}`);
    return (JSON.parse(r.stdout) as { data: J }).data as any;
  };
  // the owner's verbs confirm at a terminal, and print for one
  const owner = async (root: string, argv: string[]) => {
    const r = await run(argv, { actor: "owner", cwd: root, owner: true });
    if (r.code !== 0) throw new Error(`ath ${argv.join(" ")} → ${r.code}\n${r.stdout}${r.stderr}`);
  };
  const vocab = async (root: string, v: string, term: string, ...lines: J[]) => {
    const dir = { forms: "corpus/forms", shapes: "corpus/shapes", kinds: "graph/kinds", properties: "graph/properties" }[v]!;
    if ([root, ref].some((r) => existsSync(join(r, dir, `${term}.jsonl`)))) return; // the ontology or the base declares it
    await owner(root, ["vocab", "add", v, term, ...lines.map((l) => JSON.stringify(l))]);
  };
  const read = async (root: string, subject: string, readings: [string, string][], attests: string[] = []) => {
    const { id } = await ok(["pass", "open", subject], { cwd: root });
    for (const [at, text] of readings) await ok(["pass", "stage", subject, id, "--at", at, "--text", text, ...attests.flatMap((x) => ["--attests", x])], { cwd: root });
    await ok(["pass", "sign", subject, id], { actor: "reader-b", cwd: root });
  };
  const claim = async (root: string, entity: string, lines: J[], by = "reader-a", verify = "reader-b") => {
    const { id } = await ok(["pass", "open", entity], { actor: by, cwd: root });
    for (const l of lines) await ok(["pass", "stage", entity, id, "--line", JSON.stringify(l)], { actor: by, cwd: root });
    await ok(["pass", "sign", entity, id], { actor: verify, cwd: root });
  };
  const pinId = (root: string, id: string) => {
    const p = join(root, "athenaeum.yaml");
    writeFileSync(p, readFileSync(p, "utf8").replace(/^id: .*$/m, `id: ${id}`));
  };
  // a store's id is the one written into it: written here first, the declaration adopts it
  const marker = (path: string, id: string, role = "managed") => write(path, `id: ${id}\nrole: ${role}\n`);
  marker(join(host, "data", "athenaeum", "store.yaml"), "1d0b6f3e-2c4a-4e8b-9a7d-5f3c1e8b2a64");
  writeFileSync(join(host, "data", "athenaeum", "store.yaml"), "id: 1d0b6f3e-2c4a-4e8b-9a7d-5f3c1e8b2a64\nrole: managed\ntags: [local]\n");
  const PATH = process.env.PATH;
  process.env.PATH = `${FAKE_RCLONE}:${PATH}`; // the remotes are directories under host/remotes, reached through a stand-in
  try {
    // ══ reference — public, standalone ══════════════════════════════════════════════════════════════════════════
    await ok(["instance", "init", ref, "--name", "reference"]);
    pinId(ref, "3b8f1d2e-9a4c-4f6b-8e2d-5c7a1b9e0f43");
    cpSync(join(HERE, "ontology"), ref, { recursive: true });
    for (const [n, range, functional, authority] of [
      ["address", "string", true, false],
      ["price", "amount", true, false],
      ["source", "artifact", false, true],
      ["bedrooms", "int", true, false],
      ["tenure", "string", true, false],
      ["council-tax-band", "string", true, false],
      ["version", "string", true, false],
      ["legal-name", "string", true, false],
    ] as const)
      await vocab(ref, "properties", n, { pred: "range", val: range }, ...(functional ? [{ pred: "functional", val: true }] : []), ...(authority ? [{ pred: "authority", val: true }] : []));
    await vocab(ref, "kinds", "organization", { pred: "definition", val: "a body that acts in its own name" }, { pred: "owes", val: ["legal-name"] });
    await vocab(ref, "properties", "issued-by", { pred: "range", val: "organization" }, { pred: "functional", val: true });
    await vocab(ref, "kinds", "residence", { pred: "definition", val: "a dwelling offered or held" }, { pred: "owes", val: ["address", "price", "bedrooms", "tenure"] });
    await vocab(ref, "kinds", "standard", { pred: "definition", val: "a published method others follow" }, { pred: "owes", val: ["title", "version", "issued-by", "source"] });

    // the listing: a rendered page, read where the entity cites it and nowhere else — a record at the read stage
    const listingBytes = new Uint8Array(readFileSync(join(SYN, "cottage-listing.html")));
    const listing = await blake3Hex(listingBytes);
    write(join(work, "ref", "cottage-listing.html"), listingBytes);
    write(join(work, "ref", "cottage-listing.html.testimony.yaml"), sidecar(listing, "https://homes.example.invalid/listing/12-quay-street", "2026-03-19T21:40:00Z", "house hunting, Port Ellen"));
    const procBytes = new Uint8Array(readFileSync(join(SYN, "procedure.pdf")));
    const proc = await blake3Hex(procBytes);
    const procSidecar = sidecar(proc, "https://standards.harbour.example.invalid/hl-02/02.1/procedure.pdf", "2026-03-19T21:52:00Z", "the heat-loss procedure the office publishes");
    write(join(work, "ref", "procedure.pdf"), procBytes);
    write(join(work, "ref", "procedure.pdf.testimony.yaml"), procSidecar);
    const ingRef = await ok(["--root", ref, "ingest", "cottage-listing.html", "procedure.pdf"], { cwd: join(work, "ref") });
    const procTestimony = (ingRef.results as { hash: string; testimony: { hash: string }[] }[]).find((r) => r.hash === proc)!.testimony[0]!.hash;
    const spans: [string, string][] = [
      [htmlSpan(listingBytes, '<h1 class="listing-title">', "h1"), "12 Quay Street, Port Ellen"],
      [htmlSpan(listingBytes, '<span class="amount">', "span"), "£313,000"],
      [htmlSpan(listingBytes, '<li class="beds">', "li"), "2 bedrooms"],
      [htmlSpan(listingBytes, '<li class="tenure">', "li"), "Freehold"],
    ];
    await read(ref, listing, spans);
    const L = (i: number) => ev(`${A(listing)}?${spans[i]![0]}&text`, spans[i]![1]);
    await claim(ref, "12-quay-street-port-ellen", [
      { pred: "is", val: "residence" },
      { pred: "address", val: "12 Quay Street, Port Ellen", ev: [L(0)] },
      { pred: "price", val: "£313,000", ev: [L(1)] },
      { pred: "bedrooms", val: "2", ev: [{ ...L(2), quote: "2 bedrooms" }] },
      { pred: "tenure", val: "Freehold", ev: [L(3)] },
    ]);

    // the procedure: formed — the generated pass stages its tree and chrome rule whole; pages are addresses only
    const { id: pp } = await ok(["pass", "open", proc], { cwd: ref });
    await ok(["pass", "stage", proc, pp, "--file", join(HERE, "passes", `${proc}.p1.yaml`), "--attests", "readings", "--attests", "structure"], { cwd: ref });
    await ok(["pass", "sign", proc, pp], { actor: "reader-b", cwd: ref });
    const tree = Bun.YAML.parse(readFileSync(join(HERE, "passes", `${proc}.p1.yaml`), "utf8")) as { scopes: J[] };
    const found = new Map<string, string>();
    let tex: [string, string] | null = null;
    const walk = (ss: J[]) => {
      for (const s of ss) {
        if (typeof s.text === "string" && !found.has(s.text)) found.set(s.text, String(s.at));
        if (typeof s.tex === "string" && !tex) tex = [String(s.at), s.tex];
        if (Array.isArray(s.scopes)) walk(s.scopes as J[]);
      }
    };
    walk(tree.scopes);
    const P = (text: string, extra: J = {}) => ev(`${A(proc)}?${found.get(text)}&text`, text, extra);
    const uriSpan = (() => {
      // the `uri` value: the surface yields a mapping's values, never its keys
      const a = procSidecar.indexOf("https://");
      return `bytes=${a},${procSidecar.indexOf("\n", a)}`;
    })();
    await claim(ref, "harbour-standards-office", [
      { pred: "is", val: "organization" },
      { pred: "legal-name", val: "HARBOUR STANDARDS OFFICE", ev: [P("HARBOUR STANDARDS OFFICE")] },
    ]);
    await claim(ref, "hl-02", [
      { pred: "is", val: "standard" },
      { pred: "title", val: "Procedure to estimate heat loss from insulated pipework over a reporting period", ev: [P("Procedure to estimate heat loss from insulated pipework over a reporting period")] },
      { pred: "version", val: "02.1", ev: [P("Version 02.1")] },
      { pred: "source", val: A(proc), ev: [P("HL-02", { mode: "inferred", reason: "the document prints the standard's designation on its cover, issued by the office" })] },
      { pred: "issued-by", val: "ath://harbour-standards-office", qual: { as: "HARBOUR STANDARDS OFFICE" }, ev: [P("HARBOUR STANDARDS OFFICE")] },
    ]);
    await claim(
      ref,
      "hl-02",
      [{ pred: "source", val: A(proc), ev: [ev(`${A(procTestimony)}?${uriSpan}&text`, "https://standards.harbour.example.invalid/hl-02/02.1/procedure.pdf")] }],
      "reader-b",
      "reader-a",
    );
    marker(join(host, "remotes", "mirror", "store.yaml"), "8c2e4a1f-0b3d-4c5e-9f7a-2d1e6b8c4a90");
    await ok(["store", "add", "mirror", "--driver", "rclone", "--remote", `fake:${join(host, "remotes", "mirror")}`, "--tag", "object", "--tag", "online", "--tag", "country:gb", "--tag", "city:glasgow"], { cwd: ref });
    write(join(ref, "policies", "captures-twice.yaml"), "select: {origin: page-capture}\nrequire: {copies: 2, where: {not: [local]}, distinct: city}\nverify: 180d\n");
    await owner(ref, ["rule", "seek", "--kind", "residence", "--owes", "council-tax-band", "--why", "compare running costs before viewing"]);
    const [texAt, texBody] = tex!;
    await owner(ref, ["rule", "accept", `${A(proc)}?${texAt}`, "--rev", await short(texBody), "--why", "two-dimensional maths; the hint is in baseline order"]);
    const git = (...args: string[]) => {
      // no configuration of this host's — signing, line endings, templates — may change the commit the pair pins
      const r = Bun.spawnSync(["git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false", ...args], {
        cwd: ref,
        env: { ...process.env, GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_NOSYSTEM: "1", GIT_AUTHOR_NAME: "seed", GIT_AUTHOR_EMAIL: "seed@example.invalid", GIT_COMMITTER_NAME: "seed", GIT_COMMITTER_EMAIL: "seed@example.invalid", GIT_AUTHOR_DATE: `${DATE}T09:00:00Z`, GIT_COMMITTER_DATE: `${DATE}T09:00:00Z` },
        stdout: "pipe",
        stderr: "pipe",
      });
      if (r.exitCode !== 0) throw new Error(`git ${args.join(" ")}: ${r.stderr.toString()}`);
    };
    git("init", "-q", "-b", "main");
    git("add", "-A");
    git("commit", "-q", "-m", "reference");

    // ══ household — private, extends reference ══════════════════════════════════════════════════════════════════
    await ok(["instance", "init", home, "--name", "household", "--extends", ref]);
    pinId(home, "0f4c2a8e-7b1d-4e5a-9c3f-6d2e8b1a4c70");
    await vocab(home, "shapes", "drive-export", { pred: "definition", val: "a folder as a cloud drive exports it: what the drive's export tool delivered, recognised by its testimony" }, { pred: "matches", val: { mime: "application/zip", origin: { "/producer/tool": "google-drive-export" } } });
    await vocab(home, "shapes", "headed-sheet", { pred: "definition", val: "a CSV whose first row names its columns: Berth, Vessel, Length (m)" }, { pred: "matches", val: { mime: "text/csv", first_row: ["Berth", "Vessel", "Length (m)"] } }, { pred: "columns", val: { header: 0, form: "header" } }, { pred: "columns", val: { rows: "row" } });
    await vocab(
      home,
      "shapes",
      "messenger-thread",
      { pred: "definition", val: "one conversation as a messaging service exports it: participants, then messages" },
      { pred: "matches", val: { mime: "application/json", selector: "/participants" } },
      { pred: "matches", val: { mime: "application/json", selector: "/messages/*/sender_name" } },
      { pred: "select", val: { selector: "/messages/*", form: "message" } },
      { pred: "select", val: { selector: "/messages/*/sender_name", form: "message", field: "author" } },
      { pred: "select", val: { selector: "/messages/*/timestamp_ms", form: "message", field: "instant" } },
      { pred: "select", val: { selector: "/messages/*/content", form: "message", reads: "text" } },
    );
    await vocab(home, "properties", "display-name", { pred: "range", val: "string" }, { pred: "functional", val: true });
    await vocab(home, "properties", "length", { pred: "range", val: "decimal" }, { pred: "functional", val: true });
    await vocab(home, "kinds", "vessel", { pred: "definition", val: "a boat" }, { pred: "owes", val: ["display-name", "length"] });
    await vocab(home, "properties", "occupant", { pred: "range", val: "vessel" }, { pred: "functional", val: true });
    await vocab(home, "kinds", "berth", { pred: "definition", val: "a mooring place in a harbour" }, { pred: "owes", val: ["occupant"] });
    await vocab(home, "kinds", "person", { pred: "definition", val: "a human being" }, { pred: "owes", val: ["display-name"] });
    for (const f of ["drive-folder.zip", "drive-folder.zip.testimony.yaml", "harbour-clip.mov", "sign.jpg", "facebook-thread.json"]) cpSync(join(SYN, f), join(work, "home", f));
    const ingHome = await ok(["--root", home, "ingest", "drive-folder.zip", "harbour-clip.mov", "sign.jpg", "facebook-thread.json"], { cwd: join(work, "home") });
    const hashOf = (name: string) => (ingHome.results as { file: string; hash: string }[]).find((r) => r.file === name)!.hash;
    const constituents = (await intrinsicsOf(new Uint8Array(readFileSync(join(SYN, "drive-folder.zip"))), "application/zip")).constituents;
    const member = (suffix: string) => constituents.find((c) => c.path.endsWith(suffix))!;
    const part = (suffix: string) => member(suffix).blake3;

    // the plan inside the zip, read for its title: that constituent alone has a record, at the read stage
    const plan = part("Mooring plan 2026.pdf");
    const first = (await allPages(await member("Mooring plan 2026.pdf").read()))[0]!.lines[0]!;
    await read(home, plan, [[`page=1&bbox=${r4(first.x0)},${r4(first.y)},${r4(first.x1 - first.x0)},${r4(first.h)}`, "Mooring plan 2026"]]);

    // a photograph of a sign, read in full: transcribed, never formed — three readings and the attestation
    await read(
      home,
      hashOf("sign.jpg"),
      [
        ["bbox=0.0667,0.1786,0.6022,0.1548", "RETURNS ONLY"],
        ["bbox=0.0667,0.4643,0.4556,0.1024", "Bay 12 - Depot 7"],
        ["bbox=0.0667,0.6976,0.6467,0.1071", "No parking 7am to 6pm"],
      ],
      ["readings"],
    );

    // berths and their vessels cite the sheet inside the zip by its own id — the sheet has no record
    const C = A(part("Berth list.csv"));
    for (const [row, berth, vessel, len] of [
      [1, "A1", "Lantern", "8.2"],
      [2, "A2", "Gull", "6.5"],
    ] as const) {
      const v = vessel.toLowerCase();
      await claim(home, v, [
        { pred: "is", val: "vessel" },
        { pred: "display-name", val: vessel, ev: [ev(`${C}?row=${row}&col=1`, vessel)] },
        { pred: "length", val: len, ev: [ev(`${C}?row=${row}&col=2`, len)] },
      ]);
      await claim(home, `berth-${berth.toLowerCase()}`, [
        { pred: "is", val: "berth" },
        { pred: "occupant", val: `ath://${v}`, qual: { as: vessel }, ev: [ev(`${C}?row=${row}&col=1`, vessel)] },
      ]);
    }

    // a conversation: structure by pointer selects; a person cited through the first message's `author` field
    const threadBytes = new Uint8Array(readFileSync(join(SYN, "facebook-thread.json")));
    const T = A(hashOf("facebook-thread.json"));
    const sender = (JSON.parse(new TextDecoder().decode(threadBytes)) as { messages: { sender_name: string }[] }).messages[0]!.sender_name;
    await claim(home, sender.toLowerCase().replace(/[^a-z0-9]+/g, "-"), [
      { pred: "is", val: "person" },
      { pred: "display-name", val: sender, ev: [ev(`${T}?${jsonObjectSpan(threadBytes, "sender_name", sender)}`, sender, { binding: "field:author" })] },
    ]);

    marker(join(host, "remotes", "nas", "store.yaml"), "6b1f0c52-5d0e-4a8e-9c1e-2f0d6f9b2a71");
    marker(join(host, "remotes", "offsite", "store.yaml"), "e3a7c9d1-4f2b-4b6e-8a0c-7d5e1f3b9c26");
    marker(join(host, "phone-share", ".athenaeum", "store.yaml"), "a9d4e6f2-1c3b-4e8a-b7d5-0f2c6e9a1b38", "observed");
    await ok(["store", "add", "nas", "--driver", "rclone", "--remote", `fake:${join(host, "remotes", "nas")}`, "--tag", "hdd", "--tag", "online", "--tag", "country:ca", "--tag", "city:winnipeg", "--capacity", "8TB"], { cwd: home });
    await ok(["store", "add", "offsite", "--driver", "rclone", "--remote", `fake:${join(host, "remotes", "offsite")}`, "--tag", "object", "--tag", "online", "--tag", "country:ca", "--tag", "city:toronto", "--tag", "private-ok", "--encryption", "client"], { cwd: home });
    await ok(["store", "add", "phone-share", "--role", "observed", "--path", join(host, "phone-share"), "--tag", "phone", "--tag", "local", "--link", "reflink", "--link", "hardlink"], { cwd: home });
    write(join(home, "policies", "exports-in-canada.yaml"), 'select: {origin: google-drive-export}\nrequire: {copies: 2, where: {not: [local]}, distinct: city}\nconfine: {all: ["country:ca"]}\nverify: 90d\n');
    write(join(home, "policies", "testimony-twice.yaml"), "select: {testimony: true}\nrequire: {copies: 2, where: {all: [private-ok]}}\n");
    await owner(home, ["rule", "seek", "--kind", "berth", "--owes", "occupant", "--why", "which berth is ours next season"]);
    await owner(home, ["rule", "decline", A(part("Quay photo.png")), "--demand", "reading", "--why", "a harbour snapshot, nothing to read"]);
  } finally {
    process.env.PATH = PATH;
    rmSync(work, { recursive: true, force: true });
  }
  return { reference: ref, household: home, host };
}

if (import.meta.main) {
  const out = process.argv[2] ?? join(HERE, "instance");
  const r = await seed(out);
  console.log(`wrote ${r.reference}\n      ${r.household}\n      ${r.host}`);
}
