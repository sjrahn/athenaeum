// mock.ts — writes a mock instance pair in the specification's layout (spec/athenaeum.md §4, §5): a public
// standalone instance `reference` and a private extension `household` that builds on it, plus the host state
// they share. Everything is generated from committed fixtures under testdata/synthetic/ and the regression
// ontology; the output (testdata/mock/) is never tracked. Run: bun testdata/mock.ts
//
// It writes the files by hand to show the layout; it is not the tool. Values a pass or a harvest would author
// are written here the way they would be.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { attesterFor } from "../ath/src/engine/ops/registry.ts";
import "../ath/src/engine/ops/index.ts";
import { sniffMime } from "../ath/src/engine/ops/sniff.ts";
import { blake3Hex } from "../ath/src/lib/hash.ts";

const HERE = import.meta.dir;
const SYN = join(HERE, "synthetic");
const ONTO = join(HERE, "ontology");
const OUT = join(HERE, "mock");
const DATE = "2026-03-20";

// ── canonical form (§6.4.2): at|subject, predicate, then every other key in code-point order ──────────────────────
type J = Record<string, unknown>;
const sortKeys = (v: unknown): unknown =>
  Array.isArray(v)
    ? v.map(sortKeys)
    : v && typeof v === "object"
      ? Object.fromEntries(
          Object.keys(v as J)
            .sort()
            .map((k) => [k, sortKeys((v as J)[k])]),
        )
      : v;
const canon = (line: J): string => {
  const head = ["at", "subject", "predicate"].filter((k) => k in line);
  const rest = Object.keys(line)
    .filter((k) => !head.includes(k))
    .sort();
  return JSON.stringify(Object.fromEntries([...head, ...rest].map((k) => [k, sortKeys(line[k])])));
};
const jsonl = (lines: J[]): string =>
  `${lines
    .map(canon)
    .sort()
    .join("\n")}\n`;

const write = (path: string, text: string | Uint8Array) => {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, text);
};
const yaml = (o: J, indent = ""): string =>
  Object.entries(o)
    .map(([k, v]) =>
      v && typeof v === "object" && !Array.isArray(v)
        ? `${indent}${k}:\n${yaml(v as J, `${indent}  `)}`
        : `${indent}${k}: ${Array.isArray(v) ? `[${v.join(", ")}]` : v}\n`,
    )
    .join("");

const rev = async (body: string) => `b3:${(await blake3Hex(body)).slice(0, 16)}`;
const shard = async (name: string, n = 2) => (await blake3Hex(name)).slice(0, n);

// ── an instance being written ─────────────────────────────────────────────────────────────────────────────────────
class Instance {
  records = new Map<string, J[]>();
  concepts = new Map<string, J[]>();
  terms = new Map<string, J[]>();
  rulings: J[] = [];
  stores = new Map<string, J>();
  policies = new Map<string, J>();
  constructor(
    readonly dir: string,
    readonly config: J,
  ) {}
  record(b3: string, ...lines: J[]) {
    this.records.set(b3, [...(this.records.get(b3) ?? []), ...lines]);
  }
  concept(name: string, ...lines: J[]) {
    this.concepts.set(name, [...(this.concepts.get(name) ?? []), ...lines.map((l) => ({ subject: name, ...l }))]);
  }
  term(name: string, ...lines: J[]) {
    this.terms.set(name, [...(this.terms.get(name) ?? []), ...lines.map((l) => ({ subject: name, ...l }))]);
  }
  async flush() {
    write(join(this.dir, "athenaeum.yaml"), yaml(this.config));
    for (const [t, ls] of this.terms) write(join(this.dir, "terms", `${t}.jsonl`), jsonl(ls));
    for (const [b3, ls] of this.records) write(join(this.dir, "records", b3.slice(0, 2), `${b3}.jsonl`), jsonl(ls));
    for (const [n, ls] of this.concepts) write(join(this.dir, "concepts", await shard(n), `${n}.jsonl`), jsonl(ls));
    for (const [n, s] of this.stores) write(join(this.dir, "stores", `${n}.yaml`), yaml(s));
    for (const [n, p] of this.policies) write(join(this.dir, "policies", `${n}.yaml`), yaml(p));
    if (this.rulings.length) write(join(this.dir, "rulings.jsonl"), jsonl(this.rulings));
  }
}

// ── the host: a local store under XDG data, access under XDG config, per-instance state under XDG state ─────────
const HOST = join(OUT, "host");
const LOCAL = join(HOST, "data/athenaeum/artifacts");
const place = (b3: string, bytes: Uint8Array) => write(join(LOCAL, b3.slice(0, 2), b3), bytes);

/** properties (§8.1): the format's facts, by the format's properties op; a container's constituents. */
async function properties(bytes: Uint8Array, name: string): Promise<{ mime: string; line: J; parts: { path: string; blake3: string; bytes: Uint8Array }[] }> {
  const sniffed = sniffMime(bytes, name);
  const mime = sniffed === "text/plain" && /\.ya?ml$/.test(name) ? "application/yaml" : sniffed;
  const r = mime === "application/yaml" ? null : await attesterFor(mime)?.(bytes, mime);
  const value: J = { ...(r?.value ?? { mime, bytes: bytes.length, encoding: "utf-8" }) };
  delete value.sha256;
  delete value.md5;
  const parts: { path: string; blake3: string; bytes: Uint8Array }[] = [];
  for (const m of r?.members ?? []) parts.push({ path: m.path, blake3: m.blake3 ?? (await blake3Hex(m.bytes)), bytes: m.bytes });
  if (mime === "text/html") parts.push(...(await dataUris(bytes)));
  delete value.members;
  if (parts.length) value.constituents = parts.map((p) => ({ path: p.path, blake3: p.blake3 }));
  const family = mime.split("/")[1]!.replace(/^x-/, "").split("+")[0]!;
  return { mime, line: { at: "whole", predicate: "properties", value, by: `${family}.properties@1` }, parts };
}

/** Every `data:` URI in markup is a constituent; its path is the URI's byte span (§10.3). */
async function dataUris(bytes: Uint8Array) {
  const text = new TextDecoder("latin1").decode(bytes);
  const out: { path: string; blake3: string; bytes: Uint8Array }[] = [];
  for (const m of text.matchAll(/data:([a-z0-9.+/-]*)(;base64)?,([^"')\s]+)/gi)) {
    const payload = m[2] ? Uint8Array.from(Buffer.from(m[3]!, "base64")) : new TextEncoder().encode(decodeURIComponent(m[3]!));
    if (!payload.length) continue;
    out.push({ path: `${m.index}-${m.index! + m[0].length}`, blake3: await blake3Hex(payload), bytes: payload });
  }
  return out;
}

/** The byte span of the first element matching `open`, start tag to end tag (§10.4.4). */
function span(bytes: Uint8Array, open: string, tag: string): string {
  const text = new TextDecoder("latin1").decode(bytes);
  const a = text.indexOf(open);
  if (a < 0) throw new Error(`no ${open}`);
  const close = `</${tag}>`;
  const b = text.indexOf(close, a) + close.length;
  return `bytes=${a},${b}`;
}

/** Ingest: properties, the artifact placed in the local store, the receipt and any delivered testimony (§9). */
async function ingest(inst: Instance, bytes: Uint8Array, name: string, testimony: Uint8Array | null, actor: string) {
  const b3 = await blake3Hex(bytes);
  const p = await properties(bytes, name);
  inst.record(b3, p.line);
  place(b3, bytes);
  const delivered: string[] = [];
  if (testimony) {
    const t3 = await blake3Hex(testimony);
    const tp = await properties(testimony, `${name}.testimony.yaml`);
    inst.record(t3, tp.line, { at: "whole", predicate: "testimony", value: `ath://${b3}`, by: "ath.ingest@1" });
    place(t3, testimony);
    delivered.push(t3);
  }
  const receipt = new TextEncoder().encode(`${JSON.stringify({ actor, name, received: `${DATE}T09:14:03Z`, testimony: delivered })}\n`);
  const r3 = await blake3Hex(receipt);
  const rp = await properties(receipt, "receipt.json");
  inst.record(r3, rp.line, { at: "whole", predicate: "testimony", value: `ath://${b3}`, by: "ath.ingest@1" });
  for (const t of delivered) inst.record(r3, { at: "whole", predicate: "testimony", value: `ath://${t}`, by: "ath.ingest@1" });
  place(r3, receipt);
  return { b3, parts: p.parts };
}

/** Copy a regression term (and what it refines) into an instance's terms/, in the new form. */
function copyTerm(inst: Instance, name: string, seen = new Set<string>()) {
  if (seen.has(name) || inst.terms.has(name)) return;
  seen.add(name);
  const path = join(ONTO, `${name}.claims.jsonl`);
  if (!existsSync(path)) throw new Error(`no regression term ${name}`);
  const lines = readFileSync(path, "utf8")
    .split("\n")
    .filter(Boolean)
    .map((l) => JSON.parse(l) as J)
    .map((l) => (l.predicate === "chrome" && Array.isArray(l.value) ? { ...l, value: { selector: (l.value as string[]).join(", ") } } : l));
  inst.terms.set(name, lines);
  for (const l of lines) if (l.predicate === "refines") copyTerm(inst, String(l.value), seen);
}

// ══ reference — public, standalone ════════════════════════════════════════════════════════════════════════════════
rmSync(OUT, { recursive: true, force: true });
const ref = new Instance(join(OUT, "reference"), {
  id: "3b8f1d2e-9a4c-4f6b-8e2d-5c7a1b9e0f43",
  name: "reference",
  tier: "public",
  shard: { records: 2, concepts: 2 },
});
for (const t of ["unit", "document", "data", "container", "lossy", "image", "media", "listing-page", "listing-fact", "price", "paragraph", "figure"])
  copyTerm(ref, t);
ref.term("testimony", { predicate: "refines", value: "data" }, { predicate: "definition", value: "what a producer said about other artifacts: where, when, by what and why they were found" });
ref.term(
  "receipt",
  { predicate: "refines", value: "testimony" },
  { predicate: "definition", value: "the instance's own testimony of an ingest" },
  { predicate: "matches", value: { mime: "application/json", selector: "/actor" } },
  { predicate: "matches", value: { mime: "application/json", selector: "/received" } },
  { predicate: "select", value: { selector: "/actor", term: "producer" } },
  { predicate: "field", value: { name: "received", kind: "datetime", required: true } },
);
ref.term(
  "web-capture",
  { predicate: "refines", value: "testimony" },
  { predicate: "definition", value: "a page capture's sidecar: the page's address, the capturing tool, why it was captured" },
  { predicate: "matches", value: { mime: "application/yaml", selector: "/source/uri" } },
  { predicate: "select", value: { selector: "/source/uri", term: "source", field: "uri", attr: "" } },
  { predicate: "select", value: { selector: "/producer", term: "producer", field: "tool", attr: "tool" } },
  { predicate: "select", value: { selector: "/context", term: "context" } },
  { predicate: "field", value: { name: "uri", kind: "string", required: true } },
  { predicate: "field", value: { name: "tool", kind: "string", required: true } },
);
ref.term(
  "residence",
  { predicate: "refines", value: "unit" },
  { predicate: "definition", value: "a dwelling offered or held: its address, its price, its rooms" },
  { predicate: "owes", value: ["address", "price", "bedrooms", "tenure"] },
  { predicate: "functional", value: ["price", "bedrooms", "tenure"] },
);

const listingBytes = readFileSync(join(SYN, "cottage-listing.html"));
const captureSidecar = new TextEncoder().encode(
  [
    "source:",
    "  uri: https://homes.example.invalid/listing/12-quay-street",
    "producer:",
    "  tool: page-capture 4.2",
    "  host: capture-box",
    "  fetched: 2026-03-19T21:40:00Z",
    "context: house hunting, Port Ellen",
    "",
  ].join("\n"),
);
const listing = await ingest(ref, listingBytes, "cottage-listing.html", captureSidecar, "reader-a");
const L = `ath://${listing.b3}`;
const priceAt = span(listingBytes, '<span class="amount">', "span");
const bedsAt = span(listingBytes, '<li class="beds">', "li");
const tenureAt = span(listingBytes, '<li class="tenure">', "li");
const titleAt = span(listingBytes, '<h1 class="listing-title">', "h1");
const harvest = "harvest:listing-page@a835a5";
ref.concept(
  "12-quay-street-port-ellen",
  { predicate: "term", value: "residence", by: harvest },
  { predicate: "manifested_by", value: `${L}?whole`, by: harvest },
  { predicate: "address", value: "12 Quay Street, Port Ellen", evidence: [{ anchor: `${L}?${titleAt}&text`, quote: "12 Quay Street, Port Ellen", kind: "authoritative", mode: "stated", reading: "derived:html.text@1" }], by: harvest },
  { predicate: "price", value: "£313,000", evidence: [{ anchor: `${L}?${priceAt}&text`, quote: "£313,000", kind: "authoritative", mode: "stated", reading: "derived:html.text@1" }], by: harvest },
  { predicate: "bedrooms", value: "2", evidence: [{ anchor: `${L}?${bedsAt}&text`, quote: "2 bedrooms", kind: "authoritative", mode: "stated", reading: "derived:html.text@1" }], by: harvest },
  { predicate: "tenure", value: "Freehold", evidence: [{ anchor: `${L}?${tenureAt}&text`, quote: "Freehold", kind: "authoritative", mode: "stated", reading: "derived:html.text@1" }], by: harvest },
);
ref.stores.set("mirror", { id: "8c2e4a1f-0b3d-4c5e-9f7a-2d1e6b8c4a90", driver: "rclone", role: "managed", tags: ["object", "online", "country:gb", "city:glasgow"], encryption: "none" });
ref.policies.set("public-twice", { select: { tier: "public" }, require: { copies: 2, where: { not: ["local"] }, distinct: "city" }, verify: "180d" });
ref.rulings.push({ subject: "ath:ruling/r1", predicate: "seek", value: { select: { term: "residence" }, owes: ["council_tax_band"], why: "compare running costs before viewing" }, by: "owner", date: DATE });
await ref.flush();

// ══ household — private, extends reference ════════════════════════════════════════════════════════════════════════
const refCommit = "5f2a9c1e7d3b40a86e1f2c9b7d4a3e5f60812c7d";
const home = new Instance(join(OUT, "household"), {
  id: "0f4c2a8e-7b1d-4e5a-9c3f-6d2e8b1a4c70",
  name: "household",
  tier: "private",
  shard: { records: 2, concepts: 2 },
  extends: { path: "../reference", commit: refCommit },
  audiences: { family: ["private"] },
});
home.term(
  "drive-export",
  { predicate: "refines", value: "testimony" },
  { predicate: "definition", value: "a cloud drive's export sidecar: the account and folder exported, when, how much of it" },
  { predicate: "matches", value: { mime: "application/yaml", selector: "/origin_fields/folder" } },
  { predicate: "select", value: { selector: "/origin_fields/account", term: "source", field: "account", attr: "" } },
  { predicate: "select", value: { selector: "/origin_fields/exported_at", term: "producer", field: "exported", attr: "" } },
  { predicate: "field", value: { name: "account", kind: "string", required: true } },
);
home.term(
  "berth-list",
  { predicate: "refines", value: "data" },
  { predicate: "definition", value: "a list of moorings: berth, vessel, length" },
  { predicate: "matches", value: { mime: "text/csv", first_row: ["Berth", "Vessel", "Length (m)"] } },
  { predicate: "derivation", value: "csv.parse@1" },
  { predicate: "shape", value: { header: 0, term: "header" } },
  { predicate: "shape", value: { rows: "berth-row" } },
  { predicate: "concept", value: { term: "berth", key: "Berth", slug: "berth-{key}", claims: { vessel: "Vessel", length_m: "Length (m)" } } },
);
home.term("berth-row", { predicate: "refines", value: "unit" }, { predicate: "reads", value: "cells" });
home.term("berth", { predicate: "refines", value: "unit" }, { predicate: "definition", value: "a mooring place and what lies in it" }, { predicate: "owes", value: ["vessel", "length_m"] });
home.term("mooring-plan", { predicate: "refines", value: "document" }, { predicate: "definition", value: "a harbour's plan of berths for a season" });

const zipBytes = readFileSync(join(SYN, "drive-folder.zip"));
const zipSidecar = readFileSync(join(SYN, "drive-folder.zip.capture.yaml"));
const drive = await ingest(home, zipBytes, "drive-folder.zip", zipSidecar, "reader-a");
const part = (suffix: string) => drive.parts.find((p) => p.path.endsWith(suffix))!;

// a pass read the plan's title: the PDF constituent now has a record; the CSV, the notes and the photo do not
const plan = part("Mooring plan 2026.pdf");
const planProps = await properties(plan.bytes, "Mooring plan 2026.pdf");
const tmp = mkdtempSync(join(process.env.TMPDIR ?? tmpdir(), "mock-"));
writeFileSync(join(tmp, "p.pdf"), plan.bytes);
const bbox = spawnSync("pdftotext", ["-bbox-layout", join(tmp, "p.pdf"), "-"], { encoding: "utf8" }).stdout;
rmSync(tmp, { recursive: true, force: true });
const page = /<page width="([\d.]+)" height="([\d.]+)"/.exec(bbox)!;
const line = /<line xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">/.exec(bbox)!;
const [W, H] = [Number(page[1]), Number(page[2])];
const [x0, y0, x1, y1] = [1, 2, 3, 4].map((i) => Number(line[i]));
const r4 = (n: number) => Math.round(n * 1e4) / 1e4;
const headAt = `page=1&bbox=${r4(x0! / W)},${r4(y0! / H)},${r4((x1! - x0!) / W)},${r4((y1! - y0!) / H)}`;
const title = "Mooring plan 2026";
home.record(
  plan.blake3,
  planProps.line,
  { at: "whole", predicate: "pass", value: { id: "p1", by: "reader-a", verify: "reader-b", ontology: "b3:c41d0e2a9b7f3165", date: DATE } },
  { at: "whole", predicate: "manifests", term: "mooring-plan", pass: "p1" },
  { at: headAt, predicate: "manifests", term: "heading", level: 0, pass: "p1" },
  { at: headAt, predicate: "in", value: { at: "whole", ord: 0 }, pass: "p1" },
  { at: headAt, predicate: "reads_as", aspect: "text", body: title, rev: await rev(title), pass: "p1" },
);

// harvested berths cite the CSV constituent by its own hash — its record stays derived
const csv = part("Berth list.csv");
const C = `ath://${csv.blake3}`;
const bh = "harvest:berth-list@7e01b4";
for (const [row, berth, vessel, len] of [
  [1, "A1", "Lantern", "8.2"],
  [2, "A2", "Gull", "6.5"],
] as const) {
  home.concept(
    `berth-${berth.toLowerCase()}`,
    { predicate: "term", value: "berth", by: bh },
    { predicate: "manifested_by", value: `${C}?row=${row}`, by: bh },
    { predicate: "vessel", value: vessel, evidence: [{ anchor: `${C}?row=${row}&col=1`, quote: vessel, kind: "authoritative", mode: "stated", reading: "derived:csv.parse@1" }], by: bh },
    { predicate: "length_m", value: len, evidence: [{ anchor: `${C}?row=${row}&col=2`, quote: len, kind: "authoritative", mode: "stated", reading: "derived:csv.parse@1" }], by: bh },
  );
}

home.stores.set("nas", { id: "6b1f0c52-5d0e-4a8e-9c1e-2f0d6f9b2a71", driver: "rclone", role: "managed", tags: ["hdd", "online", "country:ca", "city:winnipeg"], encryption: "none", capacity: "8TB" });
home.stores.set("offsite", { id: "e3a7c9d1-4f2b-4b6e-8a0c-7d5e1f3b9c26", driver: "rclone", role: "managed", tags: ["object", "online", "country:ca", "city:toronto", "private-ok"], encryption: "client" });
home.stores.set("phone-share", { id: "a9d4e6f2-1c3b-4e8a-b7d5-0f2c6e9a1b38", driver: "local", role: "observed", tags: ["phone", "local"], links: ["reflink", "hardlink"] });
home.policies.set("household-in-canada", { select: { tier: "private" }, require: { copies: 2, where: { not: ["local"] }, distinct: "city" }, confine: { all: ["country:ca"] }, verify: "90d" });
home.policies.set("sessions-twice", { select: { origin: "agent-session" }, require: { copies: 2, where: { all: ["private-ok"] } } });
const photo = part("Quay photo.png");
home.rulings.push(
  { subject: "ath:ruling/r1", predicate: "seek", value: { select: { term: "berth" }, owes: ["vessel", "length_m"], why: "which berth is ours next season" }, by: "owner", date: DATE },
  { subject: "ath:ruling/r2", predicate: "decline", value: { on: `ath://${photo.blake3}`, demand: "reading", why: "a harbour snapshot, nothing to read" }, by: "owner", date: DATE },
);
await home.flush();

// host access, and the per-instance state directories
write(
  join(HOST, "config/athenaeum/access.yaml"),
  [
    "6b1f0c52-5d0e-4a8e-9c1e-2f0d6f9b2a71: { remote: 'nas:athenaeum' }",
    "e3a7c9d1-4f2b-4b6e-8a0c-7d5e1f3b9c26: { remote: 'offsite-crypt:' }",
    "8c2e4a1f-0b3d-4c5e-9f7a-2d1e6b8c4a90: { remote: 'mirror:reference' }",
    "a9d4e6f2-1c3b-4e8a-b7d5-0f2c6e9a1b38: { path: /mnt/phone-share }",
    "",
  ].join("\n"),
);
for (const id of [ref.config.id, home.config.id]) mkdirSync(join(HOST, "state/athenaeum/instances", String(id), "passes"), { recursive: true });

const tree = spawnSync("find", [".", "-not", "-path", "."], { cwd: OUT, encoding: "utf8" }).stdout.split("\n").filter(Boolean).sort();
console.log(`wrote ${OUT}\n${tree.join("\n")}`);
