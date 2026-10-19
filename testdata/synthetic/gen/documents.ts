#!/usr/bin/env bun
// documents.ts — the twins of the loose document shapes: portal-rendered PDFs (a monthly statement, a tax slip, an
// insurance policy schedule, a banking letter, a health-care print-out, a Claude Design export), a Word document
// (minimal OOXML through lib/zip.ts), an owner statement (markdown), a single contact card, an SMS backup (NDJSON,
// MMS inlined), a Timeline export (JSON), a stylesheet, a TypeScript and a Python source, a loose calendar and route.
// Fictional institutions and people; generated numbers.
//
//   bun testdata/synthetic/gen/documents.ts
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { statementPdf } from "./bundles2.ts";
import { png } from "./lib/png.ts";
import { int, lcg, paragraph, sentence } from "./lib/rand.ts";
import { zip } from "./lib/zip.ts";
import { writeTestimony } from "./testimony.ts";

const SYN = join(dirname(Bun.fileURLToPath(import.meta.url)), "..");
const TMP = join(process.env.CLAUDE_JOB_DIR ?? "/tmp", "tmp", "documents-gen");
const e = (s: string) => new TextEncoder().encode(s);
const out = (name: string, bytes: Uint8Array | string) => {
  writeFileSync(join(SYN, name), bytes);
  console.log(`wrote ${name}`);
};
function typst(src: string, tag: string): Uint8Array {
  mkdirSync(TMP, { recursive: true });
  const p = join(TMP, `${tag}.typ`);
  writeFileSync(p, `#set document(date: none)\n${src}`);
  const r = Bun.spawnSync(["typst", "compile", p, join(TMP, `${tag}.pdf`)], { stderr: "pipe" });
  if (r.exitCode !== 0) throw new Error(r.stderr.toString());
  return new Uint8Array(readFileSync(join(TMP, `${tag}.pdf`)));
}
const r = lcg(500);

// ── PDFs ──
out("statement-2026-03.pdf", statementPdf(lcg(501), 3, "Ada Abbott", "00-00-00 12345678"));
void writeTestimony("statement-2026-03.pdf");
out("tax-slip-2025.pdf", typst(`#set page(paper: "a4", margin: 2cm)\n#set text(size: 10pt)\n#align(center)[*Statement of Remuneration Paid* \\ Tax year 2025 · Original]\n#v(10pt)\n#table(columns: (auto, 1fr, auto, 1fr), [*Employer*], [Harbour Stores Ltd], [*Employee*], [Ada Abbott], [*Box 14 Employment income*], [${int(r, 20000, 60000)}.00], [*Box 22 Income tax deducted*], [${int(r, 2000, 9000)}.00], [*Box 16 Pension contributions*], [${int(r, 500, 3000)}.00], [*Box 18 Insurance premiums*], [${int(r, 200, 900)}.00])\n#v(10pt)\n#text(size: 8pt)[Rendered from the authority's portal on 2026-03-02. Fictional slip for the regression suite.]`, "tax-slip"));
void writeTestimony("tax-slip-2025.pdf");
out("policy-schedule.pdf", typst(`#set page(paper: "a4", margin: 2cm)\n#set text(size: 10pt)\n= Policy schedule\n\nInsurer: Example Mutual · Brand: Harbour Cover · Policy number HC-0000001\n\n#table(columns: (1fr, 1fr), [*Line*], [Home contents], [*Insured*], [Ada Abbott], [*Risk address*], [14 Mill Lane, Port Ellen], [*Effective*], [2026-04-01], [*Expiry*], [2027-03-31], [*Sum insured*], [${int(r, 20, 60)},000], [*Excess*], [${int(r, 1, 5)}00], [*Annual premium*], [${int(r, 150, 400)}.00])\n\n== Endorsements\n\n${sentence(r)}\n\n#text(size: 8pt)[Fictional policy for the regression suite.]`, "policy"));
void writeTestimony("policy-schedule.pdf");
out("account-confirmation.pdf", typst(`#set page(paper: "a4", margin: 2.5cm)\n#set text(size: 11pt)\n*Example Building Society* \\ 1 Quay Street, Port Ellen\n#v(16pt)\n2026-02-10\n#v(16pt)\nAda Abbott \\ 14 Mill Lane \\ Port Ellen\n#v(16pt)\nDear Ms Abbott,\n\n*Confirmation of account details*\n\nThis letter confirms that the account below is held in your name.\n\n#table(columns: (auto, 1fr), [Sort code], [00-00-00], [Account number], [\\*\\*\\*\\*5678], [Account type], [Everyday account])\n\n${sentence(r)}\n\nYours sincerely, \\ Customer services`, "banking-letter"));
void writeTestimony("account-confirmation.pdf");
out("chart-printout.pdf", typst(`#set page(paper: "a4", margin: 2cm)\n#set text(size: 10pt)\n*Quay Medical Practice* · Patient record print-out · Printed 2026-03-05 10:12 by Dr B. Calder\n#line(length: 100%)\n*Patient:* Ada Abbott · *DOB:* 1990-01-01 · *NHS no:* 000 000 0000\n\n== Encounters 2025-09-01 to 2026-03-01\n\n#table(columns: (auto, 1fr, 1fr), [*Date*], [*Problem*], [*Plan*], [2025-10-12], [Seasonal influenza vaccination], [Given, left deltoid], [2026-01-20], [Knee pain, left], [Rest, review in 6 weeks], [2026-03-01], [Review], [Improving; discharge])\n\n== Medications\n\n- Ibuprofen 400 mg, as required\n\n#text(size: 8pt)[Fictional record for the regression suite.]`, "chart"));
void writeTestimony("chart-printout.pdf");
out("design-export.pdf", typst(`#set page(width: 1280pt, height: 800pt, margin: 40pt, fill: rgb("#f3f3f3"))\n#set text(font: "DejaVu Sans Mono", size: 14pt)\n#rect(width: 100%, height: 100%, fill: white, stroke: 1pt + gray, inset: 24pt)[*Tidewatch — home screen* \\ \\ #rect(width: 60%, height: 120pt, fill: rgb("#2d5f8a"), inset: 12pt, text(fill: white)[high 06:42 4.1 m]) \\ \\ #rect(width: 60%, height: 120pt, fill: rgb("#e9e9eb"), inset: 12pt)[low 12:58 0.7 m]]`, "design"));
void writeTestimony("design-export.pdf");

// ── Word document (minimal OOXML) ──
const docx = zip([
  { path: "[Content_Types].xml", bytes: e(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>`) },
  { path: "_rels/.rels", bytes: e(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>`) },
  { path: "word/document.xml", bytes: e(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Regatta roles 2026</w:t></w:r></w:p><w:p><w:r><w:t>${paragraph(r)}</w:t></w:r></w:p><w:p><w:r><w:t>${paragraph(r)}</w:t></w:r></w:p><w:sectPr/></w:body></w:document>`) },
]);
out("regatta-roles.docx", docx);

// ── markdown owner statement ──
out("owner-statement.md", `---\nchannel: talk\nchannel_ref: 2026-03-12-evening\nauthored_at: 2026-03-12T21:40:00Z\ntarget: mooring plan\n---\n\nThe mooring plan I sent in February is the one that stands; the March draft was never adopted. ${sentence(r)}\n`);
void writeTestimony("owner-statement.md");

// ── a single contact card ──
out("contact-card.vcf", "BEGIN:VCARD\r\nVERSION:3.0\r\nPRODID:-//Example//Address Book 2.1//EN\r\nN:Calder;Bo;;;\r\nFN:Bo Calder\r\nORG:Harbour Stores\r\nTITLE:Chandler\r\nEMAIL;type=INTERNET;type=WORK;type=pref:bo.calder@example.invalid\r\nTEL;type=CELL;type=VOICE;type=pref:+44 7700 900456\r\nADR;type=HOME;type=pref:;;12 Quay Street;Port Ellen;;PE1 1AB;United Kingdom\r\nBDAY:1988-07-04\r\nNOTE:Mooring neighbour, berth A2.\r\nREV:2026-03-01T09:00:00Z\r\nUID:00000011-0000-4000-8000-00000000c0de\r\nEND:VCARD\r\n");
void writeTestimony("contact-card.vcf");

// ── SMS backup: one NDJSON per peer per month, MMS inlined ──
const sms: string[] = [];
let t = Date.UTC(2026, 2, 1, 8, 0, 0);
for (let i = 0; i < 25; i++) {
  t += int(r, 120, 20000) * 1000;
  const row: Record<string, unknown> = { kind: i === 9 ? "mms" : i === 20 ? "call" : "sms", direction: i % 3 ? "in" : "out", handle: "+44 7700 900456", contact_name: "Bo Calder", at: new Date(t).toISOString() };
  if (row.kind === "sms") row.text = sentence(r);
  else if (row.kind === "mms") row.parts = [{ content_type: "image/png", filename: "photo.png", data_base64: Buffer.from(png(6, 6, (x, y) => [x * 40, y * 40, 120])).toString("base64") }, { content_type: "text/plain", text: sentence(r) }];
  else Object.assign(row, { duration_s: int(r, 10, 600), status: "answered" });
  sms.push(JSON.stringify(row));
}
out("sms-2026-03.ndjson", `${sms.join("\n")}\n`);
void writeTestimony("sms-2026-03.ndjson");

// ── Timeline export ──
const segs: unknown[] = [];
t = Date.UTC(2026, 2, 1, 7, 0, 0);
for (let i = 0; i < 20; i++) {
  const start = new Date(t).toISOString().replace("Z", "+00:00");
  t += int(r, 600, 7200) * 1000;
  const end = new Date(t).toISOString().replace("Z", "+00:00");
  segs.push(i % 2 ? { startTime: start, endTime: end, visit: { hierarchyLevel: 0, probability: 0.9, topCandidate: { placeID: `ChIJ00000000000000${i}`, semanticType: i % 4 === 1 ? "HOME" : "UNKNOWN", probability: 0.8, placeLocation: "geo:55.627,-6.190" } } } : { startTime: start, endTime: end, activity: { start: "geo:55.627,-6.190", end: "geo:55.630,-6.185", distanceMeters: int(r, 200, 5000), probability: 0.7, topCandidate: { type: "walking", probability: 0.8 } } });
}
out("location-history.json", `${JSON.stringify(segs, null, 2)}\n`);
void writeTestimony("location-history.json");

// ── source and style ──
out("tidewatch.css", `:root{--ink:#202020;--sea:#2d5f8a}body{font:16px/1.5 system-ui,sans-serif;color:var(--ink);max-width:40rem;margin:auto}table{border-collapse:collapse}td,th{padding:.25rem .5rem;border-bottom:1px solid #ddd}.high{color:var(--sea)}\n`);
out("tidewatch.ts", `// tidewatch.ts — the typed core of the tide reader (twin of a TypeScript source)\nexport interface Tide {\n  port: string;\n  kind: "high" | "low";\n  time: string;\n  height: number;\n}\nexport function next(events: Tide[], now: number): Tide | undefined {\n  return events.find((e) => Date.parse(e.time) >= now);\n}\nexport const format = (e: Tide): string => \`\${e.port.padEnd(12)} \${e.kind.padEnd(5)} \${e.time}  \${e.height.toFixed(1)} m\`;\n`);
out("tidewatch.py", `#!/usr/bin/env python3\n"""tidewatch.py — the tide reader as a script (twin of a Python source)."""\nimport csv\nimport sys\nfrom datetime import datetime\n\n\ndef load(path):\n    with open(path, newline="") as fh:\n        return list(csv.DictReader(fh, delimiter="\\t"))\n\n\ndef main(argv):\n    rows = load(argv[1])\n    now = datetime.now()\n    for r in rows:\n        if datetime.fromisoformat(f"{r['date']}T{r['time']}") >= now:\n            print(f"{r['kind']:5} {r['time']}  {float(r['height']):.1f} m")\n            break\n\n\nif __name__ == "__main__":\n    main(sys.argv)\n`);

// ── a loose calendar and a loose route ──
out("harbour-events.ics", "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Example//Calendar//EN\r\nBEGIN:VEVENT\r\nUID:00000021-0000-4000-8000-00000000c0de\r\nDTSTAMP:20260301T070000Z\r\nDTSTART;VALUE=DATE:20260523\r\nDTEND;VALUE=DATE:20260525\r\nSUMMARY:Port Ellen Regatta\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nUID:00000022-0000-4000-8000-00000000c0de\r\nDTSTAMP:20260301T070000Z\r\nDTSTART:20260601T180000Z\r\nDTEND:20260601T200000Z\r\nSUMMARY:Harbour committee\r\nLOCATION:Harbour office\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n");
out("walk.gpx", `<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="Twin" xmlns="http://www.topografix.com/GPX/1/1"><trk><name>Quay loop</name><trkseg>${Array.from({ length: 30 }, (_, i) => `<trkpt lat="${(55.627 + i * 0.0002).toFixed(6)}" lon="${(-6.19 + i * 0.0003).toFixed(6)}"><ele>${(3 + (i % 5)).toFixed(1)}</ele><time>${new Date(Date.UTC(2026, 2, 8, 18, 55, i * 20)).toISOString()}</time></trkpt>`).join("")}</trkseg></trk></gpx>\n`);
