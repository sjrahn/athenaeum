// ops.mail.test.ts — the mail family (D-rfc822, D-rfc822-parts, D-mbox): the parser's spans and decoders, the
// attestation and its members, the mailbox roster, and the derived tree through the CLI — header, body, blocks,
// readings under eml.text@1, the harvested message concept, every entry bound, lint clean.
import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { loadArtifact } from "../src/engine/corpus/derive.ts";
import { ingestFile } from "../src/engine/corpus/ingest.ts";
import { loadChain } from "../src/engine/layer/config.ts";
import { loadOntology } from "../src/engine/ontology/load.ts";
import { attestMessage } from "../src/engine/ops/mail/attest.ts";
import { mboxMembers, unstuff } from "../src/engine/ops/mail/mbox.ts";
import {
  decodeEncodedWords,
  decodeQuotedPrintable,
  isBodyPart,
  isoDate,
  parseAddresses,
  parseContentType,
  parseMessage,
} from "../src/engine/ops/mail/parse.ts";
import { blocks, spanText, textAt } from "../src/engine/ops/mail/text.ts";
import { readJsonl } from "../src/lib/jsonl.ts";
import { ath } from "./harness.ts";
import { foundation, TESTDATA } from "./layers.ts";

const FIX = join(import.meta.dir, "fixtures");
const EML = join(TESTDATA, "synthetic", "synthetic-message.eml");
const env = { ATH_ACTOR: "tester" };
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
    expect(isoDate("Tue, 21 Apr 2026 21:33:28 -0600")).toBe("2026-04-22T03:33:28Z");
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

describe("rfc822 through the CLI", () => {
  test("a mailbox's messages are subjects; a message derives header, body and blocks; harvest binds to the attestation", async () => {
    const f = foundation();
    const chain = loadChain(f);
    const o = loadOntology(chain);
    const ing = await ingestFile(chain, join(FIX, "small.mbox"), { date: "2026-10-13", provenance: { origin: "fixtures", via: "upload" } });
    expect(ing.mime).toBe("application/mbox");
    expect(ing.members.map((m) => m.mime)).toEqual(["message/rfc822", "message/rfc822"]);
    const box = await loadArtifact(chain, o, ing.blake3);
    expect(box.root).toBe("mbox");
    const second = ing.members[1]!;
    expect((second.capturedFrom!.value as { path: string }).path).toBe("2");
    const a = await loadArtifact(chain, o, second.blake3);
    expect(a.root).toBe("rfc822");
    expect(a.tree).toBe("derived");
    const walk = a.table.walk().map((s) => `${s.terms.join("+")}@${s.at}`);
    expect(walk[0]).toBe("rfc822@whole");
    expect(walk[1]).toMatch(/^message-header@bytes=0,\d+$/);
    expect(walk[2]).toMatch(/^message-body@bytes=/);
    expect(walk.slice(3).map((w) => w.split("@")[0])).toEqual(["paragraph", "quote", "signature"]);
    const body = a.table.find("message-body")!;
    expect(body.fields).toEqual({ part: "1", encoding: "quoted-printable", charset: "utf-8" });
    expect(body.readings[0]).toMatchObject({ aspect: "text", body: "Café au lait.\n\n> Hello.\n\n--\nB.", rev: "derived:eml.text@1" });
    expect(a.attests.value).toMatchObject({ subject: "Second — réponse", from: "b@example", date_iso: "2025-01-02T00:00:00Z" });
    // harvest: one message concept keyed by Message-ID, claims bound line:attests <field>
    const h = await ath(["--json", "harvest", second.blake3], { cwd: f, env });
    expect(h.code, h.stderr).toBe(0);
    expect((h.json() as { data: { concepts: number; claims: number } }).data).toMatchObject({ concepts: 1, claims: 4 });
    const slug = "email-message-two-example";
    const lines = readJsonl(join(f, "ledger", `${slug}.claims.jsonl`));
    const subj = lines.find((l) => l.predicate === "subject")!;
    expect(subj.value).toBe("Second — réponse");
    expect((subj.evidence as { reading: string; kind: string }[])[0]).toMatchObject({
      reading: "line:attests subject",
      kind: "authoritative",
    });
    const v = await ath(["--json", "verify", slug], { cwd: f, env });
    expect(v.code).toBe(0);
    const vd = (v.json() as { data: { counts: { bound: number; entries: number; flagged: number } } }).data;
    expect(vd.counts.flagged).toBe(0);
    expect(vd.counts.bound).toBe(vd.counts.entries);
    // a claim cited through the mailbox route binds on the member's own block
    const q = a.table.find("quote")!;
    const { writeFileSync } = await import("node:fs");
    writeFileSync(
      join(f, "ledger", "t.claims.jsonl"),
      [
        '{"subject":"t","predicate":"term","value":"concept"}',
        `{"subject":"t","predicate":"quoted","value":"Hello.","evidence":[{"anchor":"corpus://${ing.blake3}?path=2;${q.at}&text","quote":"> Hello.","kind":"direct","mode":"stated","reading":"derived:eml.text@1"}],"by":"ath.test@1"}`,
      ]
        .map((l) => `${l}\n`)
        .join(""),
    );
    const vt = await ath(["--json", "verify", "t"], { cwd: f, env });
    const claims = (vt.json() as { data: { claims: { bindings: { state: string; at: string }[] }[] } }).data.claims;
    expect(claims[0]!.bindings[0]).toMatchObject({ state: "bound", at: q.at });
    expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
    expect((await ath(["export", "markdown", second.blake3], { cwd: f, env })).stdout).toContain("Café au lait.");
  });

  test("the synthetic message with attachments: the nested message is a subject that classifies on its own", async () => {
    const f = foundation();
    const r = await ath(["--json", "ingest", EML, "--origin", "synthetic", "--via", "upload", "--received", "2026-10-13"], { cwd: f, env });
    expect(r.code, r.stderr).toBe(0);
    const rows = (r.json() as { data: { ingested: { blake3: string; mime: string; members: number }[] } }).data.ingested;
    expect(rows.map((x) => x.mime)).toEqual(["message/rfc822", "message/rfc822", "image/png"]);
    expect(rows[0]!.members).toBe(2);
    const tree = await ath(["--json", "tree", rows[1]!.blake3], { cwd: f, env });
    const td = (tree.json() as { data: { root: string; scopes: { terms: string[] }[] } }).data;
    expect(td.root).toBe("rfc822");
    expect(td.scopes.map((s) => s.terms.join("+"))).toEqual(["rfc822", "message-header", "message-body"]); // one block equal to the body is the body
    const png = await ath(["--json", "tree", rows[2]!.blake3], { cwd: f, env });
    expect((png.json() as { data: { root: string } }).data.root).toBe("png");
    expect((await ath(["lint", "--all"], { cwd: f, env })).code).toBe(0);
  });
});
