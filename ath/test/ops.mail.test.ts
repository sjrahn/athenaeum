// ops.mail.test.ts — the mail family (D-rfc822, D-rfc822-parts, D-mbox): the parser's spans and decoders, the
// attestation and its members, the mailbox roster, and the derived tree through the CLI — header, body, blocks,
// readings under eml.text@1, the harvested message concept, every entry bound, lint clean.
import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { attestMessage } from "@ath/engine/formats/mail/attest.ts";
import { mboxMembers, unstuff } from "@ath/engine/formats/mail/mbox.ts";
import {
  decodeEncodedWords,
  decodeQuotedPrintable,
  isBodyPart,
  isoDate,
  parseAddresses,
  parseContentType,
  parseMessage,
} from "@ath/engine/formats/mail/parse.ts";
import { blocks, spanText, textAt } from "@ath/engine/formats/mail/text.ts";
import { TESTDATA } from "./harness.ts";

const FIX = join(import.meta.dir, "fixtures");
const EML = join(TESTDATA, "synthetic", "synthetic-message.eml");
const read = async (p: string) => new Uint8Array(await Bun.file(p).arrayBuffer());
const utf8 = new TextDecoder();

describe("rfc822 parse", () => {
  test("decoders the format specifies", () => {
    expect(utf8.decode(decodeQuotedPrintable(new TextEncoder().encode("Caf=C3=A9 au=\r\n lait.=20\r\nx")))).toBe("Café au lait. \r\nx");
    expect(decodeEncodedWords("=?utf-8?q?Second_=E2=80=94_r=C3=A9ponse?=")).toBe("Second — réponse");
    expect(decodeEncodedWords("=?UTF-8?B?w6l0w6k=?= =?UTF-8?B?IGZpbg==?=")).toBe("été fin");
    expect(parseContentType('multipart/mixed; boundary="abc"; charset=UTF-8')).toEqual({
      mime: "multipart/mixed",
      params: { boundary: "abc", charset: "UTF-8" },
    });
    expect(isoDate("Sat, 18 Apr 2026 19:12:05 -0600")).toBe("2026-04-19T01:12:05Z");
    expect(parseAddresses('"Ada Example" <ada@example>, bo@example')).toEqual([
      { name: "Ada Example", address: "ada@example" },
      { name: null, address: "bo@example" },
    ]);
  });

  test("the synthetic message: parts with raw spans; a body in place, a nested message and a PNG as members", async () => {
    const bytes = await read(EML);
    const m = parseMessage(bytes);
    expect(m.root.mime).toBe("multipart/mixed");
    expect(m.parts.map((p) => [p.path, p.mime, isBodyPart(p)])).toEqual([
      ["1", "text/plain", true],
      ["2", "message/rfc822", false],
      ["3", "image/png", false],
    ]);
    const nested = m.parts[1]!;
    expect(utf8.decode(bytes.subarray(nested.bodyStart, nested.bodyStart + 40))).toBe("Message-ID: <synthetic-nested-0001@athen");
    const body = m.parts[0]!;
    expect(spanText(m, body, body.bodyStart, body.bodyEnd).startsWith("This is the reply-text body")).toBe(true);
    expect(blocks(m, body).map((b) => b.kind)).toEqual(["paragraph"]);
    const a = await attestMessage(bytes, "message/rfc822");
    expect(a.value).toMatchObject({
      message_id: "<synthetic-message-0001@athenaeum.example>",
      subject: "Synthetic exemplar message",
      date_iso: "2025-01-01T00:00:00Z",
      content_type: "multipart/mixed",
    });
    expect(
      (a.value.members as { path: string; mime: string; filename?: string }[]).map((x) => [x.path, x.mime, x.filename ?? null]),
    ).toEqual([
      ["2", "message/rfc822", null],
      ["3", "image/png", "pixel.png"],
    ]);
    expect(a.members!.map((x) => x.name)).toEqual(["2.eml", "pixel.png"]);
    expect(a.members![1]!.bytes.length).toBe(74);
  });

  test("the mailbox roster: separators, un-stuffing, members hashed over un-stuffed bytes", async () => {
    const bytes = await read(join(FIX, "small.mbox"));
    const ms = await mboxMembers(bytes);
    expect(ms.map((m) => [m.path, m.message_id])).toEqual([
      ["1", "<one@example>"],
      ["2", "<two@example>"],
    ]);
    expect(utf8.decode(ms[0]!.bytes)).toContain("\r\nFrom here it looks fine.\r\n");
    expect(utf8.decode(unstuff(new TextEncoder().encode(">>From x\n>From y\nFrom z\n")))).toBe(">From x\nFrom y\nFrom z\n");
    const m2 = parseMessage(ms[1]!.bytes);
    expect(blocks(m2, m2.root).map((b) => b.kind)).toEqual(["paragraph", "quote", "signature"]);
    const [p, q, s] = blocks(m2, m2.root);
    expect(textAt(m2, p!.start, p!.end)).toBe("Café au lait.");
    expect(textAt(m2, q!.start, q!.end)).toBe("> Hello.");
    expect(textAt(m2, s!.start, s!.end)).toBe("--\nB.");
  });
});
