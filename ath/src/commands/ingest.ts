// ingest.ts — `ath ingest <file>…`: bytes on disk become artifact subjects; `ath ingest show <blake3>` shows what
// the ops attested and where the bytes resolve.
import { readFileSync } from "node:fs";
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
    via: z.enum(["capture", "upload", "export"]).optional(),
    received: z.string().optional(),
    snapshot: z.string().optional(),
    note: z.string().optional(),
    fidelity: z.string().optional(),
  })
  .passthrough();

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
    examples: ["ath ingest ./am-tool-03-v3.pdf --origin cdm.unfccc.int --via upload", "ath ingest page.html --sidecar page.capture.json"],
    help: `The sidecar is a JSON object with any of: origin, uri, via (capture · upload · export), received, snapshot,
note, fidelity. Flags override it. An HTML file that carries a v52 capture banner (corpus-capture-url meta tags)
supplies its own origin, uri and snapshot. A zip's members are ingested as subjects of their own.`,
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
      },
    },
    data: z.object({ ingested: z.array(ingested) }),
  }),
  async run(ctx, a) {
    const chain = openChain(ctx);
    let prov: Provenance = {};
    if (a.sidecar) {
      let raw: unknown;
      try {
        raw = JSON.parse(readFileSync(resolve(ctx.cwd, a.sidecar), "utf8"));
      } catch (e) {
        throw new AthError("USAGE", `--sidecar: ${(e as Error).message}`);
      }
      const r = Sidecar.safeParse(raw);
      if (!r.success) throw new AthError("USAGE", `--sidecar: ${r.error.issues.map((i) => i.message).join("; ")}`);
      prov = r.data;
    }
    for (const k of ["origin", "uri", "via", "received", "note"] as const)
      if (a[k] !== undefined) (prov as Record<string, unknown>)[k] = a[k];
    if (Object.keys(prov).length && !prov.received && !prov.snapshot) prov.received = ctx.clock.iso().slice(0, 10);
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
          provenance: Object.keys(prov).length ? prov : undefined,
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
