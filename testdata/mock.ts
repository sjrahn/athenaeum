// mock.ts — writes a mock instance pair in the specification's layout (spec/athenaeum.md §4, §5): a public
// standalone instance `reference` and a private extension `household` that builds on it, plus the host state
// they share. Everything is generated from committed fixtures under testdata/synthetic/, testdata/passes/ and the
// regression ontology; the output (testdata/mock/) is never tracked. Run: bun testdata/mock.ts
//
// It writes the files by hand to show the layout; it is not the tool. Lines an author would sign are written here
// the way a signed pass would leave them. Records are one YAML document each (§8): the procedure PDF is formed, the
// listing page and the mooring plan are read, the sign photograph is transcribed; the sheet and the thread are
// structured and pass through with no record.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { intrinsicsOf } from "../ath/packages/engine/src/formats/index.ts";
import { sniffMime } from "../ath/packages/engine/src/formats/sniff.ts";
import { emitRecord, type Reading, type RecordDoc as Rec, type Scope } from "../ath/packages/engine/src/record/document.ts";
import { emptyVocabulary, pin as vocabPin, serializeTerm, type Vocab } from "../ath/packages/engine/src/vocab/terms.ts";
import { canonicalLine, sortedValue as sortKeys } from "../ath/packages/kit/src/canonical.ts";
import { blake3Hex, short } from "../ath/packages/kit/src/hash.ts";

const HERE = import.meta.dir;
const SYN = join(HERE, "synthetic");
const ONTO = join(HERE, "ontology");
const OUT = join(HERE, "mock");
const DATE = "2026-03-20";
type J = Record<string, unknown>;

/** Entity lines and rulings: canonical, one per content, sorted (the tool sorts them by identity, §6.4.1). */
const jsonl = (lines: J[]) => `${[...new Set(lines.map(canonicalLine))].sort().join("\n")}\n`;
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
const rev = (body: unknown) => short(body);

// ── subjects (§7.1): the full hash, everywhere it is stored; a prefix is a terminal shortcut only ─────────────────
const A = (full: string) => `ath://${full}`;

// ── the host: local store (artifacts/, testimony/), access, per-instance state ─────────────────────────────────
const HOST = join(OUT, "host");
const keep = (tree: "artifacts" | "testimony", full: string, bytes: Uint8Array) =>
  write(join(HOST, "data/athenaeum", tree, full.slice(0, 2), full), bytes);

class Instance {
  /** Terms by `<vocabulary>/<name>`: forms, kinds and properties are separate name spaces. */
  terms = new Map<string, J[]>();
  records = new Map<string, Rec>();
  entities = new Map<string, J[]>();
  rulings: J[] = [];
  stores = new Map<string, J>();
  policies = new Map<string, J>();
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
  /** The pin of one vocabulary (§11.8), the engine's recipe over this instance's terms and its base's. */
  async pin(side: "corpus" | "graph", base?: Instance) {
    const v = emptyVocabulary();
    for (const inst of [base, this].filter(Boolean) as Instance[])
      for (const [k, ls] of inst.terms) {
        const [vocab, name] = k.split("/") as [Vocab, string];
        v[vocab].set(name, [...(v[vocab].get(name) ?? []), ...ls]);
      }
    return vocabPin(v, side);
  }
  /** A pass's judgments laid over the projection ingest wrote (§8.1). */
  judge(full: string, doc: Omit<Rec, "intrinsics" | "receipts" | "origins">) {
    const have = this.records.get(full);
    if (!have) throw new Error(`no record for ${full.slice(0, 8)}: not ingested here`);
    this.records.set(full, { ...have, ...doc });
  }
  entity(name: string, ...lines: J[]) {
    this.entities.set(name, [...(this.entities.get(name) ?? []), ...lines]);
  }
  prune(base?: Instance) {
    const have = new Set([...this.terms.keys(), ...(base ? [...base.terms.keys()] : [])]);
    for (const [k, ls] of this.terms) {
      if (!k.startsWith("forms/") && !k.startsWith("shapes/")) continue;
      const v = k.slice(0, k.indexOf("/") + 1);
      this.terms.set(
        k,
        ls
          .filter((l) => l.pred !== "refines" || have.has(v + String(l.val)))
          .map((l) => (l.pred === "expects" ? { ...l, val: (l.val as string[]).filter((f) => have.has(`forms/${f}`)) } : l))
          .filter((l) => l.pred !== "expects" || (l.val as string[]).length),
      );
      if (!this.terms.get(k)!.length) this.terms.set(k, [{ pred: "definition", val: k.slice(v.length).replace(/-/g, " ") }]);
    }
  }
  async flush(base?: Instance) {
    this.prune(base);
    const pins = { "@corpus": await this.pin("corpus", base), "@graph": await this.pin("graph", base) };
    const pinned = (ls: J[]) => JSON.parse(JSON.stringify(ls).replace(/"@(corpus|graph)"/g, (m) => JSON.stringify(pins[m.slice(1, -1) as keyof typeof pins]))) as J[];
    write(join(this.dir, "athenaeum.yaml"), yaml(this.config));
    for (const [k, ls] of this.terms) {
      const [v, name] = k.split("/") as [Vocab, string];
      write(join(this.dir, { forms: "corpus/forms", shapes: "corpus/shapes", kinds: "graph/kinds", properties: "graph/properties" }[v], `${name}.jsonl`), serializeTerm(ls));
    }
    for (const [full, doc] of this.records) {
      write(join(this.dir, "corpus/records", full.slice(0, 2), `${full}.yaml`), emitRecord(pinned([doc as unknown as J])[0] as unknown as Rec));
    }
    for (const [n, ls] of this.entities) write(join(this.dir, "graph/entities", n.slice(0, 2), `${n}.jsonl`), jsonl(pinned(ls)));
    for (const [n, s] of this.stores) write(join(this.dir, "stores", `${n}.yaml`), yaml(s));
    for (const [n, p] of this.policies) write(join(this.dir, "policies", `${n}.yaml`), yaml(p));
    if (this.rulings.length) write(join(this.dir, "rulings.jsonl"), jsonl(this.rulings));
    mkdirSync(join(HOST, "state/athenaeum/instances", String(this.config.id), "passes"), { recursive: true });
  }
}

/** intrinsics (§8.2, §10.2): the tool's own intrinsics op for the sniffed format, constituents with their bytes. */
async function intrinsics(bytes: Uint8Array, name: string) {
  const p = await intrinsicsOf(bytes, sniffMime(bytes, name));
  return { val: p.value, parts: p.constituents.map((c) => ({ path: c.path, blake3: c.blake3, bytes: c.read() })) };
}
/** Admission (§9.5): a delivered testimony follows the contract (§9.4), its `subject` the artifact it is delivered for, or ingest refuses it. Nothing else is asked, nothing is written. */
const pointer = (doc: unknown, ptr: string) => ptr.split("/").slice(1).reduce<unknown>((v, k) => (v && typeof v === "object" ? (v as J)[k] : undefined), doc);
function admit(bytes: Uint8Array, subject: string): J {
  const doc = Bun.YAML.parse(new TextDecoder().decode(bytes)) as J;
  const ok = doc.subject === `b3:${subject}` && ["/producer/tool", "/producer/version", "/producer/at"].every((p) => pointer(doc, p) !== undefined) && !!doc.source && typeof doc.source === "object" && Object.keys(doc.source as J).length > 0;
  if (!ok) throw new Error("testimony does not follow the contract, or is not about the artifact it was delivered for: ingest refuses it (§9.5)");
  return doc;
}
/** A capture sidecar in the contract's shape (§9.4). */
const sidecar = async (bytes: Uint8Array, uri: string, at: string, context: string) =>
  new TextEncoder().encode(["subject: b3:" + (await blake3Hex(bytes)), "producer:", "  tool: page-capture", '  version: "4.2"', `  at: "${at}"`, "  host: capture-box", "source:", `  uri: ${uri}`, `context: ${context}`, ""].join("\n"));

/** The byte span of an element (start tag to end tag), or of a JSON string value (§10.4.5). */
function htmlSpan(bytes: Uint8Array, open: string, tag: string) {
  const text = new TextDecoder("latin1").decode(bytes);
  const a = text.indexOf(open);
  if (a < 0) throw new Error(`no ${open}`);
  return `bytes=${a},${text.indexOf(`</${tag}>`, a) + tag.length + 3}`;
}
/** The span of the JSON object that holds a given key/value — the message, not the value (§11.7.1). */
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
function jsonSpan(bytes: Uint8Array, key: string, value: string) {
  const buf = Buffer.from(bytes);
  const needle = Buffer.from(`"${key}": ${JSON.stringify(value)}`);
  const at = buf.indexOf(needle);
  if (at < 0) throw new Error(`no ${key}: ${value}`);
  const a = at + Buffer.byteLength(`"${key}": `);
  return `bytes=${a},${a + Buffer.byteLength(JSON.stringify(value))}`;
}

/** Ingest (§19.5): the artifact and its testimony into the local store, the receipt, and the record's projection — nothing judged. */
let clock = 0;
async function ingest(inst: Instance, bytes: Uint8Array, name: string, testimony: Uint8Array | null, actor = "reader-a") {
  const full = await blake3Hex(bytes);
  keep("artifacts", full, bytes);
  const delivered: { hash: string; name: string }[] = [];
  const origins: J[] = [];
  if (testimony) {
    const t = await blake3Hex(testimony);
    keep("testimony", t, testimony);
    delivered.push({ hash: t, name: `${name}.testimony.yaml` });
    const { subject: _subject, ...origin } = admit(testimony, full);
    origins.push(origin); // the producer's object, verbatim but for `subject`, which the record's own hash states (§8.2.1)
  }
  const received = new Date(Date.parse(`${DATE}T09:00:00Z`) + 60_000 * clock++).toISOString().replace(".000", "");
  const receipt = new TextEncoder().encode(`${JSON.stringify(sortKeys({ actor, artifact: full, instance: inst.config.id, name, received, testimony: delivered }))}\n`);
  const r = await blake3Hex(receipt);
  keep("testimony", r, receipt);
  const { val, parts } = await intrinsics(bytes, name);
  inst.records.set(full, { intrinsics: val, receipts: [{ actor, received, name }], ...(origins.length ? { origins } : {}) });
  return { full, parts, testimony: delivered[0]?.hash };
}

/** Copy a regression term and what it refines, in the specification's line shape (§6.1, §11.2). */
const DROP = new Set(["concept", "keys", "cells", "sentinel", "owes", "functional", "origin", "lint", "axes", "physical", "tree", "matches", "select", "shape", "spine", "chrome", "derivation"]);
/** What only restates a format (§11.4.1): the tooling knows these, so no form names them. */
const FORMATS = new Set(["unit", "document", "data", "container", "lossy", "image", "media", "html", "xhtml", "pdf", "json", "ndjson", "csv", "tsv", "zip", "png", "jpeg", "gif", "markdown", "yaml", "rfc822", "plain-text"]);
/** Forms that named meaning, not structure (§11.1.2), and the structural form each scope really is. */
const STRUCTURE: Record<string, string | null> = { "methodological-tool": null, regulation: null, "parameter-table": "table", "revision-history": "table", toc: "table", metadata: "definition-list", price: "value", "listing-fact": "list-item", "listing-page": null };
/** A table is its rows (§8.4.7): a row reads `cells`, the table and the list nothing. */
const GRID = new Set(["table", "definition-list"]);
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
      const { kind, where, ...rest } = val as J;
      val = { ...rest, type: kind, ...(where ? { where: where === "right-margin" ? "margin" : where } : {}) };
    }
    if (pred === "reads" && GRID.has(name)) continue;
    if (pred === "matches" && val && typeof val === "object") {
      const { header, member, ...rest } = val as J;
      val = { ...rest, ...(header ? { first_row: header } : {}), ...(member ? { constituent: member } : {}) };
    }
    lines.push({ pred, val });
  }
  if (GRID.has(name)) lines.push({ pred: "reads", val: "none" });
  if (name === "list-item") lines.push({ pred: "reads", val: "text" }); // the regression term inherited it from a format root
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
const recordPass = { by: "reader-a", verify: "reader-b", vocab: "@corpus", date: DATE };
const entityPass = { pred: "pass", val: { by: "reader-a", date: DATE, id: "p1", verify: "reader-b", vocab: "@graph" } };
const ev = (anchor: string, quote: string, binding: string, extra: J = {}) => ({ anchor, mode: "stated", quote, binding, ...extra });

// ══ reference — public, standalone ════════════════════════════════════════════════════════════════════════════════
rmSync(OUT, { recursive: true, force: true });
const ref = new Instance(join(OUT, "reference"), { id: "3b8f1d2e-9a4c-4f6b-8e2d-5c7a1b9e0f43", name: "reference", shard: { records: 2, entities: 2 } });
for (const f of ["header", "heading", "cover-page", "label", "paragraph", "definition", "definition-list", "row", "caption", "list", "list-item", "equation", "figure", "table-of-contents", "table", "footnote", "end-mark"])
  copyForm(ref, f);
ref.term("value", { pred: "definition", val: "a short value printed apart from running text" }, { pred: "reads", val: "text" });
ref.shape(
  "homes-listing",
  { pred: "definition", val: "the markup of homes.example.invalid's property pages" },
  { pred: "matches", val: { mime: "text/html", selector: '.listing[itemtype="https://schema.org/Residence"]', origin: { "/source/uri": "https://homes.example.invalid/*" } } },
  { pred: "select", val: { selector: "h1.listing-title", form: "heading", level: 0 } },
  { pred: "select", val: { selector: ".price .amount", form: "value" } },
  { pred: "select", val: { selector: "ul.facts li", form: "list-item" } },
  { pred: "select", val: { selector: ".description > p", form: "paragraph" } },
  { pred: "select", val: { selector: ".rooms li.room", form: "list-item" } },
  { pred: "select", val: { selector: ".photos img", form: "figure" } },
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

// the listing: a rendered page, read where the entity cites it and nowhere else — a record at the read stage
const listingBytes = readFileSync(join(SYN, "cottage-listing.html"));
const captureSidecar = await sidecar(listingBytes, "https://homes.example.invalid/listing/12-quay-street", "2026-03-19T21:40:00Z", "house hunting, Port Ellen");
const listing = await ingest(ref, listingBytes, "cottage-listing.html", captureSidecar);
const L = A(listing.full);
const listingRead: Record<string, Reading> = {};
const span = (open: string, tag: string, text: string) => {
  const at = htmlSpan(listingBytes, open, tag);
  listingRead[at] = { text };
  return at;
};
const cite = async (at: string, quote: string) => ev(`${L}?${at}&text`, quote, await rev(listingRead[at]!.text!));
const [addrAt, priceAt, bedsAt, tenureAt] = [
  span('<h1 class="listing-title">', "h1", "12 Quay Street, Port Ellen"),
  span('<span class="amount">', "span", "£313,000"),
  span('<li class="beds">', "li", "2 bedrooms"),
  span('<li class="tenure">', "li", "Freehold"),
];
ref.judge(listing.full, { passes: { p1: { ...recordPass, over: Object.keys(listingRead) } }, readings: listingRead });
ref.entity(
  "12-quay-street-port-ellen",
  entityPass,
  { pred: "is", val: "residence", pass: "p1" },
  { pred: "address", val: "12 Quay Street, Port Ellen", ev: [await cite(addrAt, "12 Quay Street, Port Ellen")], pass: "p1" },
  { pred: "price", val: "£313,000", ev: [await cite(priceAt, "£313,000")], pass: "p1" },
  { pred: "bedrooms", val: "2", ev: [await cite(bedsAt, "2 bedrooms")], pass: "p1" },
  { pred: "tenure", val: "Freehold", ev: [await cite(tenureAt, "Freehold")], pass: "p1" },
);

// the procedure: formed — readings at their addresses, a tree over them, both complete; pages are addresses only
const procBytes = readFileSync(join(SYN, "procedure.pdf"));
const procSidecar = await sidecar(procBytes, "https://standards.harbour.example.invalid/hl-02/02.1/procedure.pdf", "2026-03-19T21:52:00Z", "the heat-loss procedure the office publishes");
const proc = await ingest(ref, procBytes, "procedure.pdf", procSidecar);
/** The line boxes pdftotext finds on a page inside a region, in reading order — how this mock gives rows their own addresses. */
function linesIn(pdf: Uint8Array, page: number, bbox: string) {
  const tmp = mkdtempSync(join(process.env.TMPDIR ?? tmpdir(), "mock-"));
  writeFileSync(join(tmp, "p.pdf"), pdf);
  const xml = spawnSync("pdftotext", ["-bbox-layout", "-f", String(page), "-l", String(page), join(tmp, "p.pdf"), "-"], { encoding: "utf8" }).stdout;
  rmSync(tmp, { recursive: true, force: true });
  const [, W, H] = /<page width="([\d.]+)" height="([\d.]+)"/.exec(xml)!.map(Number);
  const [x, y, w, h] = bbox.split(",").map(Number);
  const r4 = (n: number) => Math.round(n * 1e4) / 1e4;
  const rows: number[][] = [];
  for (const m of xml.matchAll(/<line xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">/g)) {
    const [x0, y0, x1, y1] = [m[1], m[2], m[3], m[4]].map((v) => Number(v));
    const [lx, ly, lw, lh] = [x0! / W!, y0! / H!, (x1! - x0!) / W!, (y1! - y0!) / H!];
    if (!(lx >= x! - 0.005 && ly >= y! - 0.005 && lx + lw <= x! + w! + 0.005 && ly + lh <= y! + h! + 0.005)) continue;
    const last = rows.at(-1);
    if (last && Math.abs(last[1]! - ly) < 0.004) last[2] = Math.max(last[0]! + last[2]!, lx + lw) - last[0]!; // a key and its value on one baseline are one row
    else rows.push([lx, ly, lw, lh]);
  }
  return rows.map(([lx, ly, lw, lh]) => `page=${page}&bbox=${r4(lx!)},${r4(ly!)},${r4(lw!)},${r4(lh!)}`);
}
const passFile = readdirSync(join(HERE, "passes")).find((f) => f.startsWith(proc.full))!;
type Old = { at: string; forms: string[]; in?: string; ord?: number; body?: Record<string, unknown>; [field: string]: unknown };
const old = new Map<string, Old>();
for (const raw of readFileSync(join(HERE, "passes", passFile), "utf8").split("\n").filter(Boolean)) {
  const { at, predicate, value, term, aspect, body, rev: _r, ...fields } = JSON.parse(raw) as J;
  const sc = old.get(String(at)) ?? { at: String(at), forms: [] };
  old.set(String(at), sc);
  if (predicate === "manifests") {
    const form = String(term) in STRUCTURE ? STRUCTURE[String(term)] : String(term);
    if (form === null || form === "page") continue;
    sc.forms.push(form!);
    Object.assign(sc, fields, term === "toc" ? { layout: "grid" } : {});
  } else if (predicate === "in") {
    sc.in = String((value as J).at);
    sc.ord = Number((value as J).ord);
  } else if (predicate === "reads_as") (sc.body ??= {})[String(aspect)] = body;
}
// readings: every transcribed region, its leading designator lifted into the scope's field (§8.4.4); a table is its rows
// (§8.4.7), so a grid or a key-value block read whole is split into row scopes at the lines' own boxes; the forming pass
// adopts each reading into the scope at its address (§8.4.3), so none is written under `readings`
const procRead: Record<string, Reading> = {};
const kids = (parent: string) => [...old.values()].filter((o) => o.in === parent).sort((a, b) => a.ord! - b.ord!);
for (const o of [...old.values()]) {
  if (!o.body) continue;
  if (GRID.has(o.forms[0]!)) {
    const rows = Array.isArray(o.body.cells) ? (o.body.cells as string[][]) : String(o.body.text).split("\n").map((l) => l.split(/: (.*)/s).filter(Boolean));
    const [, page, box] = /^page=(\d+)&bbox=(.*)$/.exec(o.at)!;
    const lines = linesIn(procBytes, Number(page), box!);
    if (lines.length !== rows.length) throw new Error(`${o.at}: ${rows.length} rows, ${lines.length} lines`);
    rows.forEach((cells, i) => {
      const caption = o.forms[0] === "table" && cells.slice(1).every((c) => c === ""); // a title row is the table's caption, not a row
      old.set(lines[i]!, { at: lines[i]!, forms: [caption ? "caption" : o.forms[0] === "table" ? "row" : "definition"], in: o.at, ord: i });
      procRead[lines[i]!] = caption ? { text: cells[0]! } : { cells };
    });
    continue;
  }
  const r: Reading = {};
  if (typeof o.body.text === "string") r.text = o.body.text;
  if (typeof o.body.tex === "string") r.tex = o.body.tex;
  if (Array.isArray(o.body.cells)) r.cells = o.body.cells as string[][];
  procRead[o.at] = r;
}
// the tree: a page is nowhere in it; what sat `in` a page hangs from the scope at that page, else from the root
const adopted = new Set<string>();
const scopeOf = (o: Old): Scope => {
  const { at, forms, in: _in, ord: _o, body: _b, ...fields } = o;
  const children = kids(at).map(scopeOf);
  adopted.add(at);
  return { form: forms.length === 1 ? forms[0]! : [...forms].sort(), at, ...fields, ...procRead[at], ...(children.length ? { scopes: children } : {}) };
};
const top = [...old.values()].filter((o) => o.forms.length && (o.in === "whole" || (o.in?.startsWith("page=") && !o.in.includes("&") && !old.get(o.in)?.forms.length)));
const procTree = top.sort((a, b) => a.ord! - b.ord!).map(scopeOf);
for (const at of Object.keys(procRead)) if (!adopted.has(at)) throw new Error(`reading no scope adopted: ${at}`);
const read = (body: string) => Object.entries(procRead).find(([, r]) => r.text === body)!;
const procIntrinsics = (await intrinsics(procBytes, "procedure.pdf")).val;
ref.judge(proc.full, {
  chrome: [{ repeats: { pages: Number(procIntrinsics.page_count), share: 1 }, mask: "digits", box: 2, roles: { "page-number": "Page # of #" } }],
  passes: { p1: { ...recordPass, attests: ["readings", "structure"] } },
  scopes: procTree,
});
const P = A(proc.full);
const lbl = (body: string) => `${P}?${read(body)[0]}&text`;
const procTestimony = A(proc.testimony!);
const uriSpan = (() => {
  const text = new TextDecoder().decode(procSidecar);
  const a = text.indexOf("https://");
  return `bytes=${a},${text.indexOf("\n", a)}`;
})();
ref.entity(
  "hl-02",
  entityPass,
  { pred: "is", val: "standard", pass: "p1" },
  { pred: "title", val: "Procedure to estimate heat loss from insulated pipework over a reporting period", ev: [ev(lbl("Procedure to estimate heat loss from insulated pipework over a reporting period"), "Procedure to estimate heat loss from insulated pipework over a reporting period", await rev(read("Procedure to estimate heat loss from insulated pipework over a reporting period")[1].text))], pass: "p1" },
  { pred: "version", val: "02.1", ev: [ev(lbl("Version 02.1"), "Version 02.1", await rev(read("Version 02.1")[1].text))], pass: "p1" },
  { pred: "source", val: P, ev: [ev(lbl("HL-02"), "HL-02", await rev(read("HL-02")[1].text), { mode: "inferred", reason: "the document prints the standard's designation on its cover, issued by the office" })], pass: "p1" },
  { pred: "pass", val: { by: "reader-b", date: DATE, id: "p2", verify: "reader-a", vocab: "@graph" } },
  { pred: "source", val: P, ev: [ev(`${procTestimony}?${uriSpan}&text`, "https://standards.harbour.example.invalid/hl-02/02.1/procedure.pdf", "derived:yaml.text@1", { prefix: "uri: " })], pass: "p2" },
  { pred: "issued-by", val: "ath://harbour-standards-office", qual: { as: "HARBOUR STANDARDS OFFICE" }, ev: [ev(lbl("HARBOUR STANDARDS OFFICE"), "HARBOUR STANDARDS OFFICE", await rev(read("HARBOUR STANDARDS OFFICE")[1].text))], pass: "p1" },
);
ref.entity(
  "harbour-standards-office",
  entityPass,
  { pred: "is", val: "organization", pass: "p1" },
  { pred: "legal-name", val: "HARBOUR STANDARDS OFFICE", ev: [ev(lbl("HARBOUR STANDARDS OFFICE"), "HARBOUR STANDARDS OFFICE", await rev(read("HARBOUR STANDARDS OFFICE")[1].text))], pass: "p1" },
);
const tex = Object.entries(procRead).find(([, r]) => r.tex)!;
ref.stores.set("mirror", { id: "8c2e4a1f-0b3d-4c5e-9f7a-2d1e6b8c4a90", driver: "rclone", role: "managed", tags: ["object", "online", "country:gb", "city:glasgow"], encryption: "none" });
ref.policies.set("captures-twice", { select: { origin: "page-capture" }, require: { copies: 2, where: { not: ["local"] }, distinct: "city" }, verify: "180d" });
ref.rulings.push(
  { id: "r1", pred: "seek", val: { select: { kind: "residence" }, owes: ["council-tax-band"], why: "compare running costs before viewing" }, date: DATE, by: "owner" },
  { id: "r2", pred: "accept", val: { on: `${P}?${tex[0]}`, rev: await rev(tex[1].tex), why: "two-dimensional maths; the hint is in baseline order" }, date: DATE, by: "owner" },
);

// ══ household — private, extends reference ════════════════════════════════════════════════════════════════════════
const home = new Instance(join(OUT, "household"), {
  id: "0f4c2a8e-7b1d-4e5a-9c3f-6d2e8b1a4c70",
  name: "household",
  extends: { path: "../reference", commit: "5f2a9c1e7d3b40a86e1f2c9b7d4a3e5f60812c7d" },
  shard: { records: 2, entities: 2 },
});
home.shape(
  "drive-export",
  { pred: "definition", val: "a folder as a cloud drive exports it: what the drive's export tool delivered, recognised by its testimony" },
  { pred: "matches", val: { mime: "application/zip", origin: { "/producer/tool": "google-drive-export" } } },
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
  { pred: "select", val: { selector: "/messages/*/sender_name", form: "message", field: "sender" } },
  { pred: "select", val: { selector: "/messages/*/timestamp_ms", form: "message", field: "sent" } },
  { pred: "select", val: { selector: "/messages/*/content", form: "message", reads: "text" } },
);
home.term(
  "message",
  { pred: "definition", val: "one message of a conversation: who sent it, when, and its text" },
  { pred: "reads", val: "text" },
  { pred: "field", val: { name: "sender", type: "string", required: true } },
  { pred: "field", val: { name: "sent", type: "datetime" } },
);
kind(home, "berth", ["occupant"], "a mooring place in a harbour");
kind(home, "vessel", ["display-name", "length"], "a boat");
kind(home, "person", ["display-name"], "a human being");
prop(home, "occupant", "vessel", true);
prop(home, "display-name", "string", true);
prop(home, "length", "decimal", true);

const zipBytes = readFileSync(join(SYN, "drive-folder.zip"));
const drive = await ingest(home, zipBytes, "drive-folder.zip", readFileSync(join(SYN, "drive-folder.zip.capture.yaml")));
// a recording: one record, its video and audio tracks listed as parts with their intrinsics; nothing said yet
await ingest(home, readFileSync(join(SYN, "harbour-clip.mov")), "harbour-clip.mov", null);
const part = (suffix: string) => drive.parts.find((p) => p.path.endsWith(suffix))!;

// the plan inside the zip was read for its title: that constituent alone has a record, at the read stage
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
home.records.set(plan.blake3, { intrinsics: (await intrinsics(plan.bytes, "Mooring plan 2026.pdf")).val }); // an asset's projection: derived from its container's until something is said
home.judge(plan.blake3, { passes: { p1: { ...recordPass, over: [headAt] } }, readings: { [headAt]: { text: "Mooring plan 2026" } } });

// a photograph of a sign, read in full: transcribed, never formed — three readings and the attestation
const signBytes = readFileSync(join(SYN, "sign.jpg"));
const sign = await ingest(home, signBytes, "sign.jpg", null);
home.judge(sign.full, {
  passes: { p1: { ...recordPass, attests: ["readings"] } },
  readings: {
    "bbox=0.0667,0.1786,0.6022,0.1548": { text: "RETURNS ONLY" },
    "bbox=0.0667,0.4643,0.4556,0.1024": { text: "Bay 12 - Depot 7" },
    "bbox=0.0667,0.6976,0.6467,0.1071": { text: "No parking 7am to 6pm" },
  },
});

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

// a conversation: structure by pointer selects; a person cited through the first message's `sender` field
const threadBytes = readFileSync(join(SYN, "facebook-thread.json"));
const thread = await ingest(home, threadBytes, "facebook-thread.json", null);
const T = A(thread.full);
const first = (JSON.parse(threadBytes.toString()) as { messages: { sender_name: string }[] }).messages[0]!.sender_name;
home.entity(
  first.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
  entityPass,
  { pred: "is", val: "person", pass: "p1" },
  { pred: "display-name", val: first, ev: [ev(`${T}?${jsonObjectSpan(threadBytes, "sender_name", first)}`, first, "field:sender")], pass: "p1" },
);

home.stores.set("nas", { id: "6b1f0c52-5d0e-4a8e-9c1e-2f0d6f9b2a71", driver: "rclone", role: "managed", tags: ["hdd", "online", "country:ca", "city:winnipeg"], encryption: "none", capacity: "8TB" });
home.stores.set("offsite", { id: "e3a7c9d1-4f2b-4b6e-8a0c-7d5e1f3b9c26", driver: "rclone", role: "managed", tags: ["object", "online", "country:ca", "city:toronto", "private-ok"], encryption: "client" });
home.stores.set("phone-share", { id: "a9d4e6f2-1c3b-4e8a-b7d5-0f2c6e9a1b38", driver: "local", role: "observed", tags: ["phone", "local"], links: ["reflink", "hardlink"] });
home.policies.set("exports-in-canada", { select: { origin: "google-drive-export" }, require: { copies: 2, where: { not: ["local"] }, distinct: "city" }, confine: { all: ["country:ca"] }, verify: "90d" });
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
