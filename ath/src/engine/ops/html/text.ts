// text.ts — `html.text@1`, the quote surface of a markup scope (D-html): the text of the nodes inside a byte span,
// with head/script/style/template/noscript/svg dropped, block elements and <br> ending a line, td/th separated by a
// tab, whitespace runs collapsed to one space, lines trimmed, blank runs collapsed. Also `html.attr@1 <name>` and
// `html.title@1`.
import { type Element, isTag, isText, type Node } from "domhandler";
import { registerOp } from "../registry.ts";
import { elementAt, type HtmlDoc, parseHtml, select, spanOf } from "./dom.ts";

export const HTML_TEXT_OP = "html.text@1";
export const HTML_ATTR_OP = "html.attr@1";
export const HTML_TITLE_OP = "html.title@1";

const DROP = new Set(["head", "script", "style", "template", "noscript", "svg", "iframe"]);
const BLOCK = new Set([
  "address",
  "article",
  "aside",
  "blockquote",
  "dd",
  "details",
  "dialog",
  "div",
  "dl",
  "dt",
  "fieldset",
  "figcaption",
  "figure",
  "footer",
  "form",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "header",
  "hr",
  "li",
  "main",
  "nav",
  "ol",
  "p",
  "pre",
  "section",
  "table",
  "tr",
  "ul",
  "body",
  "html",
  "caption",
  "thead",
  "tbody",
  "tfoot",
  "summary",
  "option",
  "legend",
]);

function collect(n: Node, out: string[], pre: boolean): void {
  if (isText(n)) {
    out.push(pre ? n.data : n.data.replace(/\s+/g, " "));
    return;
  }
  if (!isTag(n)) return;
  const name = n.name.toLowerCase();
  if (DROP.has(name)) return;
  if (name === "br") {
    out.push("\n");
    return;
  }
  const block = BLOCK.has(name);
  if (block) out.push("\n");
  if (name === "td" || name === "th") out.push("\t");
  for (const c of n.children) collect(c, out, pre || name === "pre");
  if (block) out.push("\n");
}

/** Collapse to the surface form: trim each line, drop empty lines, single spaces inside a line. */
export function surfaceText(raw: string): string {
  return raw
    .split("\n")
    .map((l) =>
      l
        .replace(/[ \t]*\t[ \t]*/g, "\t")
        .replace(/ {2,}/g, " ")
        .trim(),
    )
    .filter((l) => l.length > 0)
    .join("\n");
}

/** The text of one element. */
export function elementText(el: Element): string {
  const out: string[] = [];
  collect(el, out, false);
  return surfaceText(out.join(""));
}

/** The text of the smallest element covering `bytes=start,end`; null when no element aligns. */
export function textAt(d: HtmlDoc, start: number, end: number): string | null {
  const el = elementAt(d, start, end);
  if (!el) return null;
  const s = spanOf(d, el);
  if (!s || s.start !== start || s.end !== end) return null;
  return elementText(el);
}

export function attrAt(d: HtmlDoc, start: number, end: number, attr: string): string | null {
  const el = elementAt(d, start, end);
  if (!el) return null;
  return el.attribs[attr] ?? null;
}

export function rootAttr(d: HtmlDoc, attr: string): string | null {
  const html = select(d, "html")[0];
  return html?.attribs[attr] ?? null;
}

export function titleOf(d: HtmlDoc): string | null {
  const t = select(d, "title")[0];
  return t ? elementText(t) : null;
}

/** Every text run of the document with its byte span (for the remainder count); drop-set subtrees excluded. */
export function textRuns(d: HtmlDoc): { start: number; end: number; text: string }[] {
  const out: { start: number; end: number; text: string }[] = [];
  const walk = (n: Node) => {
    if (isText(n)) {
      const t = n.data.replace(/\s+/g, " ").trim();
      if (!t) return;
      const s = spanOf(d, n);
      if (s) out.push({ start: s.start, end: s.end, text: t });
      return;
    }
    if (!isTag(n)) {
      if ("children" in n) for (const c of (n as { children: Node[] }).children) walk(c);
      return;
    }
    if (DROP.has(n.name.toLowerCase())) return;
    for (const c of n.children) walk(c);
  };
  walk(d.doc);
  return out;
}

// ── the ops the ontology names (D-derivation) ───────────────────────────────────────────────────────────────────────
const parse = (bytes: Uint8Array) => parseHtml(bytes);

registerOp<HtmlDoc>({
  name: HTML_TEXT_OP,
  family: "html",
  parse,
  surface: (d, m) => {
    if (m.kind === "whole") {
      const root = select(d, "html")[0];
      return root ? elementText(root) : null;
    }
    return m.kind === "bytes" ? textAt(d, m.start, m.end) : null;
  },
});

registerOp<HtmlDoc>({
  name: HTML_ATTR_OP,
  family: "html",
  parse,
  arg: (a) => (a ? null : `${HTML_ATTR_OP} needs the attribute name as its argument`),
  surface: (d, m, arg) => {
    if (!arg) return null;
    if (m.kind === "whole") return rootAttr(d, arg);
    return m.kind === "bytes" ? attrAt(d, m.start, m.end, arg) : null;
  },
});

registerOp<HtmlDoc>({
  name: HTML_TITLE_OP,
  family: "html",
  parse,
  surface: (d, m) => (m.kind === "whole" ? titleOf(d) : null),
});
