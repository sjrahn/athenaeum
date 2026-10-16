#!/usr/bin/env bun
// odds.ts — the twins of the reference archives and the odd containers, as minimal files that carry the signature the
// sniffer reads and the first structures a reader meets: a ZIM archive header, an OSM PBF file (one OSMHeader blob),
// a FreeCAD document (a zip of Document.xml and GuiDocument.xml), a gzip file. Stubs by design: the suite proves
// they are told apart and attested, nothing more.
//
//   bun testdata/synthetic/gen/odds.ts
import { gzipSync } from "node:zlib";
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { zip } from "./lib/zip.ts";

const SYN = join(dirname(Bun.fileURLToPath(import.meta.url)), "..");
const e = (s: string) => new TextEncoder().encode(s);
const out = (name: string, bytes: Uint8Array) => {
  writeFileSync(join(SYN, name), bytes);
  console.log(`wrote ${name} (${bytes.length} bytes)`);
};

// ZIM: the 80-byte header (magic 0x044D495A, major 6, minor 1, a uuid, counts and offsets), then an empty MIME list
{
  const b = new Uint8Array(80 + 16);
  const dv = new DataView(b.buffer);
  dv.setUint32(0, 0x044d495a, true);
  dv.setUint16(4, 6, true);
  dv.setUint16(6, 1, true);
  b.set([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x40, 0x00, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0xc0, 0xde], 8); // uuid
  dv.setUint32(24, 0, true); // entry count
  dv.setUint32(28, 0, true); // cluster count
  dv.setBigUint64(32, 80n, true); // url pointer list
  dv.setBigUint64(40, 80n, true); // title pointer list
  dv.setBigUint64(48, 80n, true); // cluster pointer list
  dv.setBigUint64(56, 80n, true); // mime list
  dv.setUint32(64, 0xffffffff, true); // main page
  dv.setUint32(68, 0xffffffff, true); // layout page
  dv.setBigUint64(72, 96n, true); // checksum position
  b.set(e("text/html\0\0"), 80); // the mime list, terminated
  out("reference.zim", b);
}

// OSM PBF: a BlobHeader (type "OSMHeader") and its Blob holding a raw HeaderBlock with a bbox and the required features
{
  const varint = (n: number) => {
    const o: number[] = [];
    while (n >= 0x80) {
      o.push((n & 0x7f) | 0x80);
      n >>>= 7;
    }
    o.push(n);
    return o;
  };
  const field = (num: number, wire: number, payload: number[]) => [...varint((num << 3) | wire), ...(wire === 2 ? varint(payload.length) : []), ...payload];
  const str = (num: number, s: string) => field(num, 2, [...e(s)]);
  const headerBlock = [
    ...field(1, 2, [...field(1, 0, varint(-6300000000 + 2 ** 64 - 2 ** 64)), ...field(2, 0, varint(-6100000000 >>> 0))]), // bbox (approximate, nanodegrees; fictional)
    ...str(4, "OsmSchema-V0.6"),
    ...str(4, "DenseNodes"),
    ...str(16, "twin 1.0"),
    ...str(17, "regression suite"),
  ];
  const blob = [...field(1, 2, headerBlock), ...field(2, 0, varint(headerBlock.length))]; // raw, raw_size
  const blobHeader = [...str(1, "OSMHeader"), ...field(3, 0, varint(blob.length))];
  const b = new Uint8Array(4 + blobHeader.length + blob.length);
  new DataView(b.buffer).setUint32(0, blobHeader.length);
  b.set(blobHeader, 4);
  b.set(blob, 4 + blobHeader.length);
  out("region.osm.pbf", b);
}

// FreeCAD document
out(
  "bracket.FCStd",
  zip([
    { path: "Document.xml", bytes: e(`<?xml version='1.0' encoding='utf-8'?>\n<Document SchemaVersion="4" ProgramVersion="1.0.0" FileVersion="1"><Properties Count="3"><Property name="Label" type="App::PropertyString"><String value="Bracket"/></Property><Property name="CreatedBy" type="App::PropertyString"><String value="Example"/></Property><Property name="Uid" type="App::PropertyUUID"><Uuid value="00000000-0000-4000-8000-00000000c0de"/></Property></Properties><Objects Count="1"><Object type="Part::Box" name="Box"/></Objects><ObjectData Count="1"><Object name="Box"><Properties Count="3"><Property name="Length" type="App::PropertyLength"><Float value="120"/></Property><Property name="Width" type="App::PropertyLength"><Float value="80"/></Property><Property name="Height" type="App::PropertyLength"><Float value="6"/></Property></Properties></Object></ObjectData></Document>\n`) },
    { path: "GuiDocument.xml", bytes: e(`<?xml version='1.0' encoding='utf-8'?>\n<Document SchemaVersion="1"><ViewProviderData Count="1"><ViewProvider name="Box" expanded="0"><Properties Count="1"><Property name="Visibility" type="App::PropertyBool"><Bool value="true"/></Property></Properties></ViewProvider></ViewProviderData></Document>\n`) },
  ]),
);

// gzip of a text
out("notes.txt.gz", new Uint8Array(gzipSync(e("Harbour notes, compressed.\nFictional text for the regression suite.\n"), { level: 6 })));
