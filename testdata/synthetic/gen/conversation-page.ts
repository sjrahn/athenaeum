#!/usr/bin/env bun
// conversation-page.ts — the twin of an iMessage conversation page as imessage-exporter writes it: one <div class="message">
// per message (sent or received), a timestamp link with the full instant in its title, the sender, the bubble text,
// inlined attachments as data: images, a reply block, tapback reactions, an edit history table, a rich-link app bubble;
// the exporter's injected corpus metas and a sidecar carrying the export's provenance. Fictional chat, generated prose.
//
//   bun testdata/synthetic/gen/conversation-page.ts
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { png } from "./lib/png.ts";
import { int, lcg, pick, sentence } from "./lib/rand.ts";

const SYN = join(dirname(Bun.fileURLToPath(import.meta.url)), "..");
const OUT = join(SYN, "quay-messages.html");
const r = lcg(7700);
const HANDLE = "+44 7700 900456";
const PERIOD = "2026-03";
const THEM = "Bo Calder";
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const stamp = (d: Date) => {
  const h = d.getUTCHours();
  const hh = h % 12 === 0 ? 12 : h % 12;
  return `${MON[d.getUTCMonth()]} ${String(d.getUTCDate()).padStart(2, "0")}, ${d.getUTCFullYear()}  ${hh}:${String(d.getUTCMinutes()).padStart(2, "0")}:${String(d.getUTCSeconds()).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
};
const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const b64png = (i: number) => Buffer.from(png(12, 12, (x, y) => [(x * 20 + i * 30) & 255, (y * 20) & 255, 90])).toString("base64");

let t = Date.UTC(2026, 2, 2, 9, 12, 5);
const msgs: string[] = [];
for (let i = 0; i < 40; i++) {
  t += int(r, 40, 9000) * 1000;
  const d = new Date(t);
  const sent = r() < 0.5;
  const parts: string[] = [];
  if (i === 7 || i === 23) parts.push(`<div class="message_part"><img src="data:image/png;base64,${b64png(i)}" alt="attachment"></div>`);
  if (i === 12) parts.push(`<div class="message_part"><div class="app"><a href="https://example.invalid/tides/port-ellen">Tide times for the harbour</a><div class="caption">example.invalid</div></div></div>`);
  else if (i === 18)
    parts.push(
      `<div class="message_part"><div class="edited"><table><tbody><tr><td><span class="timestamp">${stamp(d)}</span></td><td>${esc(sentence(r))}</td></tr></tbody><tfoot><tr><td><span class="timestamp">${stamp(new Date(t + 60000))}</span></td><td><b>${esc(sentence(r))}</b></td></tr></tfoot></table></div></div>`,
    );
  else parts.push(`<div class="message_part"><span class="bubble">${esc(sentence(r))}${r() < 0.3 ? ` <u>${esc(sentence(r))}</u>` : ""}</span></div>`);
  const reply = i === 30 ? `<div class="reply"><div class="received"><p><span class="timestamp"><a title="${stamp(new Date(t - 400000))}">${stamp(new Date(t - 400000))}</a></span><span class="sender">${THEM}</span></p><hr><div class="message_part"><span class="bubble">${esc(sentence(r))}</span></div></div></div>` : "";
  const tap = i % 9 === 4 ? `<div class="tapbacks"><span class="tapback">❤️ by ${sent ? THEM : "Me"}</span></div>` : "";
  const read = sent && r() < 0.5 ? ` (Read by them after ${int(r, 1, 40)} minutes)` : "";
  msgs.push(
    `<div class="message">\n<div class="${sent ? "sent iMessage" : "received"}">\n<p><span class="timestamp"><a title="${stamp(d)}" href="sms://${encodeURIComponent(HANDLE)}?ts=${Math.floor(t / 1000)}">${stamp(d)}</a>${read}</span><span class="sender">${sent ? "Me" : THEM}</span></p>\n<hr>\n${reply}${parts.join("\n")}\n${tap}</div>\n</div>`,
  );
}
const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="corpus-origin-schema" content="imessage-export">
<meta name="corpus-origin-period" content="${PERIOD}">
<meta name="corpus-origin-handle" content="${HANDLE}">
<title>${HANDLE}</title>
<style>body{font-family:-apple-system,sans-serif;max-width:720px;margin:auto}.message{margin:8px 0}.sent{text-align:right}.sent .bubble{background:#1f8aff;color:#fff}.received .bubble{background:#e9e9eb}.bubble{display:inline-block;padding:8px 12px;border-radius:16px}.timestamp{font-size:.8em;color:#777}.sender{font-weight:bold;margin-left:.5em}hr{border:0}.tapback{font-size:.85em}.app{border:1px solid #ccc;padding:6px}.edited table{font-size:.9em}</style>
<link rel="stylesheet" href="style.css">
</head>
<body>
${msgs.join("\n")}
</body>
</html>
`;
writeFileSync(OUT, html);
writeFileSync(
  `${OUT}.capture.yaml`,
  `# provenance of a local export, as the producer leaves it beside the bytes (D-sidecar)\norigin: imessage-export\nvia: export\nfetched_at: "2026-04-01T06:00:00Z"\nsnapshot_engine: imessage-exporter 3.0.0\norigin_fields:\n  schema: imessage-export\n  handle: "${HANDLE}"\n  period: "${PERIOD}"\n`,
);
console.log(`wrote ${OUT} (${html.length} chars, ${msgs.length} messages) + sidecar`);
