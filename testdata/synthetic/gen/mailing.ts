#!/usr/bin/env bun
// mailing.ts — the twin of the festival mailing: a Gmail-shaped message, multipart/mixed over multipart/alternative
// (a quoted-printable text body with five paragraphs and a signature after a sigdash, an HTML alternative), then three
// attachments — a spreadsheet (a minimal OOXML workbook written by lib/zip.ts), a JPEG and a PDF (the committed
// synthetic rasters). Fictional organisers; CRLF throughout; every boundary and id fixed, so the bytes reproduce.
//
//   bun testdata/synthetic/gen/mailing.ts
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { zip } from "./lib/zip.ts";

const HERE = dirname(Bun.fileURLToPath(import.meta.url));
const SYN = join(HERE, "..");
const OUT = join(SYN, "regatta-mailing.eml");

/** Quoted-printable (RFC 2045 §6.7): non-ASCII and `=` as =XX, a trailing space as =20, soft breaks at 76. */
export function qp(text: string): string {
  const bytes = new TextEncoder().encode(text.replace(/\r?\n/g, "\n"));
  const lines: string[] = [];
  let line = "";
  const push = (tok: string) => {
    if (line.length + tok.length > 75) {
      lines.push(`${line}=`);
      line = "";
    }
    line += tok;
  };
  for (let i = 0; i < bytes.length; i++) {
    const b = bytes[i]!;
    if (b === 0x0a) {
      if (line.endsWith(" ")) line = `${line.slice(0, -1)}=20`;
      lines.push(line);
      line = "";
    } else if (b === 0x3d || b < 0x20 || b > 0x7e) push(`=${b.toString(16).toUpperCase().padStart(2, "0")}`);
    else push(String.fromCharCode(b));
  }
  if (line) lines.push(line);
  return lines.join("\r\n");
}
const b64 = (b: Uint8Array) => Buffer.from(b).toString("base64").replace(/(.{76})/g, "$1\r\n");

const text = `Hello volunteers,

Thank you all for signing up for the Port Ellen Regatta on the weekend of 23–24 May. This message carries the schedule, the volunteer poster and the roles sheet; please read the roles sheet before the briefing.

The briefing is at the harbour office at 08:00 on Saturday. Tea and bacon rolls are provided — bring a waterproof, the forecast is "changeable".

Parking at the quay is for competitors only. Volunteers park at the school on Mill Lane and walk down; it is five minutes.

If you can no longer make it, reply to this message by Wednesday so the roster can be redone. Replies go to the organisers, not to everyone.

See you on the quay,

-- 
Ada Abbott
Volunteer coordinator, Port Ellen Regatta
+44 7700 900123
`;
const html = `<div dir="ltr"><p>Hello volunteers,</p><p>Thank you all for signing up for the <b>Port Ellen Regatta</b> on the weekend of 23–24 May. This message carries the schedule, the volunteer poster and the roles sheet; please read the roles sheet before the briefing.</p><p>The briefing is at the harbour office at 08:00 on Saturday. Tea and bacon rolls are provided — bring a waterproof, the forecast is &quot;changeable&quot;.</p><p>Parking at the quay is for competitors only. Volunteers park at the school on Mill Lane and walk down; it is five minutes.</p><p>If you can no longer make it, reply to this message by Wednesday so the roster can be redone. Replies go to the organisers, not to everyone.</p><p>See you on the quay,</p><div>-- <br>Ada Abbott<br>Volunteer coordinator, Port Ellen Regatta<br>+44 7700 900123</div></div>
`;

/** A minimal OOXML workbook: one sheet, a header row and a few rows of inline strings. */
function xlsx(): Uint8Array {
  const rows = [
    ["Time", "Event", "Volunteers needed"],
    ["08:00", "Briefing", "all"],
    ["09:30", "Dinghy start", "4"],
    ["11:00", "Keelboat start", "6"],
    ["13:00", "Lunch", "2"],
    ["15:30", "Prize giving", "3"],
  ];
  const cell = (r: number, c: number, v: string) => `<c r="${String.fromCharCode(65 + c)}${r + 1}" t="inlineStr"><is><t>${v}</t></is></c>`;
  const sheet = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${rows.map((row, r) => `<row r="${r + 1}">${row.map((v, c) => cell(r, c, v)).join("")}</row>`).join("")}</sheetData></worksheet>`;
  const e = (s: string) => new TextEncoder().encode(s);
  return zip([
    {
      path: "[Content_Types].xml",
      bytes: e(
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>`,
      ),
    },
    {
      path: "_rels/.rels",
      bytes: e(
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`,
      ),
    },
    {
      path: "xl/workbook.xml",
      bytes: e(
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Schedule" sheetId="1" r:id="rId1"/></sheets></workbook>`,
      ),
    },
    {
      path: "xl/_rels/workbook.xml.rels",
      bytes: e(
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>`,
      ),
    },
    { path: "xl/worksheets/sheet1.xml", bytes: e(sheet) },
  ]);
}

const B1 = "000000000000a1b2c30650043266";
const B2 = "000000000000a1b2c20650043264";
const jpg = new Uint8Array(readFileSync(join(SYN, "garden.jpg")));
const pdf = new Uint8Array(readFileSync(join(SYN, "till-receipt.pdf")));
const parts = [
  "X-GM-THRID: 1863140059282400001",
  "X-Gm-Message-State: AOJu0YzSyntheticTwinOfTheFestivalMailingNoRealStateHere0001",
  "X-Received: by 2002:a05:690e:1188:b0:651:c9a8:0001 with SMTP id 0001-0001mr1d50.64.1776828822136;",
  "        Tue, 21 Apr 2026 20:33:42 -0700 (PDT)",
  "MIME-Version: 1.0",
  "From: Ada Abbott <ada.abbott@example.invalid>",
  "Date: Tue, 21 Apr 2026 21:33:28 -0600",
  "Message-ID: <CAA3XGkX-regatta-2026-volunteers-0001@mail.example.invalid>",
  "Subject: Port Ellen Regatta 2026 =?UTF-8?Q?=E2=80=94?= volunteer schedule, poster and roles",
  "To: Regatta volunteers <regatta-volunteers@example.invalid>",
  `Content-Type: multipart/mixed; boundary="${B1}"`,
  "",
  `--${B1}`,
  `Content-Type: multipart/alternative; boundary="${B2}"`,
  "",
  `--${B2}`,
  'Content-Type: text/plain; charset="UTF-8"',
  "Content-Transfer-Encoding: quoted-printable",
  "",
  qp(text),
  `--${B2}`,
  'Content-Type: text/html; charset="UTF-8"',
  "Content-Transfer-Encoding: quoted-printable",
  "",
  qp(html),
  `--${B2}--`,
  `--${B1}`,
  "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet; ",
  '\tname="2026 Regatta Schedule.xlsx"',
  'Content-Disposition: attachment; filename="2026 Regatta Schedule.xlsx"',
  "Content-Transfer-Encoding: base64",
  "Content-ID: <f_regatta0001>",
  "X-Attachment-Id: f_regatta0001",
  "",
  b64(xlsx()),
  `--${B1}`,
  'Content-Type: image/jpeg; name="Regatta-Volunteer-Poster.jpg"',
  'Content-Disposition: attachment; filename="Regatta-Volunteer-Poster.jpg"',
  "Content-Transfer-Encoding: base64",
  "Content-ID: <f_regatta0002>",
  "X-Attachment-Id: f_regatta0002",
  "",
  b64(jpg),
  `--${B1}`,
  'Content-Type: application/pdf; name="Regatta Roles 2026.pdf"',
  'Content-Disposition: attachment; filename="Regatta Roles 2026.pdf"',
  "Content-Transfer-Encoding: base64",
  "Content-ID: <f_regatta0003>",
  "X-Attachment-Id: f_regatta0003",
  "",
  b64(pdf),
  `--${B1}--`,
  "",
];
if (import.meta.main) {
  const eml = parts.join("\r\n");
  writeFileSync(OUT, eml);
  console.log(`wrote ${OUT} (${eml.length} bytes)`);
}
