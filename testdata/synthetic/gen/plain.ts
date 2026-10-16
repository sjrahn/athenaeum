#!/usr/bin/env bun
// plain.ts — the twins whose test is classify + attest + lint: fictional content in the shape of the private
// regression artifacts (testdata/exemplars.yaml, `source: regression`), one function each. The text formats are
// written by this script and reproduce byte-for-byte; the raster, video and the receipt PDF come from a tool
// (ImageMagick, ffmpeg, typst — versions in gen/README.md) and are pinned by the committed bytes, as the README says.
//
//   bun testdata/synthetic/gen/plain.ts [--only name,name]     names: md js json vcf p21 tsv png jpg mp4 receipt
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

const HERE = dirname(Bun.fileURLToPath(import.meta.url));
const SYN = join(HERE, "..");
const out = (name: string, body: string | Uint8Array) => {
  writeFileSync(join(SYN, name), body);
  console.log(`wrote ${name}`);
};
const run = (cmd: string[]) => {
  const r = Bun.spawnSync(cmd, { stdout: "pipe", stderr: "pipe" });
  if (r.exitCode !== 0) throw new Error(`${cmd[0]}: ${r.stderr.toString()}`);
};

// a small deterministic generator for the fabricated rows (no Math.random: the bytes must reproduce)
function lcg(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
}
const FIRST = ["Ada", "Bo", "Cyd", "Dee", "Eli", "Fay", "Gus", "Hal", "Ida", "Jo", "Kai", "Lou", "Max", "Nia", "Oz", "Pat", "Quin", "Rae", "Sol", "Tam"];
const LAST = ["Abbott", "Birch", "Calder", "Dale", "Ennis", "Frost", "Grove", "Hale", "Irwin", "Judd", "Kerr", "Lowe", "Moss", "Nash", "Orme", "Penn", "Quill", "Rowe", "Stone", "Thorn"];
const STREETS = ["Harbour Row", "Quay Street", "Mill Lane", "Orchard Close", "Station Road", "Beacon Hill", "Ferry Way", "Linden Walk"];
const TOWNS = ["Port Ellen", "Wexcombe", "Stanlow", "Ashby Fen", "Kirkhaven", "Marlow Cross"];

const gens: Record<string, () => void> = {
  // ── text/markdown: a project readme, five headings, a list, a fenced block, a table ───────────────────────────
  md() {
    const md = `# Tidewatch

A small command-line tool that reads tide tables for a harbour and prints the next high and low water, the
height, and the time to go. It exists because the harbour office publishes the tables as a spreadsheet and
nobody wants to open a spreadsheet at five in the morning.

## Installing

Tidewatch is a single script. Put it somewhere on your path and make it executable:

\`\`\`sh
curl -O https://example.invalid/tidewatch/tidewatch.sh
chmod +x tidewatch.sh
mv tidewatch.sh ~/.local/bin/tidewatch
\`\`\`

It needs a POSIX shell and \`awk\`. Nothing else.

## Usage

\`\`\`
tidewatch [--port NAME] [--days N] [--json]
\`\`\`

- \`--port\` selects the harbour; the default is the one in \`~/.config/tidewatch/port\`.
- \`--days\` prints that many days ahead instead of the next event only.
- \`--json\` prints one object per event for other tools to read.

Without arguments it prints something like:

\`\`\`
Port Ellen   high  06:42  4.1 m   in 1 h 12 min
Port Ellen   low   12:58  0.7 m   in 7 h 28 min
\`\`\`

## Tables

The tables live under \`~/.config/tidewatch/tables/\`, one file per port and year, as tab-separated values with
a header row. The columns are:

| column | meaning                              |
| ------ | ------------------------------------ |
| date   | ISO date of the event                |
| time   | local time, 24-hour clock            |
| kind   | \`high\` or \`low\`                      |
| height | metres above chart datum, one decimal |

A table that is missing for the current year makes the tool exit with status 3 and a message naming the file
it looked for.

## Heights and datums

Heights are relative to chart datum, which is the lowest astronomical tide for the port. To convert to the
local land datum add the offset printed in the table's header comment; it differs by port and is usually
between one and three metres.

Predictions do not account for weather. A deep low or a strong onshore wind can add half a metre or more, and
the tool says nothing about that.

## Contributing

Bug reports and tables for other ports are welcome. Keep tables in the same format and name them
\`<port>-<year>.tsv\`. Please do not send tables copied from a publisher's almanac; those are not ours to share.

## Licence

Tidewatch is released under the MIT licence; see \`LICENSE\`.
`;
    out("tidewatch-readme.md", md);
  },

  // ── text/javascript: one self-contained script, a few hundred lines ──────────────────────────────────────────
  js() {
    const lines: string[] = [];
    lines.push(
      "// tidewatch.js — a tide-table reader bundled into one file: parser, predictor, formatter and the command line.",
      "// Generated as a regression twin; the shape (one large self-contained script) is what matters, not the code.",
      '"use strict";',
      "",
      "const DATUM_OFFSET = { 'port-ellen': 1.9, 'wexcombe': 2.4, 'stanlow': 1.2, 'ashby-fen': 2.8 };",
      "",
      "function parseTable(text) {",
      "  const rows = text.split('\\n').filter((l) => l && !l.startsWith('#'));",
      "  const head = rows.shift().split('\\t');",
      "  return rows.map((r) => Object.fromEntries(r.split('\\t').map((v, i) => [head[i], v])));",
      "}",
      "",
    );
    for (let i = 0; i < 40; i++) {
      lines.push(
        `function step${i}(events, now) {`,
        `  // stage ${i}: ${["filter past events", "sort by time", "attach the datum offset", "round the height", "label the kind"][i % 5]}`,
        `  const k = ${i} % 5;`,
        "  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));",
        "}",
        "",
      );
    }
    lines.push(
      "function format(e) {",
      "  const h = e.height.toFixed(1);",
      "  return `${e.port.padEnd(12)} ${e.kind.padEnd(5)} ${e.time}  ${h} m   in ${e.until}`;",
      "}",
      "",
      "function main(argv) {",
      "  const port = argv.includes('--port') ? argv[argv.indexOf('--port') + 1] : 'port-ellen';",
      "  const json = argv.includes('--json');",
      "  const table = parseTable(require('fs').readFileSync(`${port}-2026.tsv`, 'utf8'));",
      "  let events = table.map((r) => ({ port, kind: r.kind, time: r.time, height: Number(r.height), t: Date.parse(`${r.date}T${r.time}`) }));",
    );
    for (let i = 0; i < 40; i++) lines.push(`  events = step${i}(events, Date.now());`);
    lines.push(
      "  for (const e of events.slice(0, 2)) console.log(json ? JSON.stringify(e) : format(e));",
      "}",
      "",
      "if (require.main === module) main(process.argv.slice(2));",
      "module.exports = { parseTable, format, DATUM_OFFSET };",
      "",
    );
    out("tidewatch.js", lines.join("\n"));
  },

  // ── application/json: an object with one top-level array ────────────────────────────────────────────────────
  json() {
    const r = lcg(7);
    const pick = <T>(a: T[]) => a[Math.floor(r() * a.length)]!;
    const entries = Array.from({ length: 24 }, (_, i) => ({
      id: `adr-${String(i + 1).padStart(3, "0")}`,
      name: `${pick(FIRST)} ${pick(LAST)}`,
      street: `${1 + Math.floor(r() * 120)} ${pick(STREETS)}`,
      town: pick(TOWNS),
      postcode: `PE${1 + Math.floor(r() * 30)} ${1 + Math.floor(r() * 9)}${pick(["AB", "CD", "EF", "GH"])}`,
      country: "GB",
    }));
    out("address-book.json", `${JSON.stringify({ addresses: entries }, null, 2)}\n`);
  },

  // ── text/vcard: a vCard 3.0 collection in the shape of a contacts export ─────────────────────────────────────
  vcf() {
    const r = lcg(11);
    const pick = <T>(a: T[]) => a[Math.floor(r() * a.length)]!;
    const cards: string[] = [];
    for (let i = 0; i < 30; i++) {
      const first = pick(FIRST);
      const last = pick(LAST);
      const n = 100000 + Math.floor(r() * 899999);
      cards.push(
        [
          "BEGIN:VCARD",
          "VERSION:3.0",
          "PRODID:-//Example//Address Book 2.1//EN",
          `N:${last};${first};;;`,
          `FN:${first} ${last}`,
          `EMAIL;type=INTERNET;type=HOME;type=pref:${first.toLowerCase()}.${last.toLowerCase()}@example.invalid`,
          `TEL;type=CELL;type=VOICE;type=pref:+44 7700 ${String(n).slice(0, 6)}`,
          `ADR;type=HOME;type=pref:;;${1 + Math.floor(r() * 120)} ${pick(STREETS)};${pick(TOWNS)};;PE${1 + Math.floor(r() * 30)} ${1 + Math.floor(r() * 9)}AB;United Kingdom`,
          `REV:2026-0${1 + (i % 9)}-${String(1 + (i % 27)).padStart(2, "0")}T0${i % 10}:00:00Z`,
          `UID:${String(i + 1).padStart(8, "0")}-0000-4000-8000-00000000c0de`,
          "END:VCARD",
        ].join("\r\n"),
      );
    }
    out("address-cards.vcf", `${cards.join("\r\n")}\r\n`);
  },

  // ── application/p21: an ISO 10303-21 exchange file (IFC4 schema) with a handful of entities ─────────────────
  p21() {
    const p21 = `ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
FILE_NAME('bracket.ifc','2026-03-12T10:15:00',('Example Author'),('Example Organisation'),'Example Exporter 1.0','Example CAD 4.2','');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCPROJECT('0YvctVUKr0kugbFTf53O9L',#2,'Bracket',$,$,$,$,(#9),#5);
#2=IFCOWNERHISTORY(#3,#4,$,.ADDED.,$,$,$,1773310500);
#3=IFCPERSONANDORGANIZATION(#6,#7,$);
#4=IFCAPPLICATION(#7,'1.0','Example Exporter','EXAMPLE');
#5=IFCUNITASSIGNMENT((#10,#11,#12));
#6=IFCPERSON($,'Author','Example',$,$,$,$,$);
#7=IFCORGANIZATION($,'Example Organisation',$,$,$);
#8=IFCCARTESIANPOINT((0.,0.,0.));
#9=IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-05,#13,$);
#10=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);
#11=IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.);
#12=IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.);
#13=IFCAXIS2PLACEMENT3D(#8,$,$);
#14=IFCSITE('2Yvct5UKr0kugbFTf53O9M',#2,'Site',$,$,#15,$,$,.ELEMENT.,$,$,$,$,$);
#15=IFCLOCALPLACEMENT($,#13);
#16=IFCBUILDING('3Yvct5UKr0kugbFTf53O9N',#2,'Workshop',$,$,#17,$,$,.ELEMENT.,$,$,$);
#17=IFCLOCALPLACEMENT(#15,#13);
#18=IFCBUILDINGSTOREY('4Yvct5UKr0kugbFTf53O9O',#2,'Ground',$,$,#19,$,$,.ELEMENT.,0.);
#19=IFCLOCALPLACEMENT(#17,#13);
#20=IFCRECTANGLEPROFILEDEF(.AREA.,'Plate',#21,120.,80.);
#21=IFCAXIS2PLACEMENT2D(#22,$);
#22=IFCCARTESIANPOINT((0.,0.));
#23=IFCDIRECTION((0.,0.,1.));
#24=IFCEXTRUDEDAREASOLID(#20,#13,#23,6.);
#25=IFCSHAPEREPRESENTATION(#9,'Body','SweptSolid',(#24));
#26=IFCPRODUCTDEFINITIONSHAPE($,$,(#25));
#27=IFCPLATE('5Yvct5UKr0kugbFTf53O9P',#2,'Bracket plate',$,$,#28,#26,'PL-001',.NOTDEFINED.);
#28=IFCLOCALPLACEMENT(#19,#13);
#29=IFCRELCONTAINEDINSPATIALSTRUCTURE('6Yvct5UKr0kugbFTf53O9Q',#2,$,$,(#27),#18);
#30=IFCRELAGGREGATES('7Yvct5UKr0kugbFTf53O9R',#2,$,$,#1,(#14));
#31=IFCRELAGGREGATES('8Yvct5UKr0kugbFTf53O9S',#2,$,$,#14,(#16));
#32=IFCRELAGGREGATES('9Yvct5UKr0kugbFTf53O9T',#2,$,$,#16,(#18));
ENDSEC;
END-ISO-10303-21;
`;
    out("bracket.p21", p21);
  },

  // ── text/tab-separated-values: a nine-column media manifest with a gap column ────────────────────────────────
  tsv() {
    const r = lcg(5);
    const head = ["id", "guid", "kind", "filename", "mime", "bytes", "taken_at", "present", "note"];
    const rows = [head.join("\t")];
    for (let i = 0; i < 60; i++) {
      const kind = pick3(r, ["image", "video", "audio"]);
      const ext = { image: "heic", video: "mov", audio: "m4a" }[kind]!;
      const mime = { image: "image/heic", video: "video/quicktime", audio: "audio/mp4" }[kind]!;
      const present = r() < 0.8 ? "yes" : "no";
      rows.push(
        [
          String(1000 + i),
          `${hex(r, 8)}-${hex(r, 4)}-4${hex(r, 3)}-8${hex(r, 3)}-${hex(r, 12)}`.toUpperCase(),
          kind,
          `IMG_${2000 + Math.floor(r() * 8000)}.${ext}`,
          mime,
          String(20000 + Math.floor(r() * 4000000)),
          `2026-0${1 + (i % 9)}-${String(1 + (i % 28)).padStart(2, "0")} ${String(i % 24).padStart(2, "0")}:${String((i * 7) % 60).padStart(2, "0")}:00`,
          present,
          present === "no" ? "missing from the export" : "",
        ].join("\t"),
      );
    }
    out("media-manifest.tsv", `${rows.join("\n")}\n`);
  },

  // ── image/png: a window-like raster with text (ImageMagick) ──────────────────────────────────────────────────
  png() {
    run([
      "magick",
      "-size",
      "800x480",
      "xc:#f3f3f3",
      "-fill",
      "#ffffff",
      "-stroke",
      "#9a9a9a",
      "-draw",
      "rectangle 40,40 760,440",
      "-stroke",
      "none",
      "-fill",
      "#2d5f8a",
      "-draw",
      "rectangle 40,40 760,72",
      "-fill",
      "#ffffff",
      "-pointsize",
      "16",
      "-draw",
      "text 52,62 'Tidewatch — Port Ellen'",
      "-fill",
      "#202020",
      "-pointsize",
      "20",
      "-draw",
      "text 60,120 'high  06:42  4.1 m   in 1 h 12 min'",
      "-draw",
      "text 60,160 'low   12:58  0.7 m   in 7 h 28 min'",
      "-draw",
      "text 60,200 'high  19:05  4.3 m   in 13 h 35 min'",
      "-strip",
      join(SYN, "window.png"),
    ]);
    console.log("wrote window.png");
  },

  // ── image/jpeg: a photograph-like raster carrying an EXIF orientation (ImageMagick writes the tag) ───────────
  jpg() {
    run([
      "magick",
      "-size",
      "640x480",
      "plasma:#2b6ca3-#e9d8a6",
      "-blur",
      "0x2",
      "-fill",
      "#3a5a2a",
      "-draw",
      "ellipse 320,420 400,90 0,360",
      "-quality",
      "82",
      join(SYN, "garden.jpg"),
    ]);
    // ImageMagick writes no Exif for a synthesised image: the orientation rides in an APP1 segment written here
    const jpg = new Uint8Array(require("node:fs").readFileSync(join(SYN, "garden.jpg")));
    out("garden.jpg", withExifOrientation(jpg, 6));
  },

  // ── video/mp4: two seconds, h264 video + aac audio (ffmpeg) ──────────────────────────────────────────────────
  mp4() {
    run([
      "ffmpeg",
      "-y",
      "-loglevel",
      "error",
      "-f",
      "lavfi",
      "-i",
      "testsrc=duration=2:size=320x240:rate=25",
      "-f",
      "lavfi",
      "-i",
      "sine=frequency=440:duration=2",
      "-c:v",
      "libx264",
      "-pix_fmt",
      "yuv420p",
      "-c:a",
      "aac",
      "-shortest",
      "-movflags",
      "+faststart",
      join(SYN, "countdown.mp4"),
    ]);
    console.log("wrote countdown.mp4");
  },

  // ── application/pdf: a single-page till receipt, print-to-PDF style (typst) ──────────────────────────────────
  receipt() {
    const typ = `// till-receipt.typ — generated by testdata/synthetic/gen/plain.ts
#set document(title: "Receipt 00412", date: none)
#set page(width: 80mm, height: auto, margin: 6mm)
#set text(font: "DejaVu Sans Mono", size: 8pt)
#align(center)[*HARBOUR STORES* \\ 12 Quay Street, Port Ellen \\ VAT GB 000 0000 00]
#v(4pt)
Receipt 00412 #h(1fr) 2026-03-12 17:42
Till 2 #h(1fr) Served by: R.
#line(length: 100%)
#table(columns: (1fr, auto, auto), stroke: none, inset: (x: 0pt, y: 2pt),
  [Rope, 8 mm, per m], [12], [18.00],
  [Shackle, galvanised], [2], [7.90],
  [Anti-fouling, 750 ml], [1], [24.50],
  [Chandlery tape], [1], [3.20],
)
#line(length: 100%)
Subtotal #h(1fr) 53.60 \\
VAT 20% #h(1fr) 10.72 \\
*Total* #h(1fr) *64.32* \\
Card #h(1fr) 64.32
#v(4pt)
#align(center)[Thank you for your custom \\ Goods may be returned within 28 days with this receipt]
`;
    writeFileSync(join(SYN, "till-receipt.typ"), typ);
    run(["typst", "compile", join(SYN, "till-receipt.typ"), join(SYN, "till-receipt.pdf")]);
    console.log("wrote till-receipt.pdf");
  },
};

/** A JPEG with an APP1 Exif segment carrying one IFD entry, Orientation = `o`, inserted after SOI. */
function withExifOrientation(jpg: Uint8Array, o: number): Uint8Array {
  if (jpg[0] !== 0xff || jpg[1] !== 0xd8) throw new Error("not a JPEG");
  // TIFF (little-endian): header 8 bytes, IFD count 2, one 12-byte entry, next-IFD 4 bytes = 26 bytes
  const tiff = new Uint8Array(26);
  const dv = new DataView(tiff.buffer);
  tiff.set([0x49, 0x49, 0x2a, 0x00]); // "II", 42
  dv.setUint32(4, 8, true); // IFD0 at offset 8
  dv.setUint16(8, 1, true); // one entry
  dv.setUint16(10, 0x0112, true); // Orientation
  dv.setUint16(12, 3, true); // SHORT
  dv.setUint32(14, 1, true); // count
  dv.setUint16(18, o, true); // value (left-aligned in the 4-byte field)
  dv.setUint32(22, 0, true); // no next IFD
  const payload = new Uint8Array(6 + tiff.length);
  payload.set([0x45, 0x78, 0x69, 0x66, 0x00, 0x00]); // "Exif\0\0"
  payload.set(tiff, 6);
  const seg = new Uint8Array(4 + payload.length);
  seg.set([0xff, 0xe1, (payload.length + 2) >> 8, (payload.length + 2) & 0xff]);
  seg.set(payload, 4);
  const outBytes = new Uint8Array(jpg.length + seg.length);
  outBytes.set(jpg.subarray(0, 2));
  outBytes.set(seg, 2);
  outBytes.set(jpg.subarray(2), 2 + seg.length);
  return outBytes;
}

function pick3<T>(r: () => number, a: T[]): T {
  return a[Math.floor(r() * a.length)]!;
}
function hex(r: () => number, n: number): string {
  let s = "";
  for (let i = 0; i < n; i++) s += Math.floor(r() * 16).toString(16);
  return s;
}

const only = process.argv.includes("--only") ? process.argv[process.argv.indexOf("--only") + 1]!.split(",") : Object.keys(gens);
for (const k of only) {
  const g = gens[k];
  if (!g) throw new Error(`no generator '${k}' (${Object.keys(gens).join(", ")})`);
  g();
}
