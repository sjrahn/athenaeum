// parse.ts — an RFC 5322 / RFC 2045 parser of the engine's own with byte spans (D-rfc822): the header block, the
// MIME part tree (depth-first, IMAP-style paths `1`, `1.2`, `3`), every part's raw body span in the file, and the
// decoders the format itself specifies (RFC 2047 encoded words, quoted-printable, base64, charsets). Nothing here
// reads a layer; a part's raw span is the intrinsic coordinate (`bytes=a,b`), its decoded text the derivation.

export interface Header {
  name: string;
  /** The unfolded, RFC 2047-decoded value. */
  value: string;
  /** The raw (folded) field as the bytes hold it. */
  raw: string;
  start: number;
  end: number;
}

export interface Part {
  /** IMAP-style path: `1`, `1.2`, `3`; the root message is `` (empty). */
  path: string;
  mime: string;
  params: Record<string, string>;
  charset: string | null;
  /** Content-Transfer-Encoding, lower-cased; `7bit` when absent. */
  cte: string;
  disposition: string | null;
  filename: string | null;
  headers: Header[];
  /** The part's header block (from its first header byte to the blank line, exclusive). */
  headerStart: number;
  headerEnd: number;
  /** The raw body span in the file, half-open; for a multipart the span holds the sub-parts. */
  bodyStart: number;
  bodyEnd: number;
  boundary: string | null;
  children: Part[];
}

export interface Message {
  bytes: Uint8Array;
  root: Part;
  /** The parts depth-first, root excluded. */
  parts: Part[];
}

const latin1 = new TextDecoder("latin1");
const utf8Strict = new TextDecoder("utf-8", { fatal: true });

/** A raw header line: UTF-8 when it is valid UTF-8 (RFC 6532), latin1 otherwise. */
function headerLine(b: Uint8Array): string {
  try {
    return utf8Strict.decode(b);
  } catch {
    return latin1.decode(b);
  }
}

function indexOfSeq(b: Uint8Array, seq: number[], from: number, to = b.length): number {
  outer: for (let i = from; i <= to - seq.length; i++) {
    for (let k = 0; k < seq.length; k++) if (b[i + k] !== seq[k]) continue outer;
    return i;
  }
  return -1;
}

/** The end of the header block starting at `start`: the offset of the blank line's terminator; returns
 * [headerEnd, bodyStart]. A block with no blank line ends at `to` with an empty body. */
function splitHeaders(b: Uint8Array, start: number, to: number): [number, number] {
  let i = start;
  // an empty header block
  if (b[i] === 0x0a) return [i, i + 1];
  if (b[i] === 0x0d && b[i + 1] === 0x0a) return [i, i + 2];
  while (i < to) {
    const nl = b.indexOf(0x0a, i);
    if (nl === -1 || nl >= to) return [to, to];
    const lineEnd = nl > i && b[nl - 1] === 0x0d ? nl - 1 : nl;
    if (lineEnd === i) return [i, nl + 1]; // the blank line
    i = nl + 1;
  }
  return [to, to];
}

const CHARSET_ALIASES: Record<string, string> = {
  "utf-8": "utf-8",
  utf8: "utf-8",
  "us-ascii": "utf-8",
  ascii: "utf-8",
  "iso-8859-1": "windows-1252",
  latin1: "windows-1252",
  "windows-1252": "windows-1252",
  cp1252: "windows-1252",
  "iso-8859-15": "iso-8859-15",
  "iso-8859-2": "iso-8859-2",
  "windows-1251": "windows-1251",
  shift_jis: "shift_jis",
  "euc-jp": "euc-jp",
  gb2312: "gb2312",
  gbk: "gbk",
  big5: "big5",
  "utf-16": "utf-16le",
  "utf-16le": "utf-16le",
  "utf-16be": "utf-16be",
};

export function decodeCharset(bytes: Uint8Array, charset: string | null): string {
  const label = CHARSET_ALIASES[(charset ?? "utf-8").toLowerCase()] ?? "utf-8";
  try {
    return new TextDecoder(label as ConstructorParameters<typeof TextDecoder>[0], { ignoreBOM: false }).decode(bytes);
  } catch {
    return new TextDecoder("utf-8").decode(bytes);
  }
}

/** Quoted-printable (RFC 2045 §6.7): `=XX`, soft line breaks `=\r?\n`, trailing whitespace before a break dropped. */
export function decodeQuotedPrintable(b: Uint8Array): Uint8Array {
  const out = new Uint8Array(b.length);
  let o = 0;
  for (let i = 0; i < b.length; i++) {
    const c = b[i]!;
    if (c === 0x3d) {
      // '='
      const n1 = b[i + 1];
      const n2 = b[i + 2];
      if (n1 === 0x0a) {
        i += 1;
        continue;
      }
      if (n1 === 0x0d && n2 === 0x0a) {
        i += 2;
        continue;
      }
      if (n1 !== undefined && n2 !== undefined && isHex(n1) && isHex(n2)) {
        out[o++] = (hexVal(n1) << 4) | hexVal(n2);
        i += 2;
        continue;
      }
      out[o++] = c;
      continue;
    }
    if (c === 0x20 || c === 0x09) {
      // trailing whitespace before a line break is transport padding
      let j = i;
      while (j < b.length && (b[j] === 0x20 || b[j] === 0x09)) j++;
      if (j >= b.length || b[j] === 0x0a || (b[j] === 0x0d && b[j + 1] === 0x0a)) {
        i = j - 1;
        continue;
      }
    }
    out[o++] = c;
  }
  return out.subarray(0, o);
}

const isHex = (c: number) => (c >= 0x30 && c <= 0x39) || (c >= 0x41 && c <= 0x46) || (c >= 0x61 && c <= 0x66);
const hexVal = (c: number) => (c <= 0x39 ? c - 0x30 : c <= 0x46 ? c - 0x41 + 10 : c - 0x61 + 10);

export function decodeBase64(b: Uint8Array): Uint8Array {
  const s = latin1.decode(b).replace(/[^A-Za-z0-9+/=]/g, "");
  return Uint8Array.from(Buffer.from(s, "base64"));
}

/** The body bytes of a part after its transfer encoding (identity for 7bit/8bit/binary). */
export function decodeTransfer(raw: Uint8Array, cte: string): Uint8Array {
  switch (cte) {
    case "base64":
      return decodeBase64(raw);
    case "quoted-printable":
      return decodeQuotedPrintable(raw);
    default:
      return raw;
  }
}

/** RFC 2047 encoded words in a header value: `=?charset?B|Q?text?=`; adjacent words join without the space. */
export function decodeEncodedWords(s: string): string {
  return s.replace(/=\?([^?]+)\?([BbQq])\?([^?]*)\?=(\s+(?==\?))?/g, (_m, cs: string, enc: string, text: string) => {
    const raw =
      enc.toUpperCase() === "B"
        ? decodeBase64(new TextEncoder().encode(text))
        : decodeQuotedPrintable(new TextEncoder().encode(text.replace(/_/g, " ")));
    return decodeCharset(raw, cs.replace(/\*.*$/, ""));
  });
}

/** Parse a header block [start, end): unfolded values, RFC 2047 decoded. */
export function parseHeaders(b: Uint8Array, start: number, end: number): Header[] {
  const out: Header[] = [];
  let i = start;
  let cur: { name: string; raw: string; start: number; end: number } | null = null;
  const flush = () => {
    if (!cur) return;
    const unfolded = cur.raw
      .replace(/^[^:]*:\s*/, "")
      .replace(/\r?\n[ \t]+/g, " ")
      .trim();
    out.push({ name: cur.name, value: decodeEncodedWords(unfolded), raw: cur.raw, start: cur.start, end: cur.end });
    cur = null;
  };
  while (i < end) {
    let nl = b.indexOf(0x0a, i);
    if (nl === -1 || nl >= end) nl = end;
    const lineEnd = nl > i && b[nl - 1] === 0x0d ? nl - 1 : nl;
    const line = headerLine(b.subarray(i, lineEnd));
    if ((line.startsWith(" ") || line.startsWith("\t")) && cur) {
      cur.raw += `\n${line}`;
      cur.end = lineEnd;
    } else {
      flush();
      const colon = line.indexOf(":");
      if (colon > 0) cur = { name: line.slice(0, colon).trim(), raw: line, start: i, end: lineEnd };
    }
    i = nl + 1;
  }
  flush();
  return out;
}

export function header(headers: Header[], name: string): string | null {
  const n = name.toLowerCase();
  return headers.find((h) => h.name.toLowerCase() === n)?.value ?? null;
}

export function headerAll(headers: Header[], name: string): string[] {
  const n = name.toLowerCase();
  return headers.filter((h) => h.name.toLowerCase() === n).map((h) => h.value);
}

/** `type/subtype; a=b; c="d"` → the lower-cased type and its parameters (RFC 2231 continuations joined). */
export function parseContentType(v: string | null): { mime: string; params: Record<string, string> } {
  if (!v) return { mime: "text/plain", params: {} };
  const [head, ...rest] = v.split(";");
  const mime = (head ?? "").trim().toLowerCase() || "text/plain";
  const params: Record<string, string> = {};
  const cont = new Map<string, string[]>();
  for (const p of rest) {
    const eq = p.indexOf("=");
    if (eq === -1) continue;
    let name = p.slice(0, eq).trim().toLowerCase();
    let val = p.slice(eq + 1).trim();
    if (val.startsWith('"') && val.endsWith('"')) val = val.slice(1, -1).replace(/\\(.)/g, "$1");
    const star = /^(.+?)\*(\d+)?\*?$/.exec(name);
    if (star) {
      name = star[1]!;
      if (name && val.includes("'")) val = decodeURIComponent(val.split("'").slice(2).join("'"));
      const parts = cont.get(name) ?? [];
      parts[Number(star[2] ?? 0)] = val;
      cont.set(name, parts);
      continue;
    }
    params[name] = decodeEncodedWords(val);
  }
  for (const [k, v2] of cont) params[k] = decodeEncodedWords(v2.join(""));
  return { mime, params };
}

function buildPart(b: Uint8Array, path: string, start: number, end: number): Part {
  const [headerEnd, bodyStart] = splitHeaders(b, start, end);
  const headers = parseHeaders(b, start, headerEnd);
  const ct = parseContentType(header(headers, "Content-Type"));
  const disp = parseContentType(header(headers, "Content-Disposition"));
  const filename = disp.params.filename ?? ct.params.name ?? null;
  const part: Part = {
    path,
    mime: ct.mime,
    params: ct.params,
    charset: ct.params.charset ?? null,
    cte: (header(headers, "Content-Transfer-Encoding") ?? "7bit").trim().toLowerCase(),
    disposition: header(headers, "Content-Disposition") ? disp.mime : null,
    filename,
    headers,
    headerStart: start,
    headerEnd,
    bodyStart,
    bodyEnd: end,
    boundary: ct.mime.startsWith("multipart/") ? (ct.params.boundary ?? null) : null,
    children: [],
  };
  if (part.boundary) part.children = splitMultipart(b, part, path);
  return part;
}

/** The sub-parts between `--boundary` lines (RFC 2046 §5.1.1): a part runs from the byte after the boundary line's
 * terminator to the byte before the CRLF that precedes the next boundary. */
function splitMultipart(b: Uint8Array, parent: Part, parentPath: string): Part[] {
  const marker = new TextEncoder().encode(`--${parent.boundary}`);
  const lines: { at: number; lineEnd: number; closing: boolean }[] = [];
  let i = parent.bodyStart;
  while (i < parent.bodyEnd) {
    const at = indexOfSeq(b, [...marker], i, parent.bodyEnd);
    if (at === -1) break;
    const atLineStart = at === parent.bodyStart || b[at - 1] === 0x0a;
    let nl = b.indexOf(0x0a, at);
    if (nl === -1 || nl > parent.bodyEnd) nl = parent.bodyEnd;
    if (atLineStart) {
      const tail = latin1.decode(b.subarray(at + marker.length, nl)).replace(/\r$/, "");
      if (tail === "" || tail === "--" || /^[ \t]*$/.test(tail) || /^--[ \t]*$/.test(tail))
        lines.push({ at, lineEnd: nl === parent.bodyEnd ? nl : nl + 1, closing: tail.startsWith("--") });
    }
    i = nl + 1;
  }
  const out: Part[] = [];
  for (let k = 0; k < lines.length; k++) {
    const l = lines[k]!;
    if (l.closing) break;
    const next = lines[k + 1];
    const start = l.lineEnd;
    let end = next ? next.at : parent.bodyEnd;
    // the CRLF (or LF) before the next boundary belongs to the boundary
    if (next) {
      if (end > start && b[end - 1] === 0x0a) end--;
      if (end > start && b[end - 1] === 0x0d) end--;
    }
    out.push(buildPart(b, parentPath ? `${parentPath}.${k + 1}` : String(k + 1), start, end));
  }
  return out;
}

export function parseMessage(bytes: Uint8Array): Message {
  const root = buildPart(bytes, "", 0, bytes.length);
  const parts: Part[] = [];
  const walk = (p: Part) => {
    for (const c of p.children) {
      parts.push(c);
      walk(c);
    }
  };
  walk(root);
  return { bytes, root, parts };
}

/** The leaf parts (no children), depth-first; the root itself when the message is not multipart. */
export function leaves(m: Message): Part[] {
  const out: Part[] = [];
  const walk = (p: Part) => {
    if (!p.children.length) out.push(p);
    for (const c of p.children) walk(c);
  };
  walk(m.root);
  return out;
}

/** The decoded body bytes of a part (transfer encoding undone). */
export function partBytes(m: Message, p: Part): Uint8Array {
  return decodeTransfer(m.bytes.subarray(p.bodyStart, p.bodyEnd), p.cte);
}

/** A part is a body (read in place) when it is text/plain and not an attachment; anything else is a member. */
export function isBodyPart(p: Part): boolean {
  return p.mime === "text/plain" && p.disposition !== "attachment";
}

/** An RFC 5322 date as ISO 8601 UTC, or null when it does not parse. */
export function isoDate(v: string | null): string | null {
  if (!v) return null;
  const cleaned = v.replace(/\s*\([^)]*\)\s*$/, "").trim();
  const t = Date.parse(cleaned);
  if (Number.isNaN(t)) return null;
  return new Date(t).toISOString().replace(/\.\d{3}Z$/, "Z");
}

/** Addresses from a From/To/Cc value: `Name <addr>`, `addr`, comma-separated, quotes stripped. */
export function parseAddresses(v: string | null): { name: string | null; address: string }[] {
  if (!v) return [];
  const out: { name: string | null; address: string }[] = [];
  const re = /(?:"([^"]*)"|([^<,]+?))?\s*<([^>]+)>|([^\s,<>]+@[^\s,<>]+)/g;
  let m: RegExpExecArray | null = re.exec(v);
  while (m !== null) {
    if (m[3]) out.push({ name: (m[1] ?? m[2] ?? "").trim() || null, address: m[3].trim() });
    else if (m[4]) out.push({ name: null, address: m[4] });
    m = re.exec(v);
  }
  return out;
}
