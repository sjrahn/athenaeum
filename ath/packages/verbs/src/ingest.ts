// ingest.ts — `ath ingest <file…> [--testimony <file>…]` (spec §19.5): for each file, sniff it, admit or refuse the
// testimony delivered with it before anything is placed (§9.5) — beside it as `<file>.testimony.<ext>`, or named with
// --testimony and matched by its `subject` — place the artifact and its testimony in the local store, write the
// receipt (§9.3), and write the record's projection, or add the receipt and the origins to the record it has
// (§8.1). Nothing judged is written. A refused testimony refuses its file and places nothing of it (73).
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { basename, dirname, join, relative, resolve } from "node:path";
import { defineContract, z } from "@ath/contracts";
import { intrinsicsOf } from "@ath/engine/formats/index.ts";
import { sniffMime } from "@ath/engine/formats/sniff.ts";
import { ownRecord, recordPath, recordView, writeRecord } from "@ath/engine/instance/instance.ts";
import type { RecordDoc } from "@ath/engine/record/document.ts";
import { admit, isOriginOf, originOf, parseTestimony, receiptBytes } from "@ath/engine/testimony/testimony.ts";
import { canonicalJson } from "@ath/kit/canonical.ts";
import { defineCommand } from "@ath/kit/define.ts";
import { AthError } from "@ath/kit/errors.ts";
import { blake3Hex } from "@ath/kit/hash.ts";
import { custodyIndex, instanceOf, localStore } from "./context.ts";

const result = z.object({
  file: z.string(),
  status: z.enum(["new", "met again", "refused"]),
  hash: z.string(),
  mime: z.string().optional(),
  record: z.string().optional(),
  receipt: z.string().optional(),
  testimony: z.array(z.object({ hash: z.string(), name: z.string() })).optional(),
  problems: z.array(z.string()).optional(),
});

const contract = defineContract({
  key: "ingest",
  args: z.object({ files: z.array(z.string()).min(1), testimony: z.array(z.string()).default([]) }),
  argv: {
    positionals: [{ name: "files", variadic: true, required: true, help: "the artifacts, from disk" }],
    flags: { testimony: { type: "string", repeat: true, metavar: "FILE", help: "testimony delivered with them, matched by its subject" } },
  },
  data: z.object({ results: z.array(result) }),
});

/** Testimony delivered beside a file: `<file>.testimony.<ext>` (§9.2.1). */
function besideTestimony(file: string): string[] {
  const dir = dirname(file);
  const prefix = `${basename(file)}.testimony.`;
  return readdirSync(dir)
    .filter((n) => n.startsWith(prefix) && n.length > prefix.length)
    .sort()
    .map((n) => join(dir, n));
}

export const ingestCommand = defineCommand({
  meta: {
    summary: "place artifacts and their testimony in custody and write each record's projection",
    tier: "write",
    mutating: true,
    locks: ["repository", "index"],
    examples: ["ath ingest statement-03.pdf", "ath ingest photo.jpg --testimony photo.capture.yaml"],
  },
  contract,
  async run(ctx, a) {
    const inst = instanceOf(ctx);
    const store = localStore(ctx);
    const index = custodyIndex(ctx);
    const actor = ctx.caller.actor!;
    try {
      // explicit testimony is matched to its file by its subject; a file passed twice is ingested once
      const explicit = await Promise.all(
        a.testimony.map(async (t) => {
          const p = resolve(ctx.cwd, t);
          if (!existsSync(p)) throw new AthError("NOT_FOUND", `no testimony file ${t}`);
          const bytes = new Uint8Array(readFileSync(p));
          const doc = parseTestimony(bytes) as { subject?: unknown } | null;
          return { path: p, bytes, subject: typeof doc?.subject === "string" ? doc.subject : null, used: false };
        }),
      );
      const results: z.input<typeof result>[] = [];
      for (const f of [...new Set(a.files.map((x) => resolve(ctx.cwd, x)))]) {
        if (!existsSync(f) || !statSync(f).isFile()) throw new AthError("NOT_FOUND", `no file ${relative(ctx.cwd, f) || f}`);
        const bytes = new Uint8Array(readFileSync(f));
        const hash = await blake3Hex(bytes);
        const name = basename(f);
        const shown = relative(ctx.cwd, f) || f;
        const delivered: { path: string; bytes: Uint8Array }[] = besideTestimony(f).map((p) => ({
          path: p,
          bytes: new Uint8Array(readFileSync(p)),
        }));
        // explicit testimony goes with the file its subject names; with one file, all of it does, to be admitted or refused
        for (const t of explicit)
          if (!t.used && (t.subject === `b3:${hash}` || a.files.length === 1)) {
            t.used = true;
            delivered.push(t);
          }
        // admission: every delivered testimony, before anything is placed
        const problems: string[] = [];
        const admitted: { hash: string; name: string; bytes: Uint8Array; doc: Record<string, unknown> }[] = [];
        for (const t of delivered) {
          const c = admit(t.bytes, hash);
          if (!c.ok) problems.push(...c.problems.map((p) => `${basename(t.path)}: ${p}`));
          else admitted.push({ hash: await blake3Hex(t.bytes), name: basename(t.path), bytes: t.bytes, doc: c.doc! });
        }
        if (problems.length) {
          results.push({ file: shown, status: "refused", hash, problems });
          continue;
        }
        const held = recordView(inst, hash);
        const projection = held ? null : await intrinsicsOf(bytes, sniffMime(bytes, name));
        // placement: the artifact and its testimony in the local store, then the receipt that delivered them
        await store.put("artifacts", hash, bytes);
        index.putCopy({
          store: store.id,
          tree: "artifacts",
          hash,
          state: "verified",
          size: bytes.length,
          verified_at: ctx.wall.iso(),
          generation: 0,
        });
        for (const t of admitted) {
          await store.put("testimony", t.hash, t.bytes);
          index.putCopy({
            store: store.id,
            tree: "testimony",
            hash: t.hash,
            state: "verified",
            size: t.bytes.length,
            verified_at: ctx.wall.iso(),
            generation: 0,
          });
        }
        const received = ctx.wall.iso();
        const receipt = receiptBytes({
          actor,
          artifact: hash,
          instance: inst.config.id,
          name,
          received,
          testimony: admitted.map((t) => ({ hash: t.hash, name: t.name })),
        });
        const receiptHash = await blake3Hex(receipt);
        await store.put("testimony", receiptHash, receipt);
        index.putCopy({
          store: store.id,
          tree: "testimony",
          hash: receiptHash,
          state: "verified",
          size: receipt.length,
          verified_at: ctx.wall.iso(),
          generation: 0,
        });
        index.putReceipt({
          receipt: receiptHash,
          instance: inst.config.id,
          artifact: hash,
          name,
          received,
          actor,
          testimony: admitted.map((t) => ({ hash: t.hash, name: t.name })),
        });
        // the record: a new projection, or this ingest's receipt and origins added to the one it has
        const own = ownRecord(inst, hash);
        const met = own !== null || projection === null;
        const rec: RecordDoc = own ?? (projection ? { intrinsics: projection.value } : {});
        rec.receipts = [...(rec.receipts ?? []), { actor, received, name }];
        const origins = [...(rec.origins ?? [])];
        for (const t of admitted) if (!origins.some((o) => isOriginOf(o, t.doc))) origins.push(originOf(t.doc));
        if (origins.length) rec.origins = origins;
        writeRecord(inst, hash, rec);
        results.push({
          file: shown,
          status: met ? "met again" : "new",
          hash,
          mime: String((projection?.value ?? held?.record.intrinsics)?.mime),
          record: relative(inst.root, recordPath(inst, hash)),
          receipt: receiptHash,
          testimony: admitted.map((t) => ({ hash: t.hash, name: t.name })),
        });
        ctx.events.emit({ kind: "ingest.file", level: "debug", msg: `${met ? "met again" : "new"}  ${hash}  ${shown}` });
      }
      for (const t of explicit)
        if (!t.used)
          results.push({
            file: relative(ctx.cwd, t.path),
            status: "refused",
            hash: "",
            problems: [`its subject ${t.subject ?? "(none)"} is none of the files delivered with it`],
          });
      const refused = results.filter((r) => r.status === "refused");
      if (refused.length)
        throw new AthError("CONFLICT", refused.map((r) => `${r.file}: refused — ${r.problems!.join("; ")}`).join("\n"), {
          results: JSON.parse(canonicalJson(results)),
        });
      return { data: { results } };
    } finally {
      index.close();
    }
  },
  text(d, io) {
    for (const r of d.results) io.out(`${r.status.padEnd(9)}  ${r.hash}  ${r.file}${r.record ? `  → ${r.record}` : ""}\n`);
  },
});
