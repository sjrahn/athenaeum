// resolve.ts — `ath resolve <anchor> [--trace] [--out <file>]` (spec §19.5): the artifact, the surface or the reading at
// an address. A route through a container to an asset canonicalises to the asset's own id (§7.5.2); one into a part
// stays on the container. A region the artifact does not have is refused (§7.4.3). `--trace` reports the route custody
// took (§18.8.2); `--out` writes the bytes at the address — a page or a box of a PDF as a PNG a reader can look at.
import { resolve as resolvePath } from "node:path";
import { defineContract, z } from "@ath/contracts";
import { traceLines } from "@ath/custody";
import { formatAddress, parseAddress, type Region } from "@ath/engine/address/address.ts";
import { regionProblem } from "@ath/engine/address/anchor.ts";
import { formatOf, intrinsicsOf, Parses, surfaceAt } from "@ath/engine/formats/index.ts";
import { renderPage } from "@ath/engine/formats/pdf/render.ts";
import { sniffMime } from "@ath/engine/formats/sniff.ts";
import { containersIndex, holdings, recordView, resolvePrefix } from "@ath/engine/instance/instance.ts";
import { fieldsOf, readingAt, scopeAt } from "@ath/engine/record/tree.ts";
import { defineCommand } from "@ath/kit/define.ts";
import { AthError } from "@ath/kit/errors.ts";
import { writeAtomic } from "@ath/kit/fs.ts";
import { resolver } from "./artifacts.ts";
import { custodyIndex, instanceOf, localStore } from "./context.ts";

const contract = defineContract({
  key: "resolve",
  args: z.object({ anchor: z.string(), trace: z.boolean().default(false), out: z.string().optional() }),
  argv: {
    positionals: [{ name: "anchor", required: true, help: "ath://<hash or prefix>?<at>, or a hash" }],
    flags: {
      trace: { type: "boolean", help: "the route custody took, and every other residence the index knows" },
      out: { type: "string", metavar: "FILE", help: "write the bytes at the address (a PDF page or box as PNG)" },
    },
  },
  data: z.object({
    anchor: z.string(),
    artifact: z.string(),
    mime: z.string().nullable(),
    class: z.string().nullable(),
    bytes: z.number(),
    reading: z.record(z.string(), z.unknown()).nullable(),
    scope: z.object({ form: z.union([z.string(), z.array(z.string())]), fields: z.record(z.string(), z.unknown()) }).nullable(),
    surface: z.string().nullable(),
    route: z.array(z.string()).optional(),
    out: z.string().optional(),
  }),
});

export const resolveCommand = defineCommand({
  meta: {
    summary: "the artifact, the surface or the reading at an address",
    tier: "read",
    mutating: false,
    examples: ["ath resolve 'ath://5e6e497d?page=1&bbox=0.14,0.69,0.09,0.01'"],
  },
  contract,
  async run(ctx, a) {
    const inst = instanceOf(ctx);
    const m = /^(?:ath:\/\/)?(?:b3:)?([0-9a-f]{8,64})(?:\?(.+))?$/.exec(a.anchor.trim());
    if (!m) throw new AthError("USAGE", `'${a.anchor}' is not an anchor: ath://<hash>?<at>`);
    const known = new Set([...holdings(inst).keys(), ...containersIndex(inst).keys()]);
    let hash = resolvePrefix(m[1]!, known);
    let address = parseAddress(m[2] ?? "whole");
    const index = custodyIndex(ctx);
    try {
      const { resolve } = resolver(inst, localStore(ctx), index);
      let got = await resolve(hash);
      // an asset never said anything about has no record: its intrinsics are the format's, sniffed by the name its
      // container gives it (§10.1.3)
      const containers = containersIndex(inst);
      const intrinsicsFor = async (h: string, b: Uint8Array) =>
        recordView(inst, h)?.record.intrinsics ??
        (await intrinsicsOf(b, sniffMime(b, containers.get(h)?.[0]?.path.split("/").pop()))).value;
      let intr = await intrinsicsFor(hash, got.bytes);
      // a route to an asset canonicalises to the asset's own id; the rest of the address applies in it
      const paths = new Set(address.regions.map((r) => r.path));
      if (paths.size === 1 && [...paths][0] !== undefined) {
        const path = [...paths][0]!;
        const c = (intr.constituents as { path: string; blake3: string; kind: string }[] | undefined)?.find((x) => x.path === path);
        if (!c) throw new AthError("NOT_FOUND", `${hash} has no constituent at path ${path}`);
        if (c.kind === "asset") {
          hash = c.blake3;
          got = await resolve(hash);
          intr = await intrinsicsFor(hash, got.bytes);
          address = {
            regions: address.regions.map(({ path: _p, ...rest }) => (Object.keys(rest).length ? rest : { whole: true as const })),
            ...(address.aspect ? { aspect: address.aspect } : {}),
          };
        }
      } else if (paths.size > 1) throw new AthError("USAGE", "a union routes into one constituent at most");
      for (const r of address.regions) {
        const p = regionProblem(intr, r);
        if (p) throw new AthError("NOT_FOUND", `${hash}: ${p}`);
      }
      const at = formatAddress({ regions: address.regions });
      const mime = typeof intr.mime === "string" ? intr.mime : null;
      const format = mime ? formatOf(mime) : null;
      const rec = recordView(inst, hash)?.record ?? null;
      const scope = rec ? scopeAt(rec, at) : null;
      const reading = rec ? readingAt(rec, at) : null;
      let surface: string | null = null;
      if (format?.class === "structured" && format.ops[0]) surface = await surfaceAt(new Parses(got.bytes), format.ops[0], address.regions);
      const data: z.input<typeof contract.data> = {
        anchor: `ath://${hash}${at === "whole" ? "" : `?${at}`}${address.aspect ? `&${address.aspect}` : ""}`,
        artifact: hash,
        mime,
        class: format?.class ?? null,
        bytes: got.bytes.length,
        reading: reading as Record<string, unknown> | null,
        scope: scope ? { form: scope.form, fields: fieldsOf(scope) } : null,
        surface,
      };
      if (a.trace) data.route = traceLines(got.trace);
      if (a.out) {
        const out = resolvePath(ctx.cwd, a.out);
        writeAtomic(out, await bytesAt(got.bytes, mime, address.regions));
        data.out = out;
      }
      return { data };
    } finally {
      index.close();
    }
  },
  text(d, io) {
    io.out(`${d.anchor}\n${d.mime ?? "?"} · ${d.class ?? "unregistered"} · ${d.bytes} bytes\n`);
    if (d.scope)
      io.out(`scope    ${[d.scope.form].flat().join(", ")} ${Object.keys(d.scope.fields).length ? JSON.stringify(d.scope.fields) : ""}\n`);
    if (d.reading)
      for (const [k, v] of Object.entries(d.reading)) io.out(`${k.padEnd(8)} ${typeof v === "string" ? v : JSON.stringify(v)}\n`);
    if (d.surface !== null) io.out(`surface  ${d.surface}\n`);
    for (const l of d.route ?? []) io.out(`${l}\n`);
    if (d.out) io.out(`wrote ${d.out}\n`);
  },
});

/** The bytes at an address: a byte span's slice, a PDF page or box rendered, else the artifact's bytes. */
async function bytesAt(bytes: Uint8Array, mime: string | null, regions: readonly Region[]): Promise<Uint8Array> {
  const r = regions[0]!;
  if (regions.length > 1) throw new AthError("USAGE", "--out writes one region");
  if (r.bytes) return bytes.subarray(r.bytes[0], r.bytes[1]);
  if (mime === "application/pdf" && r.page !== undefined) return renderPage(bytes, r.page, 2, r.bbox);
  return bytes;
}
