// intrinsics.ts — what an archive and an Office package define about themselves (spec §10.3). A zip: every file
// entry an asset at its entry name. An OOXML package (docx, xlsx, pptx): every entry under a `media/` or
// `embeddings/` directory an asset; every other package part a part, with its content type from
// `[Content_Types].xml` and its size.
import { DomUtils, parseDocument } from "htmlparser2";
import type { Constituent, IntrinsicsResult } from "../format.ts";
import { zipEntries } from "./roster.ts";

export async function zipIntrinsics(bytes: Uint8Array): Promise<IntrinsicsResult> {
  const entries = await zipEntries(bytes);
  return {
    facts: {},
    constituents: entries.map((e) => ({ path: e.path, blake3: e.blake3, kind: "asset", read: e.read, name: e.path.split("/").pop() })),
  };
}

/** An OOXML package's content types: part name → type, by override, else by extension default. */
function contentTypes(xml: string): (path: string) => string | undefined {
  const doc = parseDocument(xml, { xmlMode: true });
  const defaults = new Map<string, string>();
  const overrides = new Map<string, string>();
  for (const e of DomUtils.findAll((x) => x.name === "Default", doc.children))
    defaults.set((e.attribs.Extension ?? "").toLowerCase(), e.attribs.ContentType ?? "");
  for (const e of DomUtils.findAll((x) => x.name === "Override", doc.children))
    overrides.set((e.attribs.PartName ?? "").replace(/^\//, ""), e.attribs.ContentType ?? "");
  return (p) => overrides.get(p) ?? defaults.get(p.split(".").pop()?.toLowerCase() ?? "");
}

export async function ooxmlIntrinsics(bytes: Uint8Array): Promise<IntrinsicsResult> {
  const entries = await zipEntries(bytes);
  const ct = entries.find((e) => e.path === "[Content_Types].xml");
  const typeOf = ct ? contentTypes(new TextDecoder().decode(ct.read())) : () => undefined;
  const constituents: Constituent[] = entries.map((e) => {
    const asset = /(^|\/)(media|embeddings)\//.test(e.path);
    const c: Constituent = { path: e.path, blake3: e.blake3, kind: asset ? "asset" : "part", read: e.read, name: e.path.split("/").pop() };
    if (!asset) {
      const mime = typeOf(e.path);
      c.intrinsics = { ...(mime ? { mime } : {}), bytes: e.read().length };
    }
    return c;
  });
  return { facts: {}, constituents };
}
