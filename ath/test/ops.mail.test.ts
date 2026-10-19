// ops.mail.test.ts — the mail family (D-rfc822, D-rfc822-parts, D-mbox): the parser's spans and decoders, the
// attestation and its members, the mailbox roster, and the derived tree through the CLI — header, body, blocks,
// readings under eml.text@1, the harvested message concept, every entry bound, lint clean.
import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { intrinsicsOf } from "@ath/engine/formats/index.ts";
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
import { spanText, textAt } from "@ath/engine/formats/mail/text.ts";
import { select, selectParse } from "@ath/engine/select/select.ts";
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
    const a = await intrinsicsOf(bytes, "message/rfc822");
    expect(a.value).toMatchObject({
      op: "rfc822.intrinsics@1",
      message_id: "<synthetic-message-0001@athenaeum.example>",
      subject: "Synthetic exemplar message",
      date_iso: "2025-01-01T00:00:00Z",
    });
    expect((a.value.parts as { path: string }[]).map((p) => p.path)).toEqual(["1", "2", "3"]);
    expect(a.constituents.map((x) => [x.path, x.kind, x.fields?.mime ?? x.intrinsics?.mime, x.fields?.filename ?? null])).toEqual([
      ["1", "part", "text/plain", null],
      ["2", "asset", "message/rfc822", null],
      ["3", "asset", "image/png", "pixel.png"],
    ]);
    expect(a.constituents.map((x) => x.name ?? null)).toEqual([null, "2.eml", "pixel.png"]);
    expect(a.constituents[2]!.read().length).toBe(74);
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
    // a quote and a signature are a shape's line rules over the decoded body, not the tooling's kinds
    const sp = selectParse(ms[1]!.bytes, "message/rfc822")!;
    expect(select(sp, { blank: true }).map((n) => n.text)).toEqual(["Café au lait. ", "> Hello.", "-- \r\nB."]);
    expect(select(sp, { lines: "^>" }).map((n) => n.text)).toEqual(["> Hello."]);
    expect(select(sp, { from: "^-- $" }).map((n) => n.text)).toEqual(["-- \r\nB.\r\n\n"]);
    expect(textAt(m2, m2.root.bodyStart, m2.root.bodyEnd)).toContain("> Hello.");
  });
});
