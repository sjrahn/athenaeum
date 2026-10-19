// opf.ts — an EPUB's package document (the OPF the OCF container names): its Dublin Core, its manifest with each
// item's media type, its spine as entry paths in reading order. XML is parsed with htmlparser2 in xmlMode.

import { AthError } from "@ath/kit/errors.ts";
import { DomUtils, parseDocument } from "htmlparser2";
import type { MemberBytes } from "../zip/roster.ts";

export interface Opf {
  path: string;
  title: string | null;
  creators: string[];
  language: string | null;
  identifier: string | null;
  identifiers: { value: string; scheme?: string }[];
  date: string | null;
  publisher: string | null;
  /** The manifest: id → { href (resolved member path), mediaType }. */
  manifest: Map<string, { href: string; mediaType: string }>;
  /** Member paths in spine order. */
  spine: string[];
}

const utf8 = new TextDecoder("utf-8");

function resolvePath(base: string, href: string): string {
  const dir = base.includes("/") ? base.slice(0, base.lastIndexOf("/") + 1) : "";
  const parts = `${dir}${decodeURIComponent(href.split("#")[0]!)}`.split("/");
  const out: string[] = [];
  for (const p of parts) {
    if (p === "" || p === ".") continue;
    if (p === "..") out.pop();
    else out.push(p);
  }
  return out.join("/");
}

/** The package document's path from META-INF/container.xml. */
export function rootfilePath(members: MemberBytes[]): string {
  const c = members.find((m) => m.path === "META-INF/container.xml");
  if (!c) throw new AthError("EXTERNAL", "epub: no META-INF/container.xml");
  const doc = parseDocument(utf8.decode(c.bytes), { xmlMode: true });
  const rf = DomUtils.findOne((e) => e.name === "rootfile", doc.children, true);
  const p = rf?.attribs["full-path"];
  if (!p) throw new AthError("EXTERNAL", "epub: container.xml names no rootfile");
  return p;
}

export function parseOpf(path: string, xml: string): Opf {
  const doc = parseDocument(xml, { xmlMode: true });
  const local = (name: string) => (name.includes(":") ? name.slice(name.indexOf(":") + 1) : name);
  const els = (name: string) => DomUtils.findAll((e) => local(e.name) === name, doc.children);
  const text = (name: string) =>
    els(name)
      .map((e) => DomUtils.textContent(e).trim())
      .filter(Boolean);
  const pkg = DomUtils.findOne((e) => local(e.name) === "package", doc.children, true);
  const uid = pkg?.attribs["unique-identifier"];
  const identifiers = els("identifier").map((e) => {
    const scheme = e.attribs["opf:scheme"] ?? e.attribs.scheme;
    const v = DomUtils.textContent(e).trim();
    return scheme ? { value: v, scheme, id: e.attribs.id } : { value: v, id: e.attribs.id };
  });
  const unique = identifiers.find((i) => uid && i.id === uid) ?? identifiers[0];
  const manifest = new Map<string, { href: string; mediaType: string }>();
  for (const item of els("item")) {
    const id = item.attribs.id;
    const href = item.attribs.href;
    if (!id || !href) continue;
    manifest.set(id, { href: resolvePath(path, href), mediaType: item.attribs["media-type"] ?? "" });
  }
  const spine: string[] = [];
  for (const ref of els("itemref")) {
    const idref = ref.attribs.idref;
    const item = idref ? manifest.get(idref) : undefined;
    if (item) spine.push(item.href);
  }
  return {
    path,
    title: text("title")[0] ?? null,
    creators: text("creator"),
    language: text("language")[0] ?? null,
    identifier: unique?.value ?? null,
    identifiers: identifiers.map(({ value, scheme }) => (scheme ? { value, scheme } : { value })),
    date: text("date")[0] ?? null,
    publisher: text("publisher")[0] ?? null,
    manifest,
    spine,
  };
}

export function readOpf(members: MemberBytes[]): Opf {
  const path = rootfilePath(members);
  const opf = members.find((m) => m.path === path);
  if (!opf) throw new AthError("EXTERNAL", `epub: rootfile ${path} is not in the archive`);
  return parseOpf(path, utf8.decode(opf.bytes));
}
