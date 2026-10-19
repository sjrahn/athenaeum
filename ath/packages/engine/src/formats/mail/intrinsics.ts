// intrinsics.ts — what a message and a mailbox define about themselves (spec §10.2, §10.3). A message: the RFC 5322
// fields that identify it (header fields read as UTF-8 where valid, else ISO-8859-1, encoded words decoded), the
// MIME part table with every part's raw byte span, and its constituents — every leaf part with a filename or an
// attachment disposition, and every nested message, decoded from its transfer encoding, as assets; the body parts and
// their multipart wrappers as parts. A mailbox: its message count, and every message, un-stuffed, as an asset at its
// 1-based ordinal.
import { blake3Hex } from "@ath/kit/hash.ts";
import type { Constituent, IntrinsicsResult, J } from "../format.ts";
import { mboxMembers } from "./mbox.ts";
import { decodeTransfer, header, isoDate, type Part, parseMessage } from "./parse.ts";

const isAsset = (p: Part) => p.mime === "message/rfc822" || !!p.filename || p.disposition === "attachment";

export async function messageIntrinsics(bytes: Uint8Array): Promise<IntrinsicsResult> {
  const m = parseMessage(bytes);
  const h = m.root.headers;
  const facts: J = {};
  for (const [k, name] of [
    ["message_id", "Message-ID"],
    ["subject", "Subject"],
    ["from", "From"],
    ["to", "To"],
    ["cc", "Cc"],
    ["date", "Date"],
  ] as const) {
    const v = header(h, name);
    if (v) facts[k] = v;
  }
  const iso = isoDate(header(h, "Date"));
  if (iso) facts.date_iso = iso;
  if (m.parts.length)
    facts.parts = m.parts.map((p) => {
      const row: J = { path: p.path, mime: p.mime, transfer_encoding: p.cte };
      if (p.charset) row.charset = p.charset;
      if (p.filename) row.filename = p.filename;
      if (p.disposition) row.disposition = p.disposition;
      row.span = [p.bodyStart, p.bodyEnd];
      return row;
    });
  const constituents: Constituent[] = [];
  for (const p of m.parts) {
    const multipart = p.children.length > 0;
    const read = () => (multipart ? bytes.subarray(p.bodyStart, p.bodyEnd) : decodeTransfer(bytes.subarray(p.bodyStart, p.bodyEnd), p.cte));
    const data = read();
    const c: Constituent = { path: p.path, blake3: await blake3Hex(data), kind: !multipart && isAsset(p) ? "asset" : "part", read };
    if (c.kind === "asset") {
      c.fields = {
        mime: p.mime,
        ...(p.filename ? { filename: p.filename } : {}),
        ...(p.disposition ? { disposition: p.disposition } : {}),
      };
      c.name = p.filename ?? (p.mime === "message/rfc822" ? `${p.path}.eml` : undefined);
    } else c.intrinsics = { mime: p.mime, bytes: data.length };
    constituents.push(c);
  }
  return { facts, constituents };
}

export async function mboxIntrinsics(bytes: Uint8Array): Promise<IntrinsicsResult> {
  const members = await mboxMembers(bytes);
  return {
    facts: { messages: members.length },
    constituents: members.map((x) => ({
      path: x.path,
      blake3: x.blake3,
      kind: "asset",
      ...(x.message_id ? { fields: { message_id: x.message_id } } : {}),
      read: () => x.bytes,
      name: `${x.path}.eml`,
    })),
  };
}
