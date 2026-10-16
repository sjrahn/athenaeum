#!/usr/bin/env bun
// chat-archive.ts — the twin of the mailbox slice: an mboxrd archive of 358 messages in the shape of a chat export
// folded into mail (every message multipart/alternative with a text/xml and a text/html part; two carry a text/plain
// body instead), `From ` separators, `>From` stuffing in two bodies, Gmail-style thread headers. Fictional chat.
//
//   bun testdata/synthetic/gen/chat-archive.ts
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { FIRST, LAST, int, lcg, pick, sentence } from "./lib/rand.ts";

const OUT = join(dirname(Bun.fileURLToPath(import.meta.url)), "..", "quay-chat.mbox");
const r = lcg(358);
const people = Array.from({ length: 6 }, () => `${pick(r, FIRST)} ${pick(r, LAST)}`);
const addr = (p: string) => `${p.toLowerCase().replace(" ", ".")}@example.invalid`;
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const rfc = (d: Date) =>
  `${DOW[d.getUTCDay()]}, ${d.getUTCDate()} ${MON[d.getUTCMonth()]} ${d.getUTCFullYear()} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}:${String(d.getUTCSeconds()).padStart(2, "0")} +0000`;
const asctime = (d: Date) =>
  `${DOW[d.getUTCDay()]} ${MON[d.getUTCMonth()]} ${String(d.getUTCDate()).padStart(2, " ")} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}:${String(d.getUTCSeconds()).padStart(2, "0")} ${d.getUTCFullYear()}`;
const stuff = (s: string) => s.replace(/^(>*From )/gm, ">$1");

const msgs: string[] = [];
let t = Date.UTC(2021, 2, 1, 9, 0, 0);
for (let i = 0; i < 358; i++) {
  t += int(r, 60, 7200) * 1000;
  const d = new Date(t);
  const who = pick(r, people);
  const thread = 1441149683901270000 + Math.floor(i / 12);
  const line = sentence(r);
  const plain = i === 100 || i === 250;
  const b = `----=_Part_${String(i).padStart(4, "0")}_0000000000.${Math.floor(t / 1000)}`;
  const body = plain
    ? [
        `--${b}`,
        "Content-Type: text/plain; charset=UTF-8; format=flowed",
        "Content-Transfer-Encoding: 7bit",
        "",
        stuff(`${line}\nFrom the quay it looked fine.\n\n> ${sentence(r)}\n\n-- \n${who}\n`),
        `--${b}`,
        "Content-Type: text/html; charset=UTF-8",
        "Content-Transfer-Encoding: 7bit",
        "",
        `<div>${line}<br>From the quay it looked fine.</div><blockquote>${sentence(r)}</blockquote><div>-- <br>${who}</div>`,
        `--${b}--`,
      ]
    : [
        `--${b}`,
        "Content-Type: text/xml; charset=UTF-8",
        "Content-Transfer-Encoding: 7bit",
        "",
        `<?xml version="1.0"?><message xmlns="urn:example:chat"><sender>${who}</sender><ts>${t}</ts><text>${line}</text></message>`,
        `--${b}`,
        "Content-Type: text/html; charset=UTF-8",
        "Content-Transfer-Encoding: 7bit",
        "",
        `<div class="chat-message"><span class="sender">${who}</span> <span class="ts">${rfc(d)}</span><p>${line}</p></div>`,
        `--${b}--`,
      ];
  msgs.push(
    [
      `From ${addr(who)} ${asctime(d)}`,
      `X-GM-THRID: ${thread}`,
      "X-Gmail-Labels: Chat,Archived",
      `Delivered-To: ${addr(people[0]!)}`,
      `Received: by 2002:a05:6902:0001 with SMTP id s${i}; ${rfc(d)}`,
      `To: ${addr(people[0]!)}`,
      "MIME-Version: 1.0",
      `Subject: Chat with ${who}`,
      "Content-Type: multipart/alternative;",
      `\tboundary="${b}"`,
      `Message-Id: <chat-${String(i).padStart(4, "0")}-${Math.floor(t / 1000)}@chat.example.invalid>`,
      `From: ${who} <${addr(who)}>`,
      `Date: ${rfc(d)}`,
      "",
      ...body,
      "",
    ].join("\n"),
  );
}
const out = msgs.join("\n");
writeFileSync(OUT, out);
console.log(`wrote ${OUT} (${out.length} bytes, ${msgs.length} messages)`);
