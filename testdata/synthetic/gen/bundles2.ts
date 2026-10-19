#!/usr/bin/env bun
// bundles2.ts — the twins of the remaining container shapes, one layout per function:
//   amazon   a data-request category delivery (category CSVs, invoice PDFs, proof-of-delivery images)
//   uber     a DSAR export (category CSVs beside a readme)
//   health   an Apple Health export (export.xml, the CDA re-serialisation, ECG CSVs, GPX routes, clinical JSON)
//   unraid   a host diagnostics zip (smart/, system/, config/, shares/, logs/)
//   obsidian a vault subtree (notes with frontmatter, folders, attachments, .obsidian config)
//   vendor   a vendor download tree (datasheet PDFs, DXF drawings, a nested zip, rar/7z/exe stubs by magic)
//   claude   a Claude Code session (JSONL transcript + sub-agent transcripts + tool results, zstd members)
//   bank     a year of monthly statement PDFs (typst)
//   camera   an SD-card dump (DCIM raw+HIF pairs, PRIVATE/M4ROOT clips with XML sidecars)
//   takeout  a Google Takeout slice (Fit TCX, Contacts, Maps, Keep, Calendar, the archive browser)
//   drive    a Drive download job (a flat folder of documents)
//   profile  a harvested profile year in the owner's export layout
// Every bundle gets its testimony beside it (`testimony.ts`), in the contract's shape. Fictional everything; generated prose and numbers.
//
//   bun testdata/synthetic/gen/bundles2.ts [--only amazon,uber,health,unraid,obsidian,vendor,claude,bank,camera,takeout,drive,profile]
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { png } from "./lib/png.ts";
import { FIRST, LAST, int, lcg, paragraph, pick, sentence } from "./lib/rand.ts";
import { dosStamp, zip, type ZipEntry } from "./lib/zip.ts";
import { writeTestimony } from "./testimony.ts";

const HERE = dirname(Bun.fileURLToPath(import.meta.url));
const SYN = join(HERE, "..");
const TMP = join(process.env.CLAUDE_JOB_DIR ?? "/tmp", "tmp", "bundles2-gen");
const e = (s: string) => new TextEncoder().encode(s);
const out = (name: string, bytes: Uint8Array) => {
  writeFileSync(join(SYN, name), bytes);
  console.log(`wrote ${name} (${bytes.length} bytes)`);
};
const run = (cmd: string[]) => {
  const r = Bun.spawnSync(cmd, { stdout: "pipe", stderr: "pipe" });
  if (r.exitCode !== 0) throw new Error(`${cmd[0]}: ${r.stderr.toString()}`);
};
const dos = (m: number, d: number) => dosStamp(2026, m, d, 9, 30, 0);
const name = (r: () => number) => `${pick(r, FIRST)} ${pick(r, LAST)}`;
const csv = (rows: (string | number)[][]) => e(`${rows.map((r) => r.map((c) => (typeof c === "string" && /[",\n]/.test(c) ? `"${c.replace(/"/g, '""')}"` : String(c))).join(",")).join("\n")}\n`);

/** A one-page PDF from typst source, deterministic for the same source. */
function typst(src: string, tag: string): Uint8Array {
  mkdirSync(TMP, { recursive: true });
  const p = join(TMP, `${tag}.typ`);
  writeFileSync(p, `#set document(date: none)\n${src}`);
  run(["typst", "compile", p, join(TMP, `${tag}.pdf`)]);
  return new Uint8Array(readFileSync(join(TMP, `${tag}.pdf`)));
}

/** A monthly statement: the shape of a bank's PDF — header, summary box, transaction table, footer. */
export function statementPdf(r: () => number, month: number, holder: string, acct: string): Uint8Array {
  let bal = 1200 + int(r, 0, 900);
  const rows: string[] = [];
  const n = int(r, 12, 22);
  for (let i = 0; i < n; i++) {
    const d = `2026-${String(month).padStart(2, "0")}-${String(1 + Math.floor((i * 28) / n)).padStart(2, "0")}`;
    const debit = r() < 0.7;
    const amt = debit ? int(r, 3, 180) + 0.5 : int(r, 200, 1500);
    bal += debit ? -amt : amt;
    rows.push(`[${d}], [${pick(r, ["HARBOUR STORES", "QUAY CAFE", "TRANSFER IN", "PAYROLL", "FERRY TICKETS", "MILL LANE GARAGE", "UTILITY DD", "ONLINE PURCHASE"])}], [${debit ? amt.toFixed(2) : ""}], [${debit ? "" : amt.toFixed(2)}], [${bal.toFixed(2)}]`);
  }
  return typst(
    `#set page(paper: "a4", margin: 2cm, footer: text(size: 8pt)[Statement of account · Page #context counter(page).display() · Example Building Society is a fictional institution])
#set text(font: "Libertinus Serif", size: 10pt)
#grid(columns: (1fr, 1fr), [*Example Building Society* \\ 1 Quay Street \\ Port Ellen], align(right)[*Statement of account* \\ Account ${acct} \\ Period: 2026-${String(month).padStart(2, "0")}])
#v(8pt)
${holder} \\ 14 Mill Lane \\ Port Ellen
#v(12pt)
#table(columns: (1fr, 1fr, 1fr), [*Opening balance*], [*Total out*], [*Closing balance*], [${(bal).toFixed(2)}], [—], [${bal.toFixed(2)}])
#v(12pt)
#table(columns: (auto, 1fr, auto, auto, auto), align: (left, left, right, right, right), [*Date*], [*Description*], [*Out*], [*In*], [*Balance*], ${rows.join(", ")})
#v(12pt)
#text(size: 8pt)[Interest rate 1.25% AER variable. Please check your statement and report any discrepancy within 30 days.]
`,
    `statement-${month}`,
  );
}

const gens: Record<string, () => void> = {
  amazon() {
    const r = lcg(201);
    const orders = Array.from({ length: 18 }, (_, i) => [`D01-${int(r, 1000000, 9999999)}-${int(r, 1000000, 9999999)}`, `2026-0${1 + (i % 3)}-${String(1 + (i % 27)).padStart(2, "0")}T${String(i % 24).padStart(2, "0")}:00:00Z`, pick(r, ["Website", "Mobile app"]), `${pick(r, ["Rope", "Shackle", "Lantern", "Kettle", "Chart"])} ${pick(r, ["8 mm", "galvanised", "LED", "2 l", "west coast"])}`, int(r, 1, 3), (int(r, 500, 9000) / 100).toFixed(2), "GBP", pick(r, ["Shipped", "Delivered", "Returned"])]);
    const entries: ZipEntry[] = [
      { path: "Retail.OrderHistory.1/Retail.OrderHistory.1.csv", bytes: csv([["Order ID", "Order Date", "Purchase Order Number", "Product Name", "Quantity", "Unit Price", "Currency", "Order Status"], ...orders]), dos: dos(3, 10) },
      { path: "Retail.CustomerReturns.1/Retail.CustomerReturns.1.csv", bytes: csv([["Order ID", "Return Date", "Reason", "Resolution"], [orders[4]![0]!, "2026-02-20T10:00:00Z", "Not as described", "Refund"]]), dos: dos(3, 10) },
      { path: "Digital.Orders.1/Digital Orders.csv", bytes: csv([["ASIN", "Title", "Order Date", "Price"], ["B000000001", "Tide tables 2026 (e-book)", "2026-01-05T12:00:00Z", "4.99"]]), dos: dos(3, 10) },
      { path: "Retail.OrderHistory.1/Invoices/Invoice-D01-0000001-0000001.pdf", bytes: typst(`#set page(width: 148mm, height: auto, margin: 10mm)\n#set text(size: 9pt)\n*Tax invoice* \\ Order D01-0000001-0000001 · 2026-01-14 \\ #table(columns: (1fr, auto), [Rope 8 mm], [18.00], [Shipping], [3.99], [*Total*], [*21.99*])`, "amazon-invoice"), dos: dos(3, 10) },
      { path: "Retail.OrderHistory.1/ProofOfDelivery/D01-0000001-0000001.jpg", bytes: png(20, 14, (x, y) => [200 - x * 5, 180 - y * 5, 120]), method: 0, dos: dos(3, 10) },
      { path: "readme.txt", bytes: e("Your data request. Each folder holds one category as CSV. Fictional delivery for the regression suite.\n"), dos: dos(3, 10) },
    ];
    out("orders-delivery.zip", zip(entries));
    void writeTestimony("orders-delivery.zip");
  },
  uber() {
    const r = lcg(202);
    const trips = Array.from({ length: 10 }, (_, i) => [`2026-0${1 + (i % 3)}-${String(2 + i * 2).padStart(2, "0")} ${String(7 + i).padStart(2, "0")}:${String(i * 5).padStart(2, "0")}:00 +0000 UTC`, "UberX", pick(r, ["completed", "completed", "canceled"]), (int(r, 20, 240) / 10).toFixed(1), int(r, 5, 40), (int(r, 500, 3000) / 100).toFixed(2), "GBP"]);
    const entries: ZipEntry[] = [
      { path: "Rider/trips_data.csv", bytes: csv([["Request Time", "Product Type", "Trip or Order Status", "Distance (miles)", "Duration (minutes)", "Fare Amount", "Fare Currency"], ...trips]), dos: dos(3, 12) },
      { path: "Rider/profile_data.csv", bytes: csv([["First Name", "Last Name", "Email", "Phone", "Signup Time"], ["Ada", "Abbott", "ada.abbott@example.invalid", "+44 7700 900123", "2019-05-01 10:00:00 +0000 UTC"]]), dos: dos(3, 12) },
      { path: "Rider/payment_methods.csv", bytes: csv([["Payment Method", "Last Four", "Added"], ["Card", "4242", "2019-05-01"]]), dos: dos(3, 12) },
      { path: "Eats/eats_order_details.csv", bytes: csv([["Order Time", "Restaurant", "Items", "Total", "Currency"], ["2026-02-11 19:12:00 +0000 UTC", "Quay Cafe", "2", "18.40", "GBP"]]), dos: dos(3, 12) },
      { path: "Rider/ratings_data.csv", bytes: csv([["Trip Time", "Rating Given", "Rating Received"], [trips[0]![0]!, 5, 5]]), dos: dos(3, 12) },
      { path: "README.txt", bytes: e("This archive holds the personal data you requested, one CSV per category.\nFictional export for the regression suite.\n"), dos: dos(3, 12) },
    ];
    out("rides-export.zip", zip(entries));
    void writeTestimony("rides-export.zip");
  },
  health() {
    const r = lcg(203);
    const records: string[] = [];
    let t = Date.UTC(2026, 2, 1, 6, 0, 0);
    for (let i = 0; i < 120; i++) {
      t += int(r, 600, 7200) * 1000;
      const d = new Date(t).toISOString().replace("T", " ").slice(0, 19);
      const kind = pick(r, [["HKQuantityTypeIdentifierStepCount", "count", int(r, 20, 900)], ["HKQuantityTypeIdentifierHeartRate", "count/min", int(r, 52, 140)], ["HKQuantityTypeIdentifierActiveEnergyBurned", "kcal", (int(r, 5, 400) / 10).toFixed(1)]]);
      records.push(`  <Record type="${kind[0]}" sourceName="Phone" sourceVersion="19.3" unit="${kind[1]}" creationDate="${d} +0000" startDate="${d} +0000" endDate="${d} +0000" value="${kind[2]}"/>`);
    }
    const exportXml = `<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE HealthData [\n<!ELEMENT HealthData (ExportDate,Me,(Record|Workout)*)>\n]>\n<HealthData locale="en_GB">\n <ExportDate value="2026-04-01 07:00:00 +0000"/>\n <Me HKCharacteristicTypeIdentifierDateOfBirth="1990-01-01" HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexNotSet"/>\n${records.join("\n")}\n <Workout workoutActivityType="HKWorkoutActivityTypeWalking" duration="30.2" durationUnit="min" startDate="2026-03-01 07:30:00 +0000" endDate="2026-03-01 08:00:12 +0000"><WorkoutRoute><FileReference path="/workout-routes/route_2026-03-01_7.30am.gpx"/></WorkoutRoute></Workout>\n</HealthData>\n`;
    const gpx = (seed: number) => {
      const rr = lcg(seed);
      let lat = 55.627;
      let lon = -6.19;
      const pts = Array.from({ length: 60 }, (_, i) => {
        lat += (rr() - 0.5) * 0.0004;
        lon += (rr() - 0.5) * 0.0006;
        return `   <trkpt lat="${lat.toFixed(6)}" lon="${lon.toFixed(6)}"><ele>${(4 + rr() * 3).toFixed(1)}</ele><time>${new Date(Date.UTC(2026, 2, 1, 7, 30, i * 30)).toISOString()}</time></trkpt>`;
      });
      return e(`<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="Health" xmlns="http://www.topografix.com/GPX/1/1">\n <trk><name>Route 2026-03-01 7:30am</name><trkseg>\n${pts.join("\n")}\n </trkseg></trk>\n</gpx>\n`);
    };
    const ecg = e(`Name,Ada Abbott\nDate of Birth,1990-01-01\nRecorded Date,2026-03-04 21:10:00 +0000\nClassification,Sinus Rhythm\nSymptoms,None\nSoftware Version,2.0\nDevice,Watch\nSample Rate,512 hertz\nLead,Lead I\nUnit,µV\n\n${Array.from({ length: 300 }, (_, i) => (Math.sin(i / 9) * 400).toFixed(3)).join("\n")}\n`);
    const entries: ZipEntry[] = [
      { path: "apple_health_export/export.xml", bytes: e(exportXml), dos: dos(4, 1) },
      { path: "apple_health_export/export_cda.xml", bytes: e(`<?xml version="1.0" encoding="UTF-8"?>\n<ClinicalDocument xmlns="urn:hl7-org:v3"><title>Health Data Export</title><recordTarget><patientRole><patient><name><given>Ada</given><family>Abbott</family></name></patient></patientRole></recordTarget></ClinicalDocument>\n`), dos: dos(4, 1) },
      { path: "apple_health_export/electrocardiograms/ecg_2026-03-04.csv", bytes: ecg, dos: dos(4, 1) },
      { path: "apple_health_export/workout-routes/route_2026-03-01_7.30am.gpx", bytes: gpx(1), dos: dos(4, 1) },
      { path: "apple_health_export/workout-routes/route_2026-03-08_6.55pm.gpx", bytes: gpx(2), dos: dos(4, 1) },
      { path: "apple_health_export/clinical-records/Immunization-00000000-0000-4000-8000-00000000c0de.json", bytes: e(`${JSON.stringify({ resourceType: "Immunization", id: "00000000-0000-4000-8000-00000000c0de", status: "completed", vaccineCode: { text: "Seasonal influenza" }, occurrenceDateTime: "2025-10-12" }, null, 2)}\n`), dos: dos(4, 1) },
    ];
    out("health-export.zip", zip(entries));
    void writeTestimony("health-export.zip");
  },
  unraid() {
    const r = lcg(204);
    const host = "lantern";
    const d = `${host}-diagnostics-20260312-0915`;
    const smart = (dev: string, serial: string) => `smartctl 7.4 2023-08-01 r5530 [x86_64-linux-6.6.0] (local build)\n=== START OF INFORMATION SECTION ===\nDevice Model:     EXAMPLE DISK 4TB\nSerial Number:    ${serial}\nUser Capacity:    4,000,787,030,016 bytes [4.00 TB]\nSMART overall-health self-assessment test result: PASSED\nID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE\n  5 Reallocated_Sector_Ct   0x0033   100   100   010    Pre-fail  Always       -       0\n  9 Power_On_Hours          0x0032   ${100 - int(r, 1, 40)}   ${100 - int(r, 1, 40)}   000    Old_age   Always       -       ${int(r, 1000, 30000)}\n194 Temperature_Celsius     0x0022   0${int(r, 30, 45)}   040   000    Old_age   Always       -       ${int(r, 30, 45)}\n`;
    const entries: ZipEntry[] = [];
    for (const [dev, serial] of [["sda", "SN0000000001"], ["sdb", "SN0000000002"], ["sdc", "SN0000000003"]]) entries.push({ path: `${d}/smart/${dev}-EXAMPLE_DISK_4TB-${serial}.txt`, bytes: e(smart(dev!, serial!)), dos: dos(3, 12) });
    for (const [n, body] of [["df.txt", "Filesystem      Size  Used Avail Use% Mounted on\n/dev/md1        3.7T  2.1T  1.6T  57% /mnt/disk1\n/dev/md2        3.7T  3.0T  700G  82% /mnt/disk2\n"], ["memory.txt", "              total        used        free\nMem:           32Gi        11Gi        21Gi\n"], ["lsscsi.txt", "[0:0:0:0]    disk    ATA      EXAMPLE DISK 4TB  0001  /dev/sda\n[1:0:0:0]    disk    ATA      EXAMPLE DISK 4TB  0001  /dev/sdb\n"], ["vars.txt", "NAME=\"lantern\"\nVERSION=\"7.0.0\"\nmdNumDisks=\"3\"\n"], ["docker.txt", "CONTAINER ID   IMAGE                   STATUS\n0000000c0de1   example/caddy:2         Up 12 days\n"], ["ethtool.txt", "Settings for eth0:\n\tSpeed: 1000Mb/s\n\tLink detected: yes\n"]])
      entries.push({ path: `${d}/system/${n}`, bytes: e(body!), dos: dos(3, 12) });
    for (const [n, body] of [["ident.cfg", `NAME="lantern"\ntimeZone="Europe/London"\nUSE_SSL="yes"\n`], ["disk.cfg", `startArray="yes"\nspindownDelay="30"\n`], ["network.cfg", `USE_DHCP="no"\nIPADDR="192.0.2.10"\nGATEWAY="192.0.2.1"\n`], ["share.cfg", `shareUser="e"\nshareUserInclude=""\n`], ["pools/cache.cfg", `diskFsType="btrfs"\n`]])
      entries.push({ path: `${d}/config/${n}`, bytes: e(body!), dos: dos(3, 12) });
    for (const s of ["media", "backups", "appdata"]) entries.push({ path: `${d}/shares/${s}.cfg`, bytes: e(`shareComment="${s}"\nshareInclude=""\nshareUseCache="${s === "appdata" ? "prefer" : "yes"}"\n`), dos: dos(3, 12) });
    entries.push({ path: `${d}/logs/syslog.txt`, bytes: e(Array.from({ length: 80 }, (_, i) => `Mar 12 0${i % 9}:${String(i % 60).padStart(2, "0")}:00 lantern kernel: ${pick(r, ["md: sync done", "eth0: link up", "emhttpd: shcmd (1): /etc/rc.d/rc.docker start", "nginx: worker started"])}`).join("\n")), dos: dos(3, 12) });
    entries.push({ path: `${d}/${host}-diagnostics.txt`, bytes: e("Diagnostics generated 2026-03-12 09:15 by a fictional homelab host for the regression suite.\n"), dos: dos(3, 12) });
    out("host-diagnostics.zip", zip(entries));
    void writeTestimony("host-diagnostics.zip");
  },
  obsidian() {
    const r = lcg(205);
    const note = (title: string, tags: string[], body: string, links: string[] = []) => e(`---\ntitle: ${title}\ntags: [${tags.join(", ")}]\ncreated: 2026-0${1 + int(r, 0, 2)}-${String(int(r, 1, 28)).padStart(2, "0")}\n---\n\n# ${title}\n\n${body}\n${links.map((l) => `\n- [[${l}]]`).join("")}\n`);
    const entries: ZipEntry[] = [
      { path: "Harbour/.obsidian/app.json", bytes: e('{"readableLineLength":true,"strictLineBreaks":false}\n'), dos: dos(3, 14) },
      { path: "Harbour/.obsidian/workspace.json", bytes: e('{"main":{"id":"root","type":"split"},"active":"notes/Tide tables.md"}\n'), dos: dos(3, 14) },
      { path: "Harbour/notes/Tide tables.md", bytes: note("Tide tables", ["harbour", "reference"], paragraph(r), ["Port Ellen", "Mooring plan"]), dos: dos(3, 14) },
      { path: "Harbour/notes/Mooring plan.md", bytes: note("Mooring plan", ["harbour"], paragraph(r), ["Tide tables"]), dos: dos(3, 14) },
      { path: "Harbour/places/Port Ellen.md", bytes: note("Port Ellen", ["place"], paragraph(r)), dos: dos(3, 14) },
      { path: "Harbour/people/Bo Calder.md", bytes: note("Bo Calder", ["person"], sentence(r)), dos: dos(3, 14) },
      { path: "Harbour/books/The Lantern Room.md", bytes: note("The Lantern Room", ["book", "read"], paragraph(r)), dos: dos(3, 14) },
      { path: "Harbour/logs/2026-03-14.md", bytes: e(`# 2026-03-14\n\n- 07:10 ${sentence(r)}\n- 12:40 ${sentence(r)}\n- 18:05 ${sentence(r)}\n`), dos: dos(3, 14) },
      { path: "Harbour/attachments/quay-sketch.png", bytes: png(40, 24, (x, y) => [240 - x * 3, 240 - y * 4, 230]), method: 0, dos: dos(3, 14) },
      { path: "Harbour/clippings/Harbour notice.md", bytes: e(`---\nsource: https://example.invalid/notices/2026-03\nclipped: 2026-03-14\n---\n\n${paragraph(r)}\n`), dos: dos(3, 14) },
    ];
    out("vault-subtree.zip", zip(entries));
    void writeTestimony("vault-subtree.zip");
  },
  vendor() {
    const r = lcg(206);
    const datasheet = (model: string, i: number) => typst(`#set page(paper: "a4", margin: 2cm)\n#set text(size: 10pt)\n= ${model} datasheet\n\nA fictional single-board controller. Revision ${i}.${int(r, 0, 9)}.\n\n#table(columns: (auto, 1fr), [*Supply*], [12 V DC], [*Interfaces*], [2 × UART, 1 × CAN, 1 × Ethernet], [*Temperature*], [-20 to 70 °C])\n\n== Pinout\n\n${sentence(r)}\n`, `datasheet-${i}`);
    const dxf = e(`0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1015\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n0\nLINE\n8\n0\n10\n0.0\n20\n0.0\n11\n120.0\n21\n0.0\n0\nLINE\n8\n0\n10\n120.0\n20\n0.0\n11\n120.0\n21\n80.0\n0\nCIRCLE\n8\n0\n10\n60.0\n20\n40.0\n40\n12.5\n0\nENDSEC\n0\nEOF\n`);
    const stub = (magic: number[], size: number) => {
      const b = new Uint8Array(size);
      b.set(magic);
      for (let i = magic.length; i < size; i++) b[i] = (i * 31) & 255;
      return b;
    };
    const inner = zip([{ path: "firmware/README.txt", bytes: e("Fictional firmware bundle. No executable content.\n") }, { path: "firmware/image.bin", bytes: stub([0x7f, 0x45, 0x4c, 0x46], 256) }]);
    const entries: ZipEntry[] = [
      { path: "Datasheet/HL-K7S_Datasheet_V1.2.pdf", bytes: datasheet("HL-K7S", 1), dos: dos(2, 2) },
      { path: "Datasheet/HL-K10B_Datasheet_V2.0.pdf", bytes: datasheet("HL-K10B", 2), dos: dos(2, 2) },
      { path: "K7S/Mechanical_Drawing/HL-K7S_outline.dxf", bytes: dxf, dos: dos(2, 2) },
      { path: "K7S/Schematic_Diagram/HL-K7S_Schematic_V1.2.pdf", bytes: datasheet("HL-K7S schematic", 3), dos: dos(2, 2) },
      { path: "K7S/Firmware/HL-K7S_Firmware_V1.2.zip", bytes: inner, method: 0, dos: dos(2, 2) },
      { path: "Tools/flash-tool.rar", bytes: stub([0x52, 0x61, 0x72, 0x21, 0x1a, 0x07, 0x01, 0x00], 512), method: 0, dos: dos(2, 2) },
      { path: "Tools/driver.7z", bytes: stub([0x37, 0x7a, 0xbc, 0xaf, 0x27, 0x1c], 512), method: 0, dos: dos(2, 2) },
      { path: "Tools/setup.exe", bytes: stub([0x4d, 0x5a, 0x90, 0x00], 1024), method: 0, dos: dos(2, 2) },
      { path: "Readme.txt", bytes: e("Download share of a fictional vendor, assembled for the regression suite.\n"), dos: dos(2, 2) },
    ];
    out("vendor-share.zip", zip(entries));
    void writeTestimony("vendor-share.zip");
  },
  claude() {
    const r = lcg(207);
    const sid = "00000000-0000-4000-8000-00000000c0de";
    const line = (type: string, i: number, extra: Record<string, unknown>) => JSON.stringify({ parentUuid: i ? `u-${i - 1}` : null, uuid: `u-${i}`, sessionId: sid, timestamp: new Date(Date.UTC(2026, 2, 20, 10, 0, i * 7)).toISOString(), type, cwd: "/home/owner/work/harbour", version: "2.1.0", ...extra });
    const transcript: string[] = [];
    for (let i = 0; i < 40; i++) {
      if (i % 2 === 0) transcript.push(line("user", i, { message: { role: "user", content: sentence(r) } }));
      else transcript.push(line("assistant", i, { message: { role: "assistant", content: [{ type: "text", text: sentence(r) }, ...(i % 6 === 1 ? [{ type: "tool_use", id: `toolu_${i}`, name: "Read", input: { file_path: "/home/owner/work/harbour/notes.md" } }] : [])] } }));
    }
    const entries: ZipEntry[] = [
      { path: `${sid}.jsonl`, bytes: e(`${transcript.join("\n")}\n`), method: 93, dos: dos(3, 20) },
      { path: `${sid}/subagents/agent-a1b2c3.jsonl`, bytes: e(`${Array.from({ length: 6 }, (_, i) => line(i % 2 ? "assistant" : "user", 100 + i, { agentId: "a1b2c3", message: { role: i % 2 ? "assistant" : "user", content: sentence(r) } })).join("\n")}\n`), method: 93, dos: dos(3, 20) },
      { path: `${sid}/tool-results/toolu_1.json`, bytes: e(`${JSON.stringify({ tool_use_id: "toolu_1", content: paragraph(r) }, null, 2)}\n`), method: 93, dos: dos(3, 20) },
      { path: `${sid}/tool-results/toolu_7.json`, bytes: e(`${JSON.stringify({ tool_use_id: "toolu_7", content: paragraph(r) }, null, 2)}\n`), method: 93, dos: dos(3, 20) },
      { path: `${sid}/workflow-state.json`, bytes: e(`${JSON.stringify({ phase: "done", steps: 3 }, null, 2)}\n`), method: 93, dos: dos(3, 20) },
    ];
    out("agent-session.zip", zip(entries));
    void writeTestimony("agent-session.zip");
  },
  bank() {
    const r = lcg(208);
    const entries: ZipEntry[] = [];
    for (let m = 1; m <= 12; m++) entries.push({ path: `2025/Statement-2025-${String(m).padStart(2, "0")}.pdf`, bytes: statementPdf(r, m, "Ada Abbott", "00-00-00 12345678"), dos: dos(1, 15) });
    out("statements-year.zip", zip(entries));
    void writeTestimony("statements-year.zip");
  },
  camera() {
    rmSync(TMP, { recursive: true, force: true });
    mkdirSync(TMP, { recursive: true });
    const r = lcg(209);
    /** A minimal TIFF-shaped raw: little-endian header, one IFD with Make/Model/ImageWidth/Length and a strip of bytes. */
    const arw = (i: number) => {
      const w = 16;
      const h = 12;
      const strip = new Uint8Array(w * h * 2);
      for (let k = 0; k < strip.length; k++) strip[k] = (k * 7 + i * 13) & 255;
      const make = "SONY\0";
      const model = "ILCE-7CM2\0";
      const entriesN = 7;
      const ifdOff = 8;
      const ifdLen = 2 + entriesN * 12 + 4;
      const makeOff = ifdOff + ifdLen;
      const modelOff = makeOff + make.length;
      const stripOff = modelOff + model.length + ((modelOff + model.length) % 2);
      const b = new Uint8Array(stripOff + strip.length);
      const dv = new DataView(b.buffer);
      b.set([0x49, 0x49, 0x2a, 0x00]);
      dv.setUint32(4, ifdOff, true);
      dv.setUint16(ifdOff, entriesN, true);
      const ent = (n: number, tag: number, type: number, count: number, value: number) => {
        const p = ifdOff + 2 + n * 12;
        dv.setUint16(p, tag, true);
        dv.setUint16(p + 2, type, true);
        dv.setUint32(p + 4, count, true);
        if (type === 3 && count === 1) dv.setUint16(p + 8, value, true);
        else dv.setUint32(p + 8, value, true);
      };
      ent(0, 0x0100, 4, 1, w);
      ent(1, 0x0101, 4, 1, h);
      ent(2, 0x0102, 3, 1, 16);
      ent(3, 0x010f, 2, make.length, makeOff);
      ent(4, 0x0110, 2, model.length, modelOff);
      ent(5, 0x0111, 4, 1, stripOff);
      ent(6, 0x0117, 4, 1, strip.length);
      dv.setUint32(ifdOff + 2 + entriesN * 12, 0, true);
      b.set(new TextEncoder().encode(make), makeOff);
      b.set(new TextEncoder().encode(model), modelOff);
      b.set(strip, stripOff);
      return b;
    };
    const entries: ZipEntry[] = [];
    for (let i = 1; i <= 3; i++) {
      const src = join(TMP, `c${i}.png`);
      writeFileSync(src, png(24, 16, (x, y) => [(x * 10 + i * 60) & 255, (y * 12) & 255, 90]));
      const hif = join(TMP, `DSC0000${i}.HIF`);
      run(["heif-enc", "-q", "55", "-o", hif, src]);
      entries.push({ path: `DCIM/10051104/DSC0000${i}.ARW`, bytes: arw(i), method: 0, dos: dos(3, 2) });
      entries.push({ path: `DCIM/10051104/DSC0000${i}.HIF`, bytes: new Uint8Array(readFileSync(hif)), method: 0, dos: dos(3, 2) });
    }
    const mp4 = join(TMP, "C0001.MP4");
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=160x90:rate=25", "-f", "lavfi", "-i", "sine=frequency=220:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", mp4]);
    entries.push({ path: "PRIVATE/M4ROOT/CLIP/C0001.MP4", bytes: new Uint8Array(readFileSync(mp4)), method: 0, dos: dos(3, 2) });
    entries.push({ path: "PRIVATE/M4ROOT/CLIP/C0001M01.XML", bytes: e(`<?xml version="1.0" encoding="UTF-8"?>\n<NonRealTimeMeta xmlns="urn:schemas-professionalDisc:nonRealTimeMeta:ver.2.20" lastUpdate="2026-03-02T10:14:00Z"><TargetMaterial umidRef="060A2B340101010501010D4313000000"/><Duration value="25"/><CreationDate value="2026-03-02T10:14:00Z"/><Device manufacturer="Sony" modelName="ILCE-7CM2" serialNo="0000000"/><VideoFormat><VideoFrame videoCodec="AVC_3840_2160_HP@L51" captureFps="25p"/></VideoFormat></NonRealTimeMeta>\n`), dos: dos(3, 2) });
    entries.push({ path: "PRIVATE/M4ROOT/MEDIAPRO.XML", bytes: e(`<?xml version="1.0" encoding="UTF-8"?>\n<MediaProfile xmlns="http://xmlns.sony.net/pro/metadata/mediaprofile" version="1.00"><Contents><Material uri="./CLIP/C0001.MP4" type="MP4"/></Contents></MediaProfile>\n`), dos: dos(3, 2) });
    out("card-dump.zip", zip(entries));
    void writeTestimony("card-dump.zip");
    rmSync(TMP, { recursive: true, force: true });
  },
  takeout() {
    const r = lcg(210);
    const tcx = (i: number) => e(`<?xml version="1.0" encoding="UTF-8"?>\n<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"><Activities><Activity Sport="Walking"><Id>2026-03-0${i}T07:30:00.000Z</Id><Lap StartTime="2026-03-0${i}T07:30:00.000Z"><TotalTimeSeconds>1812.0</TotalTimeSeconds><DistanceMeters>${int(r, 1500, 3200)}</DistanceMeters><Calories>${int(r, 80, 200)}</Calories><Track>${Array.from({ length: 10 }, (_, k) => `<Trackpoint><Time>2026-03-0${i}T07:${30 + k}:00.000Z</Time><Position><LatitudeDegrees>55.62${k}</LatitudeDegrees><LongitudeDegrees>-6.19${k}</LongitudeDegrees></Position></Trackpoint>`).join("")}</Track></Lap></Activity></Activities></TrainingCenterDatabase>\n`);
    const entries: ZipEntry[] = [
      { path: "Takeout/archive_browser.html", bytes: e("<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>Archive browser</title></head><body><h1>Your archive</h1><ul><li>Fit</li><li>Contacts</li><li>Maps</li><li>Keep</li><li>Calendar</li></ul></body></html>\n"), dos: dos(4, 1) },
      { path: "Takeout/Fit/Activities/2026-03-01T07_30_00+00_00_PT30M12.0S_Walking.tcx", bytes: tcx(1), dos: dos(4, 1) },
      { path: "Takeout/Fit/Activities/2026-03-02T07_30_00+00_00_PT29M48.0S_Walking.tcx", bytes: tcx(2), dos: dos(4, 1) },
      { path: "Takeout/Fit/Daily activity metrics/2026-03-01.csv", bytes: csv([["Start time", "End time", "Step count", "Distance (m)"], ["07:00:00.000", "08:00:00.000", 2100, 1600], ["08:00:00.000", "09:00:00.000", 300, 220]]), dos: dos(4, 1) },
      { path: "Takeout/Contacts/All Contacts/All Contacts.vcf", bytes: e(`BEGIN:VCARD\r\nVERSION:3.0\r\nN:Calder;Bo;;;\r\nFN:Bo Calder\r\nEMAIL;TYPE=INTERNET:bo.calder@example.invalid\r\nEND:VCARD\r\nBEGIN:VCARD\r\nVERSION:3.0\r\nN:Thorn;Ida;;;\r\nFN:Ida Thorn\r\nEND:VCARD\r\n`), dos: dos(4, 1) },
      { path: "Takeout/Maps/My labelled places/Labelled places.json", bytes: e(`${JSON.stringify({ type: "FeatureCollection", features: [{ type: "Feature", geometry: { type: "Point", coordinates: [-6.19, 55.627] }, properties: { name: "Harbour", address: "Quay Street, Port Ellen" } }] }, null, 2)}\n`), dos: dos(4, 1) },
      { path: "Takeout/Keep/Mooring checklist.json", bytes: e(`${JSON.stringify({ color: "DEFAULT", isTrashed: false, isPinned: true, isArchived: false, listContent: [{ text: "Check lines", isChecked: true }, { text: "Fenders", isChecked: false }], title: "Mooring checklist", userEditedTimestampUsec: 1774000000000000, createdTimestampUsec: 1773000000000000 }, null, 2)}\n`), dos: dos(4, 1) },
      { path: "Takeout/Keep/Mooring checklist.html", bytes: e("<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>Mooring checklist</title></head><body><div class=\"note\"><div class=\"heading\">2026-03-01</div><div class=\"title\">Mooring checklist</div><div class=\"content\"><ul class=\"list\"><li class=\"listitem checked\">Check lines</li><li class=\"listitem\">Fenders</li></ul></div></div></body></html>\n"), dos: dos(4, 1) },
      { path: "Takeout/Calendar/Harbour.ics", bytes: e(`BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Example//Calendar//EN\r\nBEGIN:VEVENT\r\nUID:00000000-0000-4000-8000-00000000c0de\r\nDTSTAMP:20260301T070000Z\r\nDTSTART:20260523T080000Z\r\nDTEND:20260523T180000Z\r\nSUMMARY:Regatta volunteers briefing\r\nLOCATION:Harbour office\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n`), dos: dos(4, 1) },
      { path: "Takeout/Saved/Favourite places.csv", bytes: csv([["Title", "Note", "URL"], ["Harbour", "", "https://maps.example.invalid/?cid=1"]]), dos: dos(4, 1) },
    ];
    out("takeout-slice.zip", zip(entries));
    void writeTestimony("takeout-slice.zip");
  },
  drive() {
    const r = lcg(211);
    const entries: ZipEntry[] = [
      { path: "Harbour plans/Mooring plan 2026.pdf", bytes: typst(`#set page(paper: "a4", margin: 2cm)\n= Mooring plan 2026\n\n${paragraph(r)}\n\n#table(columns: (auto, 1fr, auto), [*Berth*], [*Vessel*], [*Length*], [A1], [Lantern], [8.2 m], [A2], [Gull], [6.5 m])`, "drive-plan"), dos: dos(3, 18) },
      { path: "Harbour plans/Berth list.csv", bytes: csv([["Berth", "Vessel", "Length (m)"], ["A1", "Lantern", 8.2], ["A2", "Gull", 6.5]]), dos: dos(3, 18) },
      { path: "Harbour plans/Notes.md", bytes: e(`# Notes\n\n${paragraph(r)}\n`), dos: dos(3, 18) },
      { path: "Harbour plans/Quay photo.png", bytes: png(32, 20, (x, y) => [x * 7, 120, y * 10]), method: 0, dos: dos(3, 18) },
    ];
    out("drive-folder.zip", zip(entries));
    void writeTestimony("drive-folder.zip");
  },
  profile() {
    const r = lcg(212);
    const posts = Array.from({ length: 6 }, (_, i) => ({ timestamp: 1774000000 + i * 86400 * 9, data: [{ post: sentence(r) }], title: "Bo Calder", attachments: i % 2 ? [{ data: [{ media: { uri: `your_facebook_activity/posts/media/your_posts/${i}.jpg`, creation_timestamp: 1774000000 + i * 86400 * 9 } }] }] : [] }));
    const entries: ZipEntry[] = [
      { path: "your_facebook_activity/posts/your_posts_1.json", bytes: e(`${JSON.stringify(posts, null, 2)}\n`), dos: dos(4, 2) },
      { path: "your_facebook_activity/comments_and_reactions/comments.json", bytes: e(`${JSON.stringify({ comments_v2: Array.from({ length: 5 }, (_, i) => ({ timestamp: 1774000000 + i * 50000, data: [{ comment: { comment: sentence(r), author: "Bo Calder" } }], title: "Bo Calder commented on a post." })) }, null, 2)}\n`), dos: dos(4, 2) },
      ...posts.flatMap((p) => p.attachments.map((a) => ({ path: a.data[0]!.media.uri, bytes: png(14, 14, (x, y) => [x * 18, y * 18, 160]), method: 0 as const, dos: dos(4, 2) }))),
      { path: "your_facebook_activity/posts/media/videos/0.mp4", bytes: new Uint8Array(readFileSync(join(SYN, "countdown.mp4"))), method: 0, dos: dos(4, 2) },
    ];
    out("profile-year.zip", zip(entries));
    void writeTestimony("profile-year.zip");
  },
};
const only = process.argv.includes("--only") ? process.argv[process.argv.indexOf("--only") + 1]!.split(",") : Object.keys(gens);
for (const k of only) {
  const g = gens[k];
  if (!g) throw new Error(`no generator '${k}'`);
  g();
}
