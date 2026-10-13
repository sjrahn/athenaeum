// dom.ts — the parsed HTML with byte spans: parse5 (spec-compliant) over the htmlparser2 tree adapter so css-select
// runs on it, plus the code-unit → byte map (D-html) that turns `sourceCodeLocation` into `bytes=a,b`. The span of
// an element runs from its start tag's first byte to its end tag's last byte, half-open; an implied end is flagged.

import { selectAll, selectOne } from "css-select";
import { type Document, type Element, isTag, type Node } from "domhandler";
import { parse } from "parse5";
import { adapter } from "parse5-htmlparser2-tree-adapter";

export interface HtmlDoc {
  text: string;
  bytes: Uint8Array;
  doc: Document;
  /** Byte offset of each UTF-16 code unit (length + 1). */
  map: Uint32Array;
  encoding: string;
}

export interface Span {
  start: number;
  end: number;
  implied: boolean;
}

/** The charset: a BOM, else a meta charset in the first 2 KiB, else utf-8. Only UTF-8 and latin1 are decoded. */
export function sniffCharset(bytes: Uint8Array): string {
  if (bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) return "utf-8";
  const head = new TextDecoder("latin1").decode(bytes.subarray(0, 2048)).toLowerCase();
  const m = /charset=["']?\s*([a-z0-9_-]+)/.exec(head);
  return m ? m[1]! : "utf-8";
}

export function byteMap(text: string): Uint32Array {
  const map = new Uint32Array(text.length + 1);
  let b = 0;
  for (let i = 0; i < text.length; i++) {
    map[i] = b;
    const c = text.charCodeAt(i);
    if (c < 0x80) b += 1;
    else if (c < 0x800) b += 2;
    else if (c >= 0xd800 && c <= 0xdbff) {
      b += 4;
      i++;
      map[i] = b;
    } else b += 3;
  }
  map[text.length] = b;
  return map;
}

export function parseHtml(bytes: Uint8Array): HtmlDoc {
  const encoding = sniffCharset(bytes);
  const label = /^(utf-?8)$/i.test(encoding) ? "utf-8" : /^(iso-8859-1|latin1|windows-1252)$/i.test(encoding) ? "windows-1252" : "utf-8";
  const text = new TextDecoder(label, { ignoreBOM: true }).decode(bytes);
  const doc = parse(text, { treeAdapter: adapter, sourceCodeLocationInfo: true });
  // for a non-UTF-8 decode the byte map is 1:1 per code unit (single-byte encodings)
  const map = label === "utf-8" ? byteMap(text) : Uint32Array.from({ length: text.length + 1 }, (_, i) => i);
  return { text, bytes, doc, map, encoding };
}

type Loc = { startOffset: number; endOffset: number; endTag?: { endOffset: number } | null };

/** The byte span of a node, or null when the parser gave it no location (synthesised html/head/body). */
export function spanOf(d: HtmlDoc, n: Node): Span | null {
  const loc = (n as unknown as { sourceCodeLocation?: Loc | null }).sourceCodeLocation;
  if (!loc) return null;
  const start = d.map[loc.startOffset]!;
  if (isTag(n)) {
    if (loc.endTag) return { start, end: d.map[loc.endTag.endOffset]!, implied: false };
    // implied end: the last descendant's end, else the start tag's end
    let end = d.map[loc.endOffset]!;
    const stack: Node[] = [...n.children];
    while (stack.length) {
      const c = stack.pop()!;
      const s = spanOf(d, c);
      if (s && s.end > end) end = s.end;
      if (isTag(c)) stack.push(...c.children);
    }
    return { start, end, implied: true };
  }
  return { start, end: d.map[loc.endOffset]!, implied: false };
}

export function select(d: HtmlDoc, selector: string, root: Node | Node[] = d.doc): Element[] {
  return selectAll(selector, root as never) as Element[];
}

export function selectFirst(d: HtmlDoc, selector: string, root: Node | Node[] = d.doc): Element | null {
  return selectOne(selector, root as never) as Element | null;
}

export function matchesSelector(d: HtmlDoc, selector: string): boolean {
  try {
    return selectFirst(d, selector) !== null;
  } catch {
    return false;
  }
}

/** The smallest element whose span covers [start, end), or null. */
export function elementAt(d: HtmlDoc, start: number, end: number): Element | null {
  let best: Element | null = null;
  let bestSize = Infinity;
  const stack: Node[] = [d.doc];
  while (stack.length) {
    const n = stack.pop()!;
    if (isTag(n)) {
      const s = spanOf(d, n);
      if (s && s.start <= start && s.end >= end && s.end - s.start < bestSize) {
        best = n;
        bestSize = s.end - s.start;
      }
    }
    if ("children" in n && Array.isArray((n as { children?: Node[] }).children)) stack.push(...(n as { children: Node[] }).children);
  }
  return best;
}
