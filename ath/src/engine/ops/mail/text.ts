// text.ts — `eml.text@1`, the quote surface of a mail scope (D-rfc822): a raw byte span inside a text body part,
// transfer-decoded and charset-decoded, CRLF folded to LF, trailing whitespace trimmed. Also the mechanical blocks
// of a text body — blank-line paragraphs, `>` quote runs, the `-- ` signature — as raw spans, since quoted-printable
// and the identity encodings are line-local and a blank line survives them (D-rfc822-parts).
import { registerOp } from "../registry.ts";
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

registerOp<Message>({
  name: EML_TEXT_OP,
  family: "mail",
  parse: (bytes) => parseMessage(bytes),
  surface: (m, a) => (a.kind === "bytes" ? textAt(m, a.start, a.end) : null),
});
