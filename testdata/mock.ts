// mock.ts — writes a mock instance pair in the specification's layout (spec/athenaeum.md §4, §5): a public
// standalone instance `reference` and a private extension `household` that builds on it, plus the host state
// they share. Everything is generated from committed fixtures under testdata/synthetic/, testdata/passes/ and the
// regression ontology; the output (testdata/mock/) is never tracked. Run: bun testdata/mock.ts
//
// It writes the files by hand to show the layout; it is not the tool. Lines an author would sign are written here
// the way a signed pass would leave them.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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
type J = Record<string, unknown>;

// ── canonical form (§6.4.2): id|at, pred, every other key in code-point order, then ev, authorship last ─────────
const AUTH = ["by", "pass"];
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
  const head = ["id", "at", "pred", "form", "in", "ord"].filter((k) => k in line);
  const tail = ["ev", ...AUTH].filter((k) => k in line);
  const mid = Object.keys(line)
    .filter((k) => !head.includes(k) && !tail.includes(k))
    .sort();
  return JSON.stringify(Object.fromEntries([...head, ...mid, ...tail].map((k) => [k, sortKeys(line[k])])));
};
const jsonl = (lines: J[]) =>
  `${[...new Set(lines.map(canon))].sort().join("\n")}\n`;
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

// ── ids (§7.1): 8 hex digits, 16 where 8 collide, the first received keeping 8 ──────────────────────────────────
const ids = new Map<string, string>();
function idOf(full: string): string {
  const known = ids.get(full);
  if (known) return known;
  const short = full.slice(0, 8);
  const taken = [...ids.values()].includes(short);
  const id = taken ? full.slice(0, 16) : short;
  ids.set(full, id);
  return id;
}
const A = (full: string) => `ath://${idOf(full)}`;

// ── the host: local store (artifacts/, testimony/), access, per-instance state ─────────────────────────────────
const HOST = join(OUT, "host");
const keep = (tree: "artifacts" | "testimony", full: string, bytes: Uint8Array) =>
  write(join(HOST, "data/athenaeum", tree, full.slice(0, 2), full), bytes);

type Vocab = "forms" | "shapes" | "kinds" | "properties";
class Instance {
  /** Terms by `<vocabulary>/<name>`: forms, kinds and properties are separate name spaces. */
  terms = new Map<string, J[]>();
  records = new Map<string, J[]>();
  entities = new Map<string, J[]>();
  rulings: J[] = [];
  stores = new Map<string, J>();
  policies = new Map<string, J>();
  holdings: J[] = [];
  constructor(
    readonly dir: string,
    readonly config: J,
  ) {}
  term(name: string, ...lines: J[]) {
    this.add("forms", name, lines);
  }
  shape(name: string, ...lines: J[]) {
    this.add("shapes", name, lines);
  }
  add(v: Vocab, name: string, lines: J[]) {
    const key = `${v}/${name}`;
    this.terms.set(key, [...(this.terms.get(key) ?? []), ...lines]);
  }
  /** The pin of one vocabulary (§11.8): term files in name order, each preceded by its name, lines sorted. */
  async pin(vocab: "corpus" | "graph", base?: Instance) {
    const want = (key: string) => (vocab === "corpus") === (key.startsWith("forms/") || key.startsWith("shapes/"));
    const all = new Map<string, J[]>();
    for (const inst of [base, this].filter(Boolean) as Instance[]) for (const [k, ls] of inst.terms) if (want(k)) all.set(k, [...(all.get(k) ?? []), ...ls]);
    const text = [...all.keys()].sort().map((n) => `${n}\n${jsonl(all.get(n)!)}`).join("");
    return `b3:${(await blake3Hex(text)).slice(0, 16)}`;
  }
  record(full: string, ...lines: J[]) {
    this.records.set(full, [...(this.records.get(full) ?? []), ...lines]);
  }
  entity(name: string, ...lines: J[]) {
    this.entities.set(name, [...(this.entities.get(name) ?? []), ...lines]);
  }
  prune(base?: Instance) {
    const have = new Set([...this.terms.keys(), ...(base ? [...base.terms.keys()] : [])].filter((k) => k.startsWith("forms/")).map((k) => k.slice(6)));
    for (const [k, ls] of this.terms) {
      if (!k.startsWith("forms/")) continue;
      this.terms.set(
        k,
        ls
          .filter((l) => l.pred !== "refines" || have.has(String(l.val)))
          .map((l) => (l.pred === "expects" ? { ...l, val: (l.val as string[]).filter((f) => have.has(f)) } : l))
          .filter((l) => l.pred !== "expects" || (l.val as string[]).length),
      );
      if (!this.terms.get(k)!.length) this.terms.set(k, [{ pred: "definition", val: k.slice(6).replace(/-/g, " ") }]);
    }
  }
  async flush(base?: Instance) {
    this.prune(base);
    const pins = { "@corpus": await this.pin("corpus", base), "@graph": await this.pin("graph", base) };
    const pinned = (ls: J[]) => JSON.parse(JSON.stringify(ls).replace(/"@(corpus|graph)"/g, (m) => JSON.stringify(pins[m.slice(1, -1) as keyof typeof pins]))) as J[];
    write(join(this.dir, "athenaeum.yaml"), yaml(this.config));
    for (const [k, ls] of this.terms) {
      const [v, name] = k.split("/") as [Vocab, string];
      write(join(this.dir, { forms: "corpus/forms", shapes: "corpus/shapes", kinds: "graph/kinds", properties: "graph/properties" }[v], `${name}.jsonl`), jsonl(ls));
    }
    for (const [full, ls] of this.records) {
      const id = idOf(full);
      write(join(this.dir, "corpus/records", id.slice(0, 2), `${id}.jsonl`), jsonl(pinned(ls)));
    }
    for (const [n, ls] of this.entities) write(join(this.dir, "graph/entities", n.slice(0, 2), `${n}.jsonl`), jsonl(pinned(ls)));
    for (const [n, s] of this.stores) write(join(this.dir, "stores", `${n}.yaml`), yaml(s));
    for (const [n, p] of this.policies) write(join(this.dir, "policies", `${n}.yaml`), yaml(p));
    if (this.rulings.length) write(join(this.dir, "rulings.jsonl"), jsonl(this.rulings));
    const state = join(HOST, "state/athenaeum/instances", String(this.config.id));
    write(join(state, "holdings.jsonl"), jsonl(this.holdings));
    mkdirSync(join(state, "passes"), { recursive: true });
  }
}

/** intrinsics (§8.1, §10.2): what the format defines, by the format's intrinsics op; a container's constituents. */
async function intrinsics(bytes: Uint8Array, name: string) {
  const sniffed = sniffMime(bytes, name);
  const mime = sniffed === "text/plain" && /\.ya?ml$/.test(name) ? "application/yaml" : sniffed;
  const r = mime === "application/yaml" ? null : await attesterFor(mime)?.(bytes, mime);
  const val: J = { ...(r?.value ?? { mime, bytes: bytes.length, encoding: "utf-8" }) };
  for (const k of ["sha256", "md5", "members"]) delete val[k];
  const parts: { path: string; blake3: string; bytes: Uint8Array }[] = [];
  for (const m of r?.members ?? []) parts.push({ path: m.path, blake3: m.blake3 ?? (await blake3Hex(m.bytes)), bytes: m.bytes });
  if (mime === "text/html") parts.push(...(await dataUris(bytes)));
  if (parts.length) val.constituents = parts.map((p) => ({ path: p.path, blake3: p.blake3 }));
  const family = mime.split("/")[1]!.replace(/^x-/, "").split("+")[0]!;
  return { line: { at: "whole", pred: "intrinsics", val, by: `${family}.intrinsics@1` }, parts };
}

/** Every `data:` URI in markup is a constituent; its path is the URI's byte span (§10.3). */
async function dataUris(bytes: Uint8Array) {
  const text = new TextDecoder("latin1").decode(bytes);
  const out: { path: string; blake3: string; bytes: Uint8Array }[] = [];
  for (const m of text.matchAll(/data:([a-z0-9.+/-]*)(;base64)?,([^"')\s]+)/gi)) {
    const payload = m[2] ? Uint8Array.from(Buffer.from(m[3]!, "base64")) : new TextEncoder().encode(decodeURIComponent(m[3]!));
    if (payload.length) out.push({ path: `${m.index}-${m.index! + m[0].length}`, blake3: await blake3Hex(payload), bytes: payload });
  }
  return out;
}

/** The byte span of an element (start tag to end tag), or of a JSON string value (§10.4.5). */
function htmlSpan(bytes: Uint8Array, open: string, tag: string) {
  const text = new TextDecoder("latin1").decode(bytes);
  const a = text.indexOf(open);
  if (a < 0) throw new Error(`no ${open}`);
  return `bytes=${a},${text.indexOf(`</${tag}>`, a) + tag.length + 3}`;
}
function jsonSpan(bytes: Uint8Array, key: string, value: string) {
  const buf = Buffer.from(bytes);
  const needle = Buffer.from(`"${key}": ${JSON.stringify(value)}`);
  const at = buf.indexOf(needle);
  if (at < 0) throw new Error(`no ${key}: ${value}`);
  const a = at + Buffer.byteLength(`"${key}": `);
  return `bytes=${a},${a + Buffer.byteLength(JSON.stringify(value))}`;
}

/** Ingest (§19.5): the artifact and its testimony into the local store, the receipt, the holdings — no repository write. */
let clock = 0;
async function ingest(inst: Instance, bytes: Uint8Array, name: string, testimony: Uint8Array | null, actor = "reader-a") {
  const full = await blake3Hex(bytes);
  keep("artifacts", full, bytes);
  const delivered: string[] = [];
  if (testimony) {
    const t = await blake3Hex(testimony);
    keep("testimony", t, testimony);
    delivered.push(t);
  }
  const received = new Date(Date.parse(`${DATE}T09:00:00Z`) + 60_000 * clock++).toISOString().replace(".000", "");
  const receipt = new TextEncoder().encode(`${JSON.stringify(sortKeys({ actor, artifact: full, instance: inst.config.id, name, received, testimony: delivered }))}\n`);
  const r = await blake3Hex(receipt);
  keep("testimony", r, receipt);
  inst.holdings.push({ artifact: full, receipt: r, testimony: delivered });
  idOf(full);
  const { parts } = await intrinsics(bytes, name);
  for (const p of parts) idOf(p.blake3);
  return { full, parts };
}

/** Copy a regression term and what it refines, in the specification's line shape (§6.1, §11.2). */
const DROP = new Set(["concept", "keys", "cells", "sentinel", "owes", "functional", "origin", "lint", "axes", "physical", "tree", "matches", "select", "shape", "spine", "chrome", "derivation"]);
/** What only restates a format (§11.4.1): the tooling knows these, so no form names them. */
const FORMATS = new Set(["unit", "document", "data", "container", "lossy", "image", "media", "html", "xhtml", "pdf", "json", "ndjson", "csv", "tsv", "zip", "png", "jpeg", "gif", "markdown", "yaml", "rfc822", "plain-text"]);
/** Forms that named meaning, not structure (§11.1.2), and the structural form each scope really is. */
const STRUCTURE: Record<string, string | null> = { "methodological-tool": null, regulation: null, "parameter-table": "table", "revision-history": "table", toc: "table", metadata: "definition-list", price: "value", "listing-fact": "list-item", "listing-page": null };
const OWN_SURFACE = new Set(["html.text@1", "pdf.words@1", "csv.parse@1", "eml.text@1", "json.text@1", "yaml.text@1", "markdown.text@1"]);
function copyForm(inst: Instance, name: string, seen = new Set<string>()) {
  if (FORMATS.has(name) || name in STRUCTURE || seen.has(name) || inst.terms.has(`forms/${name}`)) return;
  seen.add(name);
  const path = join(ONTO, `${name}.claims.jsonl`);
  if (!existsSync(path)) throw new Error(`no regression term ${name}`);
  const lines: J[] = [];
  for (const raw of readFileSync(path, "utf8").split("\n").filter(Boolean)) {
    const l = JSON.parse(raw) as J;
    const pred = String(l.predicate);
    let val = l.value as unknown;
    if (DROP.has(pred)) continue;
    if (pred === "refines" && FORMATS.has(String(val))) continue;
    if (pred === "derivation" && OWN_SURFACE.has(String(val))) continue;
    if (pred === "expects" && Array.isArray(val)) val = val.filter((f) => !FORMATS.has(String(f)));
    if (pred === "convention" && typeof val === "string") continue;
    if (pred === "tree" && typeof val === "string") val = val.split(" ")[0];
    if (pred === "chrome" && Array.isArray(val)) val = { selector: val.join(", ") };
    if ((pred === "select" || pred === "shape") && val && typeof val === "object") {
      const { term, ...rest } = val as J;
      val = { ...rest, form: term };
    }
    if (pred === "field" && val && typeof val === "object") {
      const { kind, ...rest } = val as J;
      val = { ...rest, type: kind };
    }
    if (pred === "matches" && val && typeof val === "object") {
      const { header, member, ...rest } = val as J;
      val = { ...rest, ...(header ? { first_row: header } : {}), ...(member ? { constituent: member } : {}) };
    }
    lines.push({ pred, val });
  }
  if (!lines.length) lines.push({ pred: "definition", val: name.replace(/-/g, " ") });
  inst.add("forms", name, lines);
  for (const l of lines) if (l.pred === "refines") copyForm(inst, String(l.val), seen);
  for (const l of lines) if (l.pred === "select") copyForm(inst, String((l.val as J).form), seen);
  for (const l of lines) if (l.pred === "expects") for (const f of l.val as string[]) copyForm(inst, f, seen);
  for (const l of lines) if (l.pred === "shape" && (l.val as J).form) copyForm(inst, String((l.val as J).form), seen);
}
function kind(inst: Instance, name: string, owes: string[], definition: string, evidencedBy: string[] = []) {
  inst.add("kinds", name, [{ pred: "definition", val: definition }, { pred: "owes", val: owes }, ...(evidencedBy.length ? [{ pred: "evidenced_by", val: evidencedBy }] : [])]);
}
function prop(inst: Instance, name: string, range: string, functional = false, authority = false) {
  inst.add("properties", name, [{ pred: "range", val: range }, ...(functional ? [{ pred: "functional", val: true }] : []), ...(authority ? [{ pred: "authority", val: true }] : [])]);
}
const recordPass = { pred: "pass", val: { by: "reader-a", date: DATE, id: "p1", verify: "reader-b", vocab: "@corpus" } };
const entityPass = { pred: "pass", val: { by: "reader-a", date: DATE, id: "p1", verify: "reader-b", vocab: "@graph" } };
const ev = (anchor: string, quote: string, reading: string, extra: J = {}) => ({ anchor, mode: "stated", quote, reading, ...extra });

// ══ reference — public, standalone ════════════════════════════════════════════════════════════════════════════════
rmSync(OUT, { recursive: true, force: true });
const ref = new Instance(join(OUT, "reference"), { id: "3b8f1d2e-9a4c-4f6b-8e2d-5c7a1b9e0f43", name: "reference", tier: "public", shard: { records: 2, entities: 2 } });
for (const f of ["header", "heading", "page", "cover-page", "label", "paragraph", "definition", "definition-list", "row", "caption", "list", "list-item", "equation", "figure", "table-of-contents", "table", "footnote", "end-mark"])
  copyForm(ref, f);
ref.shape(
  "web-capture",
  { pred: "definition", val: "a page capture's sidecar: the page's address, the capturing tool, why it was captured" },
  { pred: "testimony", val: true },
  { pred: "matches", val: { mime: "application/yaml", selector: "/source/uri" } },
  { pred: "field", val: { name: "source-uri", type: "string", required: true, from: "/source/uri" } },
  { pred: "field", val: { name: "producer-tool", type: "string", required: true, from: "/producer/tool" } },
  { pred: "field", val: { name: "context", type: "string", from: "/context" } },
);
ref.term("value", { pred: "definition", val: "a short value printed apart from running text" }, { pred: "reads", val: "text" });
ref.shape(
  "homes-listing",
  { pred: "definition", val: "the markup of homes.example.invalid's property pages" },
  { pred: "matches", val: { mime: "text/html", selector: '.listing[itemtype="https://schema.org/Residence"]' } },
  { pred: "select", val: { selector: "h1.listing-title", form: "heading", level: 0 } },
  { pred: "select", val: { selector: ".price .amount", form: "value" } },
  { pred: "select", val: { selector: "ul.facts li", form: "list-item" } },
  { pred: "select", val: { selector: ".description > p", form: "paragraph" } },
  { pred: "select", val: { selector: ".rooms li.room", form: "list-item" } },
  { pred: "select", val: { selector: ".photos img", form: "figure", field: "alt", attr: "alt" } },
  { pred: "chrome", val: { selector: ".site-header, .site-footer, script, .agent" } },
);
kind(ref, "residence", ["address", "price", "bedrooms", "tenure"], "a dwelling offered or held");
kind(ref, "standard", ["title", "version", "issued-by", "source"], "a published method others follow");
kind(ref, "organization", ["legal-name"], "a body that acts in its own name");
prop(ref, "address", "string", true);
prop(ref, "price", "amount", true);
prop(ref, "source", "artifact", false, true);
prop(ref, "bedrooms", "int", true);
prop(ref, "tenure", "string", true);
prop(ref, "council-tax-band", "string", true);
prop(ref, "title", "string", true);
prop(ref, "version", "string", true);
prop(ref, "issued-by", "organization", true);
prop(ref, "legal-name", "string", true);

// the listing: ingested, cited, never judged — it has no record
const listingBytes = readFileSync(join(SYN, "cottage-listing.html"));
const captureSidecar = new TextEncoder().encode(
  ["source:", "  uri: https://homes.example.invalid/listing/12-quay-street", "producer:", "  tool: page-capture 4.2", "  host: capture-box", "  fetched: 2026-03-19T21:40:00Z", "context: house hunting, Port Ellen", ""].join("\n"),
);
const listing = await ingest(ref, listingBytes, "cottage-listing.html", captureSidecar);
const L = A(listing.full);
ref.entity(
  "12-quay-street-port-ellen",
  entityPass,
  { pred: "is", val: "residence", pass: "p1" },
  { pred: "address", val: "12 Quay Street, Port Ellen", ev: [ev(`${L}?${htmlSpan(listingBytes, '<h1 class="listing-title">', "h1")}&text`, "12 Quay Street, Port Ellen", "derived:html.text@1")], pass: "p1" },
  { pred: "price", val: "£313,000", ev: [ev(`${L}?${htmlSpan(listingBytes, '<span class="amount">', "span")}&text`, "£313,000", "derived:html.text@1")], pass: "p1" },
  { pred: "bedrooms", val: "2", ev: [ev(`${L}?${htmlSpan(listingBytes, '<li class="beds">', "li")}&text`, "2 bedrooms", "derived:html.text@1")], pass: "p1" },
  { pred: "tenure", val: "Freehold", ev: [ev(`${L}?${htmlSpan(listingBytes, '<li class="tenure">', "li")}&text`, "Freehold", "derived:html.text@1")], pass: "p1" },
);

// the procedure: an asserted tree, read and signed — a record of 400-odd judgments
const procBytes = readFileSync(join(SYN, "procedure.pdf"));
const proc = await ingest(ref, procBytes, "procedure.pdf", null);
const passFile = readdirSync(join(HERE, "passes")).find((f) => f.startsWith(proc.full))!;
const scopes = new Map<string, J & { forms: string[] }>();
const readings: { at: string; aspect: string; body: unknown; rev: string }[] = [];
for (const raw of readFileSync(join(HERE, "passes", passFile), "utf8").split("\n").filter(Boolean)) {
  const { at, predicate, value, term, aspect, body, rev: r, ...fields } = JSON.parse(raw) as J;
  const sc = scopes.get(String(at)) ?? { at, forms: [] as string[] };
  scopes.set(String(at), sc);
  if (predicate === "manifests") {
    const form = String(term) in STRUCTURE ? STRUCTURE[String(term)] : String(term);
    if (form === null) continue;
    sc.forms.push(form!);
    Object.assign(sc, fields);
  } else if (predicate === "in") {
    sc.in = (value as J).at;
    sc.ord = (value as J).ord;
  } else if (predicate === "reads_as") {
    sc[String(aspect)] = body;
    readings.push({ at: String(at), aspect: String(aspect), body, rev: String(r) });
  }
}
const procLines: J[] = [...scopes.values()]
  .filter((sc) => sc.forms.length || sc.in !== undefined)
  .map(({ forms, ...sc }) => ({ ...sc, ...(forms.length ? { form: forms.length === 1 ? forms[0] : [...forms].sort() } : {}), pass: "p1" }));
const read = (body: string) => readings.find((l) => l.body === body)!;
ref.record(
  proc.full,
  (await intrinsics(procBytes, "procedure.pdf")).line,
  { at: "whole", ...recordPass },
  ...procLines,
  { at: "whole", pred: "complete", pass: "p1" },
);
const P = A(proc.full);
const lbl = (body: string) => `${P}?${read(body).at}&text`;
ref.entity(
  "hl-02",
  entityPass,
  { pred: "is", val: "standard", pass: "p1" },
  { pred: "title", val: "Procedure to estimate heat loss from insulated pipework over a reporting period", ev: [ev(lbl("Procedure to estimate heat loss from insulated pipework over a reporting period"), "Procedure to estimate heat loss from insulated pipework over a reporting period", read("Procedure to estimate heat loss from insulated pipework over a reporting period").rev as string)], pass: "p1" },
  { pred: "version", val: "02.1", ev: [ev(lbl("Version 02.1"), "Version 02.1", read("Version 02.1").rev as string)], pass: "p1" },
  { pred: "source", val: P, ev: [ev(lbl("HL-02"), "HL-02", read("HL-02").rev as string, { mode: "inferred", reason: "the document prints the standard's designation on its cover, issued by the office" })], pass: "p1" },
  { pred: "issued-by", val: "ath://harbour-standards-office", qual: { as: "HARBOUR STANDARDS OFFICE" }, ev: [ev(lbl("HARBOUR STANDARDS OFFICE"), "HARBOUR STANDARDS OFFICE", read("HARBOUR STANDARDS OFFICE").rev as string)], pass: "p1" },
);
ref.entity(
  "harbour-standards-office",
  entityPass,
  { pred: "is", val: "organization", pass: "p1" },
  { pred: "legal-name", val: "HARBOUR STANDARDS OFFICE", ev: [ev(lbl("HARBOUR STANDARDS OFFICE"), "HARBOUR STANDARDS OFFICE", read("HARBOUR STANDARDS OFFICE").rev as string)], pass: "p1" },
);
const tex = readings.find((l) => l.aspect === "tex")!;
ref.stores.set("mirror", { id: "8c2e4a1f-0b3d-4c5e-9f7a-2d1e6b8c4a90", driver: "rclone", role: "managed", tags: ["object", "online", "country:gb", "city:glasgow"], encryption: "none" });
ref.policies.set("public-twice", { select: { tier: "public" }, require: { copies: 2, where: { not: ["local"] }, distinct: "city" }, verify: "180d" });
ref.rulings.push(
  { id: "r1", pred: "seek", val: { select: { kind: "residence" }, owes: ["council-tax-band"], why: "compare running costs before viewing" }, date: DATE, by: "owner" },
  { id: "r2", pred: "accept", val: { on: `${P}?${tex.at}`, rev: tex.rev, why: "two-dimensional maths; the surface is in baseline order" }, date: DATE, by: "owner" },
);

// ══ household — private, extends reference ════════════════════════════════════════════════════════════════════════
const home = new Instance(join(OUT, "household"), {
  id: "0f4c2a8e-7b1d-4e5a-9c3f-6d2e8b1a4c70",
  name: "household",
  tier: "private",
  extends: { path: "../reference", commit: "5f2a9c1e7d3b40a86e1f2c9b7d4a3e5f60812c7d" },
  shard: { records: 2, entities: 2 },
  audiences: { family: ["private"] },
});
home.shape(
  "drive-export",
  { pred: "refines", val: "testimony" },
  { pred: "definition", val: "a cloud drive's export sidecar: the account and folder exported, when, how much of it" },
  { pred: "testimony", val: true },
  { pred: "matches", val: { mime: "application/yaml", selector: "/origin_fields/folder" } },
  { pred: "field", val: { name: "account", type: "string", required: true, from: "/origin_fields/account" } },
  { pred: "field", val: { name: "exported-at", type: "datetime", from: "/origin_fields/exported_at" } },
);
home.shape(
  "headed-sheet",
  { pred: "definition", val: "a CSV whose first row names its columns: Berth, Vessel, Length (m)" },
  { pred: "matches", val: { mime: "text/csv", first_row: ["Berth", "Vessel", "Length (m)"] } },
  { pred: "columns", val: { header: 0, form: "header" } },
  { pred: "columns", val: { rows: "row" } },
);
home.shape(
  "messenger-thread",
  { pred: "definition", val: "one conversation as a messaging service exports it: participants, then messages" },
  { pred: "matches", val: { mime: "application/json", selector: "/participants" } },
  { pred: "matches", val: { mime: "application/json", selector: "/messages/*/sender_name" } },
  { pred: "select", val: { selector: "/messages/*", form: "message" } },
  { pred: "select", val: { selector: "/messages/*/sender_name", form: "field", in: "message" } },
  { pred: "select", val: { selector: "/messages/*/content", form: "body", in: "message" } },
);
home.term("message", { pred: "definition", val: "one message of a conversation" }, { pred: "reads", val: "none" });
home.term("field", { pred: "definition", val: "one named value of a structured record" }, { pred: "reads", val: "text" });
home.term("body", { pred: "definition", val: "the running text of a message" }, { pred: "reads", val: "text" });
kind(home, "berth", ["occupant"], "a mooring place in a harbour");
kind(home, "vessel", ["display-name", "length"], "a boat");
kind(home, "person", ["display-name"], "a human being");
prop(home, "occupant", "vessel", true);
prop(home, "display-name", "string", true);
prop(home, "length", "decimal", true);

const zipBytes = readFileSync(join(SYN, "drive-folder.zip"));
const drive = await ingest(home, zipBytes, "drive-folder.zip", readFileSync(join(SYN, "drive-folder.zip.capture.yaml")));
const part = (suffix: string) => drive.parts.find((p) => p.path.endsWith(suffix))!;

// the plan inside the zip was read: that constituent alone has a record
const plan = part("Mooring plan 2026.pdf");
const tmp = mkdtempSync(join(process.env.TMPDIR ?? tmpdir(), "mock-"));
writeFileSync(join(tmp, "p.pdf"), plan.bytes);
const bbox = spawnSync("pdftotext", ["-bbox-layout", join(tmp, "p.pdf"), "-"], { encoding: "utf8" }).stdout;
rmSync(tmp, { recursive: true, force: true });
const pg = /<page width="([\d.]+)" height="([\d.]+)"/.exec(bbox)!;
const ln = /<line xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">/.exec(bbox)!;
const [W, H] = [Number(pg[1]), Number(pg[2])];
const [x0, y0, x1, y1] = [1, 2, 3, 4].map((i) => Number(ln[i]));
const r4 = (n: number) => Math.round(n * 1e4) / 1e4;
const headAt = `page=1&bbox=${r4(x0! / W)},${r4(y0! / H)},${r4((x1! - x0!) / W)},${r4((y1! - y0!) / H)}`;
home.record(
  plan.blake3,
  (await intrinsics(plan.bytes, "Mooring plan 2026.pdf")).line,
  { at: "whole", ...recordPass },
  { at: headAt, form: "heading", in: "whole", ord: 0, level: 0, text: "Mooring plan 2026", pass: "p1" },
);

// berths and their vessels cite the CSV inside the zip by its own id — the CSV has no record
const C = A(part("Berth list.csv").blake3);
for (const [row, berth, vessel, len] of [
  [1, "A1", "Lantern", "8.2"],
  [2, "A2", "Gull", "6.5"],
] as const) {
  const v = vessel.toLowerCase();
  home.entity(
    `berth-${berth.toLowerCase()}`,
    entityPass,
    { pred: "is", val: "berth", pass: "p1" },
    { pred: "occupant", val: `ath://${v}`, qual: { as: vessel }, ev: [ev(`${C}?row=${row}&col=1`, vessel, "derived:csv.parse@1")], pass: "p1" },
  );
  home.entity(
    v,
    entityPass,
    { pred: "is", val: "vessel", pass: "p1" },
    { pred: "display-name", val: vessel, ev: [ev(`${C}?row=${row}&col=1`, vessel, "derived:csv.parse@1")], pass: "p1" },
    { pred: "length", val: len, ev: [ev(`${C}?row=${row}&col=2`, len, "derived:csv.parse@1")], pass: "p1" },
  );
}

// a conversation: structure by pointer selects, a person cited at a JSON value's span
const threadBytes = readFileSync(join(SYN, "facebook-thread.json"));
const thread = await ingest(home, threadBytes, "facebook-thread.json", null);
const T = A(thread.full);
const first = (JSON.parse(threadBytes.toString()) as { messages: { sender_name: string }[] }).messages[0]!.sender_name;
home.entity(
  first.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
  entityPass,
  { pred: "is", val: "person", pass: "p1" },
  { pred: "display-name", val: first, ev: [ev(`${T}?${jsonSpan(threadBytes, "sender_name", first)}&text`, first, "derived:json.text@1")], pass: "p1" },
);

home.stores.set("nas", { id: "6b1f0c52-5d0e-4a8e-9c1e-2f0d6f9b2a71", driver: "rclone", role: "managed", tags: ["hdd", "online", "country:ca", "city:winnipeg"], encryption: "none", capacity: "8TB" });
home.stores.set("offsite", { id: "e3a7c9d1-4f2b-4b6e-8a0c-7d5e1f3b9c26", driver: "rclone", role: "managed", tags: ["object", "online", "country:ca", "city:toronto", "private-ok"], encryption: "client" });
home.stores.set("phone-share", { id: "a9d4e6f2-1c3b-4e8a-b7d5-0f2c6e9a1b38", driver: "local", role: "observed", tags: ["phone", "local"], links: ["reflink", "hardlink"] });
home.policies.set("household-in-canada", { select: { tier: "private" }, require: { copies: 2, where: { not: ["local"] }, distinct: "city" }, confine: { all: ["country:ca"] }, verify: "90d" });
home.policies.set("testimony-twice", { select: { testimony: true }, require: { copies: 2, where: { all: ["private-ok"] } } });
home.rulings.push(
  { id: "r1", pred: "seek", val: { select: { kind: "berth" }, owes: ["occupant"], why: "which berth is ours next season" }, date: DATE, by: "owner" },
  { id: "r2", pred: "decline", val: { on: A(part("Quay photo.png").blake3), demand: "reading", why: "a harbour snapshot, nothing to read" }, date: DATE, by: "owner" },
);

await ref.flush();
await home.flush(ref);
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

const tree = spawnSync("find", [".", "-not", "-path", ".", "-not", "-path", "./host/data/*/*/*"], { cwd: OUT, encoding: "utf8" }).stdout.split("\n").filter(Boolean).sort();
console.log(`wrote ${OUT}\n${tree.join("\n")}`);
