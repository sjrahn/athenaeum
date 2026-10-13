// attest.ts — what a message is (D-rfc822): the RFC 5322 headers that identify it, the MIME part table with every
// part's raw span, and the members — every leaf that is not a text/plain body (the HTML alternative, attachments,
// a nested message) — as subjects of their own, routed `path=<part path>`; the filename rides on the roster row.
import { blake3Hex } from "../../../lib/hash.ts";
import { type AttestResult, registerAttester } from "../registry.ts";
import { header, headerAll, isBodyPart, isoDate, leaves, type Message, type Part, parseMessage, partBytes } from "./parse.ts";

export interface PartRow {
  path: string;
  mime: string;
  cte: string;
  charset?: string;
  filename?: string;
  disposition?: string;
  bytes: [number, number];
}

export function partRows(m: Message): PartRow[] {
  return m.parts.map((p) => {
    const row: PartRow = { path: p.path, mime: p.mime, cte: p.cte, bytes: [p.bodyStart, p.bodyEnd] };
    if (p.charset) row.charset = p.charset;
    if (p.filename) row.filename = p.filename;
    if (p.disposition) row.disposition = p.disposition;
    return row;
  });
}

/** The leaves that become subjects of their own. */
export function memberParts(m: Message): Part[] {
  return leaves(m).filter((p) => p !== m.root && !isBodyPart(p));
}

export function messageFacts(m: Message): Record<string, unknown> {
  const h = m.root.headers;
  const v: Record<string, unknown> = {};
  const put = (k: string, name: string) => {
    const x = header(h, name);
    if (x) v[k] = x;
  };
  put("message_id", "Message-ID");
  put("subject", "Subject");
  put("from", "From");
  put("to", "To");
  put("cc", "Cc");
  put("date", "Date");
  put("in_reply_to", "In-Reply-To");
  const iso = isoDate(header(h, "Date"));
  if (iso) v.date_iso = iso;
  const refs = headerAll(h, "References");
  if (refs.length) v.references = refs.join(" ").split(/\s+/).filter(Boolean);
  return v;
}

export async function attestMessage(bytes: Uint8Array, mime: string): Promise<AttestResult> {
  const m = parseMessage(bytes);
  const value: Record<string, unknown> = { mime, bytes: bytes.length, ...messageFacts(m) };
  value.header_bytes = [0, m.root.headerEnd];
  value.content_type = m.root.mime;
  if (m.parts.length) value.parts = partRows(m);
  const members: NonNullable<AttestResult["members"]> = [];
  for (const p of memberParts(m)) {
    const data = p.mime === "message/rfc822" ? bytes.subarray(p.bodyStart, p.bodyEnd) : partBytes(m, p);
    const name = p.filename ?? (p.mime === "message/rfc822" ? `${p.path}.eml` : p.mime === "text/html" ? `${p.path}.html` : p.path);
    members.push({ path: p.path, bytes: data, blake3: await blake3Hex(data), name });
  }
  if (members.length) {
    value.members = members.map((x) => {
      const p = m.parts.find((q) => q.path === x.path)!;
      const row: Record<string, unknown> = { path: x.path, mime: p.mime, bytes: x.bytes.length, blake3: x.blake3 };
      if (p.filename) row.filename = p.filename;
      return row;
    });
  }
  return members.length ? { value, members } : { value };
}

registerAttester("message/rfc822", attestMessage);
