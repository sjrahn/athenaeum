// text.ts — `eml.text@1`, the quote surface of a mail scope (D-rfc822): a raw byte span inside a text body part,
// transfer-decoded and charset-decoded, CRLF folded to LF, trailing whitespace trimmed. Also the mechanical blocks
// of a text body — blank-line paragraphs, `>` quote runs, the `-- ` signature — as raw spans, since quoted-printable
// and the identity encodings are line-local and a blank line survives them (D-rfc822-parts).
import { parseHtml } from "../html/dom.ts";
import { HTML_TEXT_OP } from "../html/text.ts";
import { opNamed, registerOp } from "../ops.ts";
import { decodeCharset, decodeTransfer, isBodyPart, leaves, type Message, type Part, parseMessage } from "./parse.ts";

export const EML_TEXT_OP = "eml.text@1";

const latin1 = new TextDecoder("latin1");

/** Encodings under which a sub-span of the body decodes on its own. */
export function lineLocal(cte: string): boolean {
  return cte === "7bit" || cte === "8bit" || cte === "binary" || cte === "quoted-printable";
}

/** The text of a raw span [start, end) within text part `p`. */
export function spanText(m: Message, p: Part, start: number, end: number): string {
  const raw = m.bytes.subarray(start, end);
  const decoded = decodeTransfer(raw, p.cte);
  return decodeCharset(decoded, p.charset)
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+$/gm, "")
    .replace(/\n+$/, "");
}

/** The text body part that holds [start, end), or null. */
export function partAt(m: Message, start: number, end: number): Part | null {
  let best: Part | null = null;
  for (const p of leaves(m)) {
    if (!isBodyPart(p)) continue;
    if (p.bodyStart <= start && end <= p.bodyEnd) {
      if (!best || p.bodyEnd - p.bodyStart < best.bodyEnd - best.bodyStart) best = p;
    }
  }
  return best;
}

/** The derivation at `bytes=start,end`: the whole body of a text part, or a sub-span of a line-local one. */
export function textAt(m: Message, start: number, end: number): string | null {
  const p = partAt(m, start, end);
  if (!p) return null;
  const whole = p.bodyStart === start && p.bodyEnd === end;
  if (!whole && !lineLocal(p.cte)) return null;
  return spanText(m, p, start, end);
}

export type BlockKind = "paragraph" | "quote" | "signature";

export interface Block {
  kind: BlockKind;
  start: number;
  end: number;
}

/** A raw line is blank when, after the transfer encoding's line-local view, nothing but whitespace remains. */
function blankLine(line: string, cte: string): boolean {
  const l = cte === "quoted-printable" ? line.replace(/=20/g, " ").replace(/=09/g, "\t") : line;
  return /^[ \t]*$/.test(l);
}

function sigdash(line: string, cte: string): boolean {
  const l = cte === "quoted-printable" ? line.replace(/=20$/, " ") : line;
  return l === "-- ";
}

/** The mechanical blocks of a text body part, as raw spans; empty for an encoding that is not line-local. */
export function blocks(m: Message, p: Part): Block[] {
  if (!isBodyPart(p) || !lineLocal(p.cte)) return [];
  const out: Block[] = [];
  const b = m.bytes;
  let i = p.bodyStart;
  let cur: { start: number; end: number; lines: string[] } | null = null;
  const flush = () => {
    if (!cur?.lines.length) {
      cur = null;
      return;
    }
    const kind: BlockKind = cur.lines.every((l) => l.startsWith(">")) ? "quote" : "paragraph";
    out.push({ kind, start: cur.start, end: cur.end });
    cur = null;
  };
  while (i < p.bodyEnd) {
    let nl = b.indexOf(0x0a, i);
    if (nl === -1 || nl >= p.bodyEnd) nl = p.bodyEnd;
    const lineEnd = nl > i && b[nl - 1] === 0x0d ? nl - 1 : nl;
    const line = latin1.decode(b.subarray(i, lineEnd));
    if (sigdash(line, p.cte)) {
      flush();
      let end = p.bodyEnd;
      while (end > i && (b[end - 1] === 0x0a || b[end - 1] === 0x0d)) end--;
      if (end > lineEnd) out.push({ kind: "signature", start: i, end });
      return out;
    }
    if (blankLine(line, p.cte)) flush();
    else if (cur) {
      cur.end = lineEnd;
      cur.lines.push(line);
    } else cur = { start: i, end: lineEnd, lines: [line] };
    i = nl + 1;
  }
  flush();
  return out;
}

/** A part's decoded bytes (its transfer encoding undone), as its constituent resolves to. */
const partDecoded = (m: Message, p: Part): Uint8Array => decodeTransfer(m.bytes.subarray(p.bodyStart, p.bodyEnd), p.cte);

registerOp<Message>({
  name: EML_TEXT_OP,
  kind: "hint",
  family: "rfc822",
  parse: (bytes) => parseMessage(bytes),
  // a body part's span, in the part's decoded bytes, charset-decoded, CRLF folded to LF, trailing whitespace
  // trimmed; an HTML part as html.text@1 over the part
  hint: async (m, r) => {
    if (r.path === undefined) return null;
    const p = m.parts.find((x) => x.path === r.path);
    if (!p || p.children.length) return null;
    const body = partDecoded(m, p);
    const [a, b] = r.bytes ?? [0, body.length];
    if (b > body.length) return null;
    const at = `path=${r.path}&bytes=${a},${b}`;
    if (p.mime === "text/html") {
      const h = await opNamed(HTML_TEXT_OP)!.hint!(parseHtml(body), { bytes: [a, b] }, undefined);
      return h ? { text: h.text, units: h.units.map((u) => ({ text: u.text, at: `path=${r.path}&${u.at}` })) } : null;
    }
    if (!p.mime.startsWith("text/")) return null;
    const text = decodeCharset(body.subarray(a, b), p.charset)
      .replace(/\r\n/g, "\n")
      .replace(/[ \t]+$/gm, "")
      .replace(/\n+$/, "");
    return { text, units: [{ text, at }] };
  },
});
