// markdown.ts — markdown's block structure as CommonMark and GFM define it, in a subset: front matter, headings (ATX
// and setext), paragraphs, block quotes, lists and their items, fenced and indented code, pipe tables and thematic
// breaks, each with its byte span covering its lines, its markers included (spec §10.5.4). Inline markup is not
// parsed. `markdown.text@1` is the surface: the blocks in a span with their block markers removed — `#` runs, `>`, a
// list bullet or number, fence lines — and inline markup verbatim.
import { registerOp } from "../ops.ts";

export type BlockKind = "heading" | "paragraph" | "list" | "list-item" | "code" | "table" | "quote" | "break" | "front-matter";

export interface MdBlock {
  kind: BlockKind;
  start: number;
  end: number;
  /** The block's text with its markers removed. */
  text: string;
  level?: number;
  children?: MdBlock[];
}

export interface MdDoc {
  blocks: MdBlock[];
}

export const MARKDOWN_TEXT_OP = "markdown.text@1";

interface Line {
  text: string;
  start: number;
  /** End of the line's content, its line break excluded. */
  end: number;
}

function lines(b: Uint8Array): Line[] {
  const dec = new TextDecoder("utf-8");
  const out: Line[] = [];
  let i = 0;
  while (i < b.length) {
    let nl = b.indexOf(0x0a, i);
    if (nl === -1) nl = b.length;
    const e = nl > i && b[nl - 1] === 0x0d ? nl - 1 : nl;
    out.push({ text: dec.decode(b.subarray(i, e)), start: i, end: e });
    i = nl + 1;
  }
  return out;
}

const blank = (l: Line | undefined) => !l?.text.trim();
const FENCE = /^ {0,3}(`{3,}|~{3,})/;
const ATX = /^ {0,3}(#{1,6})(?:[ \t]+|$)(.*?)(?:[ \t]+#+[ \t]*)?$/;
const BREAK = /^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$/;
const QUOTE = /^ {0,3}> ?/;
const ITEM = /^( {0,3})([-*+]|\d{1,9}[.)])([ \t]+|$)/;
const DELIM = /^ *\|? *:?-+:? *(\| *:?-+:? *)*\|? *$/;
const SETEXT = /^ {0,3}(=+|-+)[ \t]*$/;

const starts = (l: Line) => FENCE.test(l.text) || ATX.test(l.text) || BREAK.test(l.text) || QUOTE.test(l.text) || ITEM.test(l.text);

function parse(ls: Line[], from: number, to: number, top: boolean): MdBlock[] {
  const out: MdBlock[] = [];
  let i = from;
  if (top && ls[0]?.text === "---") {
    let k = 1;
    while (k < ls.length && ls[k]!.text !== "---" && ls[k]!.text !== "...") k++;
    if (k < ls.length) {
      out.push({
        kind: "front-matter",
        start: ls[0]!.start,
        end: ls[k]!.end,
        text: ls
          .slice(1, k)
          .map((l) => l.text)
          .join("\n"),
      });
      i = k + 1;
    }
  }
  while (i < to) {
    const l = ls[i]!;
    if (blank(l)) {
      i++;
      continue;
    }
    const fence = FENCE.exec(l.text);
    if (fence) {
      let k = i + 1;
      while (k < to && !ls[k]!.text.trimStart().startsWith(fence[1]!)) k++;
      const close = Math.min(k, to - 1);
      out.push({
        kind: "code",
        start: l.start,
        end: ls[close]!.end,
        text: ls
          .slice(i + 1, k)
          .map((x) => x.text)
          .join("\n"),
      });
      i = k + 1;
      continue;
    }
    const atx = ATX.exec(l.text);
    if (atx) {
      out.push({ kind: "heading", level: atx[1]!.length, start: l.start, end: l.end, text: atx[2]!.trim() });
      i++;
      continue;
    }
    if (BREAK.test(l.text)) {
      out.push({ kind: "break", start: l.start, end: l.end, text: "" });
      i++;
      continue;
    }
    if (QUOTE.test(l.text)) {
      let k = i;
      while (k < to && QUOTE.test(ls[k]!.text)) k++;
      out.push({
        kind: "quote",
        start: l.start,
        end: ls[k - 1]!.end,
        text: ls
          .slice(i, k)
          .map((x) => x.text.replace(QUOTE, ""))
          .join("\n"),
      });
      i = k;
      continue;
    }
    const item = ITEM.exec(l.text);
    if (item) {
      const items: MdBlock[] = [];
      let k = i;
      while (k < to) {
        const m = ITEM.exec(ls[k]!.text);
        if (!m) break;
        const indent = m[0].length;
        let e = k + 1;
        // the item runs on while lines are indented to its content, or are lazy continuations of its paragraph
        while (e < to) {
          const x = ls[e]!;
          if (blank(x)) {
            if (e + 1 < to && /^\s/.test(ls[e + 1]!.text) && !blank(ls[e + 1])) {
              e++;
              continue;
            }
            break;
          }
          if (ITEM.test(x.text) && !/^\s{2,}/.test(x.text)) break;
          if (!/^\s/.test(x.text) && starts(x)) break;
          e++;
        }
        const body = ls.slice(k, e).map((x, n) => (n === 0 ? x.text.slice(indent) : x.text.replace(new RegExp(`^ {0,${indent}}`), "")));
        items.push({ kind: "list-item", start: ls[k]!.start, end: ls[e - 1]!.end, text: body.join("\n").trim() });
        k = e;
        while (k < to && blank(ls[k]) && k + 1 < to && ITEM.test(ls[k + 1]!.text)) k++;
      }
      out.push({
        kind: "list",
        start: items[0]!.start,
        end: items.at(-1)!.end,
        text: items.map((x) => x.text).join("\n"),
        children: items,
      });
      i = k;
      continue;
    }
    if (l.text.includes("|") && i + 1 < to && DELIM.test(ls[i + 1]!.text) && ls[i + 1]!.text.includes("-")) {
      let k = i + 2;
      while (k < to && !blank(ls[k]) && ls[k]!.text.includes("|")) k++;
      out.push({ kind: "table", start: l.start, end: ls[k - 1]!.end, text: [l, ...ls.slice(i + 2, k)].map((x) => x.text).join("\n") });
      i = k;
      continue;
    }
    if (/^( {4}|\t)/.test(l.text)) {
      let k = i;
      while (k < to && (/^( {4}|\t)/.test(ls[k]!.text) || (blank(ls[k]) && k + 1 < to && /^( {4}|\t)/.test(ls[k + 1]!.text)))) k++;
      out.push({
        kind: "code",
        start: l.start,
        end: ls[k - 1]!.end,
        text: ls
          .slice(i, k)
          .map((x) => x.text.replace(/^( {4}|\t)/, ""))
          .join("\n"),
      });
      i = k;
      continue;
    }
    // a paragraph, closed by a blank line, a block that interrupts it, or a setext underline
    let k = i + 1;
    while (k < to && !blank(ls[k]) && !starts(ls[k]!) && !SETEXT.test(ls[k]!.text)) k++;
    if (k < to && SETEXT.test(ls[k]!.text) && !blank(ls[k])) {
      out.push({
        kind: "heading",
        level: ls[k]!.text.trim().startsWith("=") ? 1 : 2,
        start: l.start,
        end: ls[k]!.end,
        text: ls
          .slice(i, k)
          .map((x) => x.text.trim())
          .join("\n"),
      });
      i = k + 1;
      continue;
    }
    out.push({
      kind: "paragraph",
      start: l.start,
      end: ls[k - 1]!.end,
      text: ls
        .slice(i, k)
        .map((x) => x.text.trim())
        .join("\n"),
    });
    i = k;
  }
  return out;
}

export function parseMarkdown(bytes: Uint8Array): MdDoc {
  const ls = lines(bytes);
  return { blocks: parse(ls, 0, ls.length, true) };
}

/** The blocks inside [a, b): a list's items stand for it, so nothing is emitted twice. */
export function blocksIn(d: MdDoc, a: number, b: number): MdBlock[] {
  const out: MdBlock[] = [];
  const walk = (bs: readonly MdBlock[]) => {
    for (const x of bs) {
      if (x.end <= a || x.start >= b) continue;
      if (x.children) walk(x.children);
      else if (x.start >= a && x.end <= b) out.push(x);
    }
  };
  walk(d.blocks);
  return out;
}

registerOp<MdDoc>({
  name: MARKDOWN_TEXT_OP,
  kind: "surface",
  family: "markdown",
  parse: parseMarkdown,
  surface: (d, r) => {
    if (r.path !== undefined) return null;
    const [a, b] = r.whole ? [0, Number.MAX_SAFE_INTEGER] : (r.bytes ?? [-1, -1]);
    if (a < 0) return null;
    return blocksIn(d, a, b)
      .filter((x) => x.kind !== "break")
      .map((x) => x.text)
      .join("\n");
  },
});
