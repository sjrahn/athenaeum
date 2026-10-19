// select.ts — the selector languages (spec §10.7.1), one per family, each naming the format's own nodes: a CSS selector
// for html and xhtml; a JSON pointer in which `*` stands for any key or index for json, ndjson and yaml; `card` or a
// content-line name for vcard; a block kind for markdown; `header`, `part[type=…]` or a line rule for a message; a
// path pattern over a container's constituents. Every node a selector names is a `bytes=` span in a text format, or
// a `path=` route in a container (§10.7.3). A selector's language refusing it is a vocabulary check failure (§17.4).
import { selectAll } from "css-select";
import { isTag } from "domhandler";
import { encodePath } from "../address/address.ts";
import { type HtmlDoc, parseHtml, spanOf } from "../formats/html/dom.ts";
import { elementText } from "../formats/html/text.ts";
import { formatOf } from "../formats/index.ts";
import { type JsonDoc, type JsonNode, parseJson, scalarsIn } from "../formats/json/json.ts";
import { decodeCharset, decodeTransfer, type Message, parseMessage } from "../formats/mail/parse.ts";
import { lineLocal } from "../formats/mail/text.ts";
import { type MdBlock, type MdDoc, parseMarkdown } from "../formats/markdown/markdown.ts";
import { parseVcard, type VcardDoc, valueText } from "../formats/vcard/vcard.ts";
import { parseYaml } from "../formats/yaml/yaml.ts";

/** A node a selector names: its address, its text, its attributes (a field's `attr` source, §10.7.4). */
export interface Selected {
  at: string;
  start?: number;
  end?: number;
  path?: string;
  text: string;
  attr(name: string): string | null;
  level?: number;
}

export type Family = "html" | "json" | "vcard" | "markdown" | "rfc822" | "container";

/** The selector language a format's selectors are read in, or null where it has none. */
export function selectorFamily(mime: string): Family | null {
  const f = formatOf(mime);
  if (f.name === "html") return "html";
  if (f.name === "json" || f.name === "yaml") return "json";
  if (f.name === "vcard") return "vcard";
  if (f.name === "markdown") return "markdown";
  if (f.name === "rfc822") return "rfc822";
  if (f.container) return "container";
  return null;
}

const BLOCKS = new Set(["heading", "paragraph", "list", "list-item", "code", "table", "quote", "break", "front-matter"]);

/** A path pattern (§11.5.1): a prefix, or a glob where `*` stands for any run of characters, anchored at the start. */
export function patternMatches(pattern: string, s: string): boolean {
  if (!pattern.includes("*")) return s.startsWith(pattern);
  const re = new RegExp(
    `^${pattern
      .split("*")
      .map((p) => p.replace(/[.+?^${}()|[\]\\]/g, "\\$&"))
      .join(".*")}`,
    "s",
  );
  return re.test(s);
}

const pointerSegments = (p: string): string[] | null =>
  p === ""
    ? []
    : p.startsWith("/")
      ? p
          .slice(1)
          .split("/")
          .map((s) => s.replace(/~1/g, "/").replace(/~0/g, "~"))
      : null;

/** Why a selector is not one its family's language reads, or null. */
export function selectorProblem(family: Family, selector: unknown): string | null {
  switch (family) {
    case "html":
      if (typeof selector !== "string" || !selector.trim()) return "a CSS selector is a non-empty string";
      try {
        selectAll(selector, []);
        return null;
      } catch (e) {
        return `not a CSS selector: ${(e as Error).message}`;
      }
    case "json":
      return typeof selector === "string" && pointerSegments(selector) ? null : "a JSON pointer begins with `/`";
    case "vcard":
      return typeof selector === "string" && (selector === "card" || /^[A-Za-z][A-Za-z0-9-]*$/.test(selector))
        ? null
        : "`card` or a content-line name";
    case "markdown":
      return typeof selector === "string" && BLOCKS.has(selector) ? null : `a block kind: ${[...BLOCKS].join(", ")}`;
    case "rfc822": {
      if (selector === "header") return null;
      if (typeof selector === "string")
        return /^part\[type=[a-z0-9.+-]+\/[a-z0-9.+*-]+\]$/i.test(selector) ? null : "`header`, `part[type=<mime>]` or a line rule";
      const s = selector as Record<string, unknown> | null;
      if (!s || typeof s !== "object") return "a line rule is an object";
      const keys = Object.keys(s);
      if (keys.length !== 1) return "a line rule has one key: lines, from or blank";
      if (s.blank === true) return null;
      const re = s.lines ?? s.from;
      if (typeof re !== "string") return "a line rule is {lines: <regex>}, {from: <regex>} or {blank: true}";
      try {
        new RegExp(re);
        return null;
      } catch (e) {
        return `not a regular expression: ${(e as Error).message}`;
      }
    }
    case "container":
      return typeof selector === "string" && selector.length ? null : "a path pattern over the constituents";
  }
}

// ── the parses a selector reads ─────────────────────────────────────────────────────────────────────────────────────

export type SelectParse =
  | { family: "html"; doc: HtmlDoc }
  | { family: "json"; doc: JsonDoc }
  | { family: "vcard"; doc: VcardDoc }
  | { family: "markdown"; doc: MdDoc }
  | { family: "rfc822"; doc: Message }
  | { family: "container"; constituents: { path: string }[] };

export function selectParse(bytes: Uint8Array, mime: string, constituents: { path: string }[] = []): SelectParse | null {
  const family = selectorFamily(mime);
  switch (family) {
    case "html":
      return { family, doc: parseHtml(bytes) };
    case "json":
      return { family, doc: formatOf(mime).name === "yaml" ? parseYaml(bytes) : parseJson(bytes, mime === "application/x-ndjson") };
    case "vcard":
      return { family, doc: parseVcard(bytes) };
    case "markdown":
      return { family, doc: parseMarkdown(bytes) };
    case "rfc822":
      return { family, doc: parseMessage(bytes) };
    case "container":
      return { family, constituents };
    default:
      return null;
  }
}

const span = (a: number, b: number) => `bytes=${a},${b}`;

function jsonSelect(doc: JsonDoc, pointer: string): Selected[] {
  const segs = pointerSegments(pointer) ?? [];
  const out: JsonNode[] = [];
  const walk = (n: JsonNode, i: number) => {
    if (i === segs.length) {
      out.push(n);
      return;
    }
    for (const [k, c] of (n.children ?? []).entries()) {
      const key = n.kind === "array" ? String(k) : c.key;
      if (segs[i] === "*" || segs[i] === key) walk(c.node, i + 1);
    }
  };
  for (const r of doc.roots) walk(r, 0);
  return out.map((n) => ({
    at: span(n.start, n.end),
    start: n.start,
    end: n.end,
    text: n.children ? scalarsIn([n], n.start, n.end).join("\n") : n.text!,
    attr: (rel: string) => {
      const sub = jsonSelect({ roots: [n] }, rel.startsWith("/") ? rel : `/${rel}`)[0];
      return sub ? sub.text : null;
    },
  }));
}

function mdBlocks(doc: MdDoc, kind: string): MdBlock[] {
  const out: MdBlock[] = [];
  const walk = (bs: readonly MdBlock[]) => {
    for (const b of bs) {
      if (b.kind === kind) out.push(b);
      if (b.children) walk(b.children);
    }
  };
  walk(doc.blocks);
  return out;
}

function lineRuns(text: string, rule: Record<string, unknown>): [number, number][] {
  // runs over the decoded text's lines, as character offsets
  const lines: { s: number; e: number; t: string }[] = [];
  let p = 0;
  for (const t of text.split("\n")) {
    const content = t.replace(/\r$/, "");
    lines.push({ s: p, e: p + content.length, t: content });
    p += t.length + 1;
  }
  const out: [number, number][] = [];
  if (typeof rule.from === "string") {
    const re = new RegExp(rule.from);
    const k = lines.findIndex((l) => re.test(l.t));
    if (k >= 0) out.push([lines[k]!.s, lines.at(-1)!.e]);
    return out;
  }
  const keep =
    rule.blank === true ? (l: { t: string }) => l.t.trim() !== "" : (l: { t: string }) => new RegExp(String(rule.lines)).test(l.t);
  let cur: [number, number] | null = null;
  for (const l of lines) {
    if (keep(l)) {
      if (cur) cur[1] = l.e;
      else cur = [l.s, l.e];
    } else if (cur) {
      out.push(cur);
      cur = null;
    }
  }
  if (cur) out.push(cur);
  return out;
}

/** Every node `selector` names in the parse, in byte (or constituent) order. */
/** Whether a selector selects anything — an element the parser synthesised, which no byte span holds, included: a
 * shape's `matches` asks only that the artifact has it (§11.5). */
export function selects(p: SelectParse, selector: unknown): boolean {
  if (p.family === "html") return selectAll(String(selector), p.doc.doc.children).some(isTag);
  return select(p, selector).length > 0;
}

export function select(p: SelectParse, selector: unknown): Selected[] {
  switch (p.family) {
    case "html":
      return selectAll(String(selector), p.doc.doc.children)
        .filter(isTag)
        .flatMap((el) => {
          const s = spanOf(p.doc, el);
          return s
            ? [{ at: span(s.start, s.end), start: s.start, end: s.end, text: elementText(el), attr: (n: string) => el.attribs[n] ?? null }]
            : [];
        });
    case "json":
      return jsonSelect(p.doc, String(selector));
    case "vcard": {
      const sel = String(selector);
      if (sel === "card")
        return p.doc.cards.map((c) => ({
          at: span(c.start, c.end),
          start: c.start,
          end: c.end,
          text: c.lines.map(valueText).join("\n"),
          attr: () => null,
        }));
      return p.doc.lines
        .filter((l) => l.name === sel.toUpperCase())
        .map((l) => ({
          at: span(l.start, l.end),
          start: l.start,
          end: l.end,
          text: valueText(l),
          attr: (n: string) => l.params[n.toUpperCase()] ?? null,
        }));
    }
    case "markdown":
      return mdBlocks(p.doc, String(selector)).map((b) => ({
        at: span(b.start, b.end),
        start: b.start,
        end: b.end,
        text: b.text,
        attr: () => null,
        ...(b.level ? { level: b.level } : {}),
      }));
    case "rfc822": {
      const m = p.doc;
      if (selector === "header") {
        const t = new TextDecoder("latin1").decode(m.bytes.subarray(0, m.root.headerEnd));
        return [
          {
            at: span(0, m.root.headerEnd),
            start: 0,
            end: m.root.headerEnd,
            text: t.replace(/\r?\n[ \t]+/g, " ").trimEnd(),
            attr: () => null,
          },
        ];
      }
      if (typeof selector === "string") {
        const want = /type=([^\]]+)\]/.exec(selector)![1]!.toLowerCase();
        return m.parts
          .filter((x) => !x.children.length && patternMatches(want, x.mime))
          .map((x) => ({
            at: `path=${encodePath(x.path)}`,
            path: x.path,
            text: decodeCharset(decodeTransfer(m.bytes.subarray(x.bodyStart, x.bodyEnd), x.cte), x.charset),
            attr: () => null,
          }));
      }
      const out: Selected[] = [];
      for (const x of m.parts.length ? m.parts : [m.root]) {
        if (x.mime !== "text/plain" || x.children.length) continue;
        const body = decodeTransfer(m.bytes.subarray(x.bodyStart, x.bodyEnd), x.cte);
        const path = x.path || undefined;
        const at = (a: number, b: number) => (path ? `path=${encodePath(path)}&bytes=${a},${b}` : span(x.bodyStart + a, x.bodyStart + b));
        const text = decodeCharset(body, x.charset);
        if (!lineLocal(x.cte)) {
          out.push({ at: at(0, body.length), ...(path ? { path } : {}), text, attr: () => null });
          continue;
        }
        // character offsets map to bytes through the encoding: re-encode each prefix in the part's charset
        const enc = (s: string) => (x.charset && !/^utf-?8$/i.test(x.charset) ? s.length : new TextEncoder().encode(s).length);
        for (const [a, b] of lineRuns(text, selector as Record<string, unknown>))
          out.push({
            at: at(enc(text.slice(0, a)), enc(text.slice(0, b))),
            ...(path ? { path } : {}),
            text: text.slice(a, b),
            attr: () => null,
          });
      }
      return out;
    }
    case "container":
      return p.constituents
        .filter((c) => patternMatches(String(selector), c.path))
        .map((c) => ({ at: `path=${encodePath(c.path)}`, path: c.path, text: "", attr: () => null }));
  }
}
