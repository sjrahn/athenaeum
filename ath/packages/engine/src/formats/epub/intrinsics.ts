// intrinsics.ts — what an EPUB defines about itself (spec §10.2, §10.3): the package's Dublin Core, the package
// document's path, the spine as entry paths in reading order; its constituents — the images, audio and video the
// package lists as assets, every other entry (the package document, the content documents, the navigation,
// stylesheets, fonts, the container files) as a part with its media type and size.
import type { Constituent, IntrinsicsResult, J } from "../format.ts";
import { zipEntries } from "../zip/roster.ts";
import { readOpf } from "./opf.ts";

export async function epubIntrinsics(bytes: Uint8Array): Promise<IntrinsicsResult> {
  const entries = await zipEntries(bytes);
  const opf = readOpf(entries.map((e) => ({ path: e.path, blake3: e.blake3, bytes: e.read() })));
  const facts: J = {};
  if (opf.title) facts.title = opf.title;
  if (opf.creators.length) facts.creator = opf.creators.join("; ");
  if (opf.language) facts.language = opf.language;
  if (opf.identifier) facts.identifier = opf.identifier;
  const isbn = opf.identifiers.find((i) => i.scheme?.toUpperCase() === "ISBN");
  if (isbn) facts.isbn = isbn.value;
  if (opf.date) facts.date = opf.date;
  if (opf.publisher) facts.publisher = opf.publisher;
  facts.package = opf.path;
  facts.spine = opf.spine;
  const types = new Map([...opf.manifest.values()].map((m) => [m.href, m.mediaType]));
  const constituents: Constituent[] = entries.map((e) => {
    const mime = types.get(e.path);
    const asset = !!mime && /^(image|audio|video)\//.test(mime);
    const c: Constituent = { path: e.path, blake3: e.blake3, kind: asset ? "asset" : "part", read: e.read, name: e.path.split("/").pop() };
    if (asset) c.fields = { mime: mime! };
    else c.intrinsics = { ...(mime ? { mime } : {}), bytes: e.read().length };
    return c;
  });
  return { facts, constituents };
}
