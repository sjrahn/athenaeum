#!/usr/bin/env bun
// chat-export.ts — the twin of the Discord export: a zip in the exporter's layout — one `<server> - <channel> -
// <name> [id].json` written with zstd (method 93), an emoji SVG under assets/ (zstd), seven PNG attachments under
// assets/ (stored) — nine members. The JSON carries the exporter's shape (guild, channel, dateRange, messages with
// author, attachments, reactions). Fictional server, generated chatter, rasters from lib/png.ts.
//
//   bun testdata/synthetic/gen/chat-export.ts
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { png } from "./lib/png.ts";
import { FIRST, LAST, int, lcg, pick, sentence } from "./lib/rand.ts";
import { dosStamp } from "./lib/zip.ts";
import { zip, type ZipEntry } from "./lib/zip.ts";

const OUT = join(dirname(Bun.fileURLToPath(import.meta.url)), "..", "quay-chat-export.zip");
const r = lcg(403);
const GUILD = { id: "100000000000000001", name: "The Lantern Room" };
const CHANNEL = { id: "100000000000000002", name: "general", category: "Text Channels" };
const users = Array.from({ length: 4 }, (_, i) => ({ id: `10000000000000${i}010`, name: `${pick(r, FIRST)}${pick(r, LAST)}`.toLowerCase(), nickname: pick(r, FIRST) }));
const assets: { name: string; bytes: Uint8Array; method: 0 | 93 }[] = [];
for (let i = 0; i < 7; i++) {
  const w = 24 + i * 4;
  assets.push({
    name: `assets/${(i * 7919 + 11).toString(16).padStart(16, "0")}-${(i * 104729 + 3).toString(16).padStart(16, "0")}.png`,
    bytes: png(w, w, (x, y) => [(x * 255) / w, (y * 255) / w, (i * 40) & 255].map(Math.floor) as [number, number, number]),
    method: 0,
  });
}
const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 36"><path fill="#FFCC4D" d="M36 18c0 9.941-8.059 18-18 18S0 27.941 0 18 8.059 0 18 0s18 8.059 18 18z"/><path fill="#664500" d="M18 21c-3.623 0-6.027-.422-9-1-.679-.131-2 0-2 2 0 4 4.595 9 11 9 6.404 0 11-5 11-9 0-2-1.321-2.131-2-2-2.973.578-5.377 1-9 1z"/></svg>\n`;
assets.push({ name: "assets/1f600-00000000c0de0001.svg", bytes: new TextEncoder().encode(svg), method: 93 });

const messages: unknown[] = [];
let t = Date.UTC(2026, 6, 1, 14, 0, 0);
for (let i = 0; i < 120; i++) {
  t += int(r, 30, 5400) * 1000;
  const u = pick(r, users);
  const att = i % 17 === 3 ? [assets[Math.floor(i / 17) % 7]!] : [];
  messages.push({
    id: `${1389000000000000000 + i * 4096}`,
    type: "Default",
    timestamp: new Date(t).toISOString().replace("Z", "+00:00"),
    timestampEdited: null,
    callEndedTimestamp: null,
    isPinned: false,
    content: sentence(r),
    author: { id: u.id, name: u.name, discriminator: "0000", nickname: u.nickname, color: null, isBot: false, roles: [], avatarUrl: `https://cdn.example.invalid/avatars/${u.id}.png` },
    attachments: att.map((a) => ({ id: `${1389000000000000000 + i * 4096 + 1}`, url: a.name, fileName: a.name.slice(7), fileSizeBytes: a.bytes.length })),
    embeds: [],
    stickers: [],
    reactions: i % 9 === 0 ? [{ emoji: { id: null, name: "😀", code: "grinning", isAnimated: false, imageUrl: "assets/1f600-00000000c0de0001.svg" }, count: int(r, 1, 4), users: [] }] : [],
    mentions: [],
  });
}
const doc = {
  guild: { ...GUILD, iconUrl: `https://cdn.example.invalid/icons/${GUILD.id}.png` },
  channel: { ...CHANNEL, type: "GuildTextChat", categoryId: "100000000000000003", topic: null },
  dateRange: { after: null, before: null },
  exportedAt: "2026-07-04T09:15:30.000000-06:00",
  messages,
  messageCount: messages.length,
};
const entries: ZipEntry[] = [
  { path: `${GUILD.name} - ${CHANNEL.name} - quay [${CHANNEL.id}].json`, bytes: new TextEncoder().encode(JSON.stringify(doc, null, 2)), method: 93, dos: dosStamp(2026, 7, 13, 12, 35, 0) },
  ...assets.map((a, i) => ({ path: a.name, bytes: a.bytes, method: a.method, dos: dosStamp(2026, 7, 12, 23, 24 + i, 0) })),
];
const bytes = zip(entries);
writeFileSync(OUT, bytes);
console.log(`wrote ${OUT} (${bytes.length} bytes, ${entries.length} members)`);
