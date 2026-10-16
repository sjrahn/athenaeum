// ingest.ts — `ath ingest <file>…`: bytes on disk become artifact subjects; `ath ingest show <blake3>` shows what
// the ops attested and where the bytes resolve.
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { defineContract, z } from "../../contracts/index.ts";
import { openChain, requireBlake3 } from "../engine/context.ts";
import { type Ingested, ingestFile, type Provenance } from "../engine/corpus/ingest.ts";
import { resolveBytes } from "../engine/layer/bytes.ts";
import { readSubject } from "../engine/layer/store.ts";
import { defineCommand } from "../kit/define.ts";
import { AthError } from "../kit/errors.ts";

const Sidecar = z
  .object({
    origin: z.string().optional(),
    uri: z.string().optional(),
    /** Other URIs the same bytes answer to (a paginated capture's page URLs, a redirect's source). */
    aliases: z.array(z.string()).optional(),
    via: z.enum(["capture", "upload", "export"]).optional(),
    received: z.string().optional(),
    snapshot: z.string().optional(),
    note: z.string().optional(),
    fidelity: z.string().optional(),
  })
  .passthrough();

/** A producer's capture sidecar (`<file>.capture.yaml`, the shape ita writes — D-sidecar): its keys fold into
 * captured_from. `source_url` → uri (+ origin), `fetched_at` → snapshot, `snapshot_engine` → engine, `aliases` and
 * `origin_fields.pagination.page_urls` → aliases, `capture_issues` → issues, `capture_context` → context,
 * `origin_fields` → fields. Keys already in ath's own shape pass through. */
export function foldCaptureSidecar(raw: Record<string, unknown>): Provenance {
  const out: Record<string, unknown> = {};
  const str = (k: string) => (typeof raw[k] === "string" ? (raw[k] as string) : undefined);
  const uri = str("source_url") ?? str("uri");
  if (uri) {
    out.uri = uri;
    try {
      out.origin = new URL(uri).hostname.replace(/^www\./, "");
    } catch {
      // not a URL
    }
  }
  const snapshot = str("fetched_at") ?? str("snapshot");
  if (snapshot) out.snapshot = snapshot;
  if (str("snapshot_engine")) out.engine = str("snapshot_engine");
  const aliases = new Set<string>();
  for (const a of Array.isArray(raw.aliases) ? raw.aliases : []) if (typeof a === "string") aliases.add(a);
  const fields = raw.origin_fields;
  if (fields && typeof fields === "object") {
    const pag = (fields as { pagination?: { page_urls?: unknown } }).pagination;
    for (const a of Array.isArray(pag?.page_urls) ? pag.page_urls : []) if (typeof a === "string") aliases.add(a);
    out.fields = fields;
  }
  if (uri) aliases.delete(uri);
  if (aliases.size) out.aliases = [...aliases];
  if (Array.isArray(raw.capture_issues) && raw.capture_issues.length) out.issues = raw.capture_issues;
  if (raw.capture_context && typeof raw.capture_context === "object") out.context = raw.capture_context;
  for (const k of ["origin", "via", "received", "note", "fidelity"]) if (str(k)) out[k] = str(k);
  if (!out.via && (str("source_url") || str("snapshot_engine"))) out.via = "capture";
  return out as Provenance;
}

const ingested = z.object({
  blake3: z.string(),
  mime: z.string(),
  bytes: z.number(),
  path: z.string(),
  existed: z.boolean(),
  members: z.number(),
});

export const ingest = defineCommand({
  meta: {
    summary: "ingest bytes from disk: hash, sniff, attest, place the bytes, write attests + captured_from (ops lines)",
    tier: "write",
    mutating: true,
    locks: ["corpus"],
    examples: ["ath ingest ./procedure.pdf --origin synthetic --via upload", "ath ingest page.html --sidecar page.capture.json"],
    help: `The sidecar is a JSON or YAML object with any of: origin, uri, aliases, via (capture · upload · export),
received, snapshot, note, fidelity — or a producer's capture sidecar (source_url, fetched_at, snapshot_engine,
capture_issues, origin_fields, capture_context), which folds into the same fields. A \`<file>.capture.yaml\` beside a
file is read on its own (--no-sidecar ignores it). Flags override it. An HTML file that carries a v52 capture banner
(corpus-capture-url meta tags) supplies its own origin, uri and snapshot. A zip's members are ingested as subjects of
their own.`,
  },
  contract: defineContract({
    key: "ingest",
    args: z.object({
      files: z.array(z.string()).min(1),
      sidecar: z.string().optional(),
      origin: z.string().optional(),
      uri: z.string().optional(),
      via: z.enum(["capture", "upload", "export"]).optional(),
      received: z.string().optional(),
      note: z.string().optional(),
      link: z.boolean().default(false),
      noMembers: z.boolean().default(false),
      noSidecar: z.boolean().default(false),
    }),
    argv: {
      positionals: [{ name: "files", required: true, variadic: true, help: "files to ingest" }],
      flags: {
        sidecar: { type: "string", metavar: "JSON", help: "provenance sidecar (applies to every file given)" },
        origin: { type: "string", help: "where the bytes came from (a host or producer name)" },
        uri: { type: "string" },
        via: { type: "string", help: "capture · upload · export" },
        received: { type: "string", help: "when the bytes were received (default: the clock's date)" },
        note: { type: "string" },
        link: { type: "boolean", help: "symlink the bytes into the store instead of copying" },
        noMembers: { type: "boolean", help: "do not ingest a container's members" },
        noSidecar: { type: "boolean", help: "ignore a <file>.capture.yaml beside the file" },
      },
    },
    data: z.object({ ingested: z.array(ingested) }),
  }),
  async run(ctx, a) {
    const chain = openChain(ctx);
    const readSidecar = (path: string, what: string): Provenance => {
      let raw: unknown;
      try {
        const text = readFileSync(path, "utf8");
        raw = path.endsWith(".json") ? JSON.parse(text) : Bun.YAML.parse(text);
      } catch (e) {
        throw new AthError("USAGE", `${what}: ${(e as Error).message}`);
      }
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new AthError("USAGE", `${what}: not an object`);
      const folded = foldCaptureSidecar(raw as Record<string, unknown>);
      const r = Sidecar.safeParse(folded);
      if (!r.success) throw new AthError("USAGE", `${what}: ${r.error.issues.map((i) => i.message).join("; ")}`);
      return r.data;
    };
    const given: Provenance = a.sidecar ? readSidecar(resolve(ctx.cwd, a.sidecar), "--sidecar") : {};
    const provFor = (file: string): Provenance | undefined => {
      const beside = `${file}.capture.yaml`;
      const prov: Provenance = { ...(!a.sidecar && !a.noSidecar && existsSync(beside) ? readSidecar(beside, beside) : {}), ...given };
      for (const k of ["origin", "uri", "via", "received", "note"] as const)
        if (a[k] !== undefined) (prov as Record<string, unknown>)[k] = a[k];
      if (Object.keys(prov).length && !prov.received && !prov.snapshot) prov.received = ctx.clock.iso().slice(0, 10);
      return Object.keys(prov).length ? prov : undefined;
    };
    const out: z.infer<typeof ingested>[] = [];
    const flat = (i: Ingested) => {
      out.push({ blake3: i.blake3, mime: i.mime, bytes: i.bytes, path: i.path, existed: i.existed, members: i.members.length });
      for (const m of i.members) flat(m);
    };
    for (const f of a.files) {
      const file = resolve(ctx.cwd, f);
      if (!(await Bun.file(file).exists())) throw new AthError("NOT_FOUND", `${f}: not found`);
      ctx.events.emit({ kind: "ingest.file", level: "info", msg: `ingesting ${f}` });
      flat(
        await ingestFile(chain, file, {
          provenance: provFor(file),
          link: a.link,
          date: ctx.clock.iso().slice(0, 10),
          members: !a.noMembers,
        }),
      );
    }
    return { data: { ingested: out } };
  },
  text(d, io) {
    for (const i of d.ingested)
      io.out(`${i.existed ? "=" : "+"} ${i.blake3}  ${i.mime}  ${i.bytes} bytes${i.members ? `  (${i.members} members)` : ""}\n`);
  },
});

export const ingestShow = defineCommand({
  meta: {
    summary: "an artifact's op lines (attests, captured_from) and where its bytes resolve in the chain",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "ingest-show",
    args: z.object({ subject: z.string() }),
    argv: { positionals: [{ name: "subject", required: true, help: "blake3 or corpus://<blake3>" }] },
    data: z.object({ blake3: z.string(), bytes: z.string().nullable(), lines: z.array(z.record(z.string(), z.unknown())) }),
  }),
  run(ctx, a) {
    const chain = openChain(ctx);
    const id = requireBlake3(a.subject);
    const lines = readSubject(chain, "corpus", id)
      .filter((l) => l.line.predicate === "attests" || l.line.predicate === "captured_from")
      .map((l) => l.line);
    if (!lines.length) throw new AthError("NOT_FOUND", `${id}: no artifact subject in the chain`);
    return { data: { blake3: id, bytes: resolveBytes(chain, id), lines } };
  },
  text(d, io) {
    io.out(`corpus://${d.blake3}\nbytes  ${d.bytes ?? "(not resident in this chain)"}\n`);
    for (const l of d.lines) io.out(`${JSON.stringify(l)}\n`);
  },
});
