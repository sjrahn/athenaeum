// vcard.ts — vCard as RFC 6350 defines it: cards between BEGIN:VCARD and END:VCARD, content lines unfolded (§3.2),
// each `[group.]NAME[;param=value]*:value`, with its byte span covering its folded physical lines. `vcard.text@1` is
// the surface: the content lines in a span, each value unescaped, a structured value's components joined by a space.
import { registerOp } from "../ops.ts";

export interface ContentLine {
  group?: string;
  name: string;
  params: Record<string, string>;
  /** The value as written, unfolded and still escaped. */
  raw: string;
  start: number;
  end: number;
}

export interface Card {
  start: number;
  end: number;
  lines: ContentLine[];
}

export interface VcardDoc {
  cards: Card[];
  lines: ContentLine[];
}

export const VCARD_TEXT_OP = "vcard.text@1";

/** Split at unescaped `sep`. */
const splitEsc = (v: string, sep: string): string[] => {
  const out: string[] = [];
  let cur = "";
  for (let i = 0; i < v.length; i++) {
    if (v[i] === "\\" && i + 1 < v.length) {
      cur += v[i]! + v[i + 1]!;
      i++;
    } else if (v[i] === sep) {
      out.push(cur);
      cur = "";
    } else cur += v[i];
  }
  out.push(cur);
  return out;
};
const unescapeValue = (v: string) => v.replace(/\\([nN,;\\])/g, (_, c: string) => (c === "n" || c === "N" ? "\n" : c));

/** A content line's value as the surface gives it: unescaped, components joined by a space. */
export const valueText = (l: ContentLine): string =>
  splitEsc(l.raw, ";")
    .map((c) => splitEsc(c, ",").map(unescapeValue).join(","))
    .filter((c) => c !== "")
    .join(" ");

export function parseVcard(bytes: Uint8Array): VcardDoc {
  const b = bytes;
  const utf8 = new TextDecoder("utf-8");
  const lines: ContentLine[] = [];
  let i = 0;
  while (i < b.length) {
    const start = i;
    // a content line runs to a line break not followed by a space or tab (folding)
    let end = i;
    const parts: Uint8Array[] = [];
    let seg = i;
    for (;;) {
      let nl = b.indexOf(0x0a, end);
      if (nl === -1) nl = b.length;
      const lineEnd = nl > end && b[nl - 1] === 0x0d ? nl - 1 : nl;
      parts.push(b.subarray(seg, lineEnd));
      end = Math.min(nl + 1, b.length);
      if (end < b.length && (b[end] === 0x20 || b[end] === 0x09)) {
        seg = end + 1;
        continue;
      }
      break;
    }
    i = end;
    const text = utf8.decode(Buffer.concat(parts));
    if (!text.trim()) continue;
    const colon = (() => {
      let q = false;
      for (let k = 0; k < text.length; k++) {
        if (text[k] === '"') q = !q;
        else if (text[k] === ":" && !q) return k;
      }
      return -1;
    })();
    if (colon < 0) continue;
    const [head, ...ps] = text.slice(0, colon).split(";");
    const dot = head!.indexOf(".");
    const params: Record<string, string> = {};
    for (const p of ps) {
      const eq = p.indexOf("=");
      params[(eq < 0 ? p : p.slice(0, eq)).toUpperCase()] = eq < 0 ? "" : p.slice(eq + 1);
    }
    // the span ends at the last byte of the content line's last physical line, its line break excluded
    let spanEnd = end;
    while (spanEnd > start && (b[spanEnd - 1] === 0x0a || b[spanEnd - 1] === 0x0d)) spanEnd--;
    lines.push({
      ...(dot > 0 ? { group: head!.slice(0, dot) } : {}),
      name: (dot > 0 ? head!.slice(dot + 1) : head!).toUpperCase(),
      params,
      raw: text.slice(colon + 1),
      start,
      end: spanEnd,
    });
  }
  const cards: Card[] = [];
  let open: { start: number; lines: ContentLine[] } | null = null;
  for (const l of lines) {
    if (l.name === "BEGIN" && l.raw.toUpperCase() === "VCARD") open = { start: l.start, lines: [] };
    else if (l.name === "END" && l.raw.toUpperCase() === "VCARD" && open) {
      cards.push({ start: open.start, end: l.end, lines: open.lines });
      open = null;
    } else open?.lines.push(l);
  }
  return { cards, lines };
}

registerOp<VcardDoc>({
  name: VCARD_TEXT_OP,
  kind: "surface",
  family: "vcard",
  parse: parseVcard,
  surface: (d, r) => {
    if (r.path !== undefined) return null;
    const [a, b] = r.whole ? [0, Number.MAX_SAFE_INTEGER] : (r.bytes ?? [-1, -1]);
    if (a < 0) return null;
    return d.lines
      .filter((l) => l.start >= a && l.end <= b && l.name !== "BEGIN" && l.name !== "END")
      .map(valueText)
      .join("\n");
  },
});
