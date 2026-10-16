// zip.ts — a deterministic zip writer for the twins: fixed DOS timestamps, store (0), deflate (8) or zstd (93, what
// Discord's exporter writes), UTF-8 names, no zip64. The engine's reader (ath/src/engine/ops/zip/roster.ts) is the
// other half; this writer never lives in the engine.
import { deflateRawSync } from "node:zlib";

export interface ZipEntry {
  path: string;
  bytes: Uint8Array;
  method?: 0 | 8 | 93;
  /** DOS date/time, defaults to 2026-03-12 10:15:00. */
  dos?: { date: number; time: number };
}

const CRC = new Uint32Array(256).map((_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
export function crc32(b: Uint8Array): number {
  let c = 0xffffffff;
  for (let i = 0; i < b.length; i++) c = CRC[(c ^ b[i]!) & 0xff]! ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

export const dosStamp = (y: number, mo: number, d: number, h: number, mi: number, s: number) => ({
  date: ((y - 1980) << 9) | (mo << 5) | d,
  time: (h << 11) | (mi << 5) | (s >> 1),
});
const DEFAULT_DOS = dosStamp(2026, 3, 12, 10, 15, 0);

export function zip(entries: ZipEntry[]): Uint8Array {
  const enc = new TextEncoder();
  const locals: Uint8Array[] = [];
  const centrals: Uint8Array[] = [];
  let offset = 0;
  for (const e of entries) {
    const method = e.method ?? 8;
    const data = method === 0 ? e.bytes : method === 8 ? new Uint8Array(deflateRawSync(e.bytes)) : new Uint8Array(Bun.zstdCompressSync(e.bytes));
    const name = enc.encode(e.path);
    const crc = crc32(e.bytes);
    const dos = e.dos ?? DEFAULT_DOS;
    const local = new Uint8Array(30 + name.length + data.length);
    const lv = new DataView(local.buffer);
    lv.setUint32(0, 0x04034b50, true);
    lv.setUint16(4, method === 93 ? 63 : 20, true);
    lv.setUint16(6, 0x800, true); // UTF-8 names
    lv.setUint16(8, method, true);
    lv.setUint16(10, dos.time, true);
    lv.setUint16(12, dos.date, true);
    lv.setUint32(14, crc, true);
    lv.setUint32(18, data.length, true);
    lv.setUint32(22, e.bytes.length, true);
    lv.setUint16(26, name.length, true);
    lv.setUint16(28, 0, true);
    local.set(name, 30);
    local.set(data, 30 + name.length);
    locals.push(local);
    const central = new Uint8Array(46 + name.length);
    const cv = new DataView(central.buffer);
    cv.setUint32(0, 0x02014b50, true);
    cv.setUint16(4, 0x031e, true); // made by: unix, 3.0
    cv.setUint16(6, method === 93 ? 63 : 20, true);
    cv.setUint16(8, 0x800, true);
    cv.setUint16(10, method, true);
    cv.setUint16(12, dos.time, true);
    cv.setUint16(14, dos.date, true);
    cv.setUint32(16, crc, true);
    cv.setUint32(20, data.length, true);
    cv.setUint32(24, e.bytes.length, true);
    cv.setUint16(28, name.length, true);
    cv.setUint16(30, 0, true);
    cv.setUint16(32, 0, true);
    cv.setUint16(34, 0, true);
    cv.setUint16(36, 0, true);
    cv.setUint32(38, 0x81a40000, true); // -rw-r--r--
    cv.setUint32(42, offset, true);
    central.set(name, 46);
    centrals.push(central);
    offset += local.length;
  }
  const cdSize = centrals.reduce((n, c) => n + c.length, 0);
  const eocd = new Uint8Array(22);
  const ev = new DataView(eocd.buffer);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(8, entries.length, true);
  ev.setUint16(10, entries.length, true);
  ev.setUint32(12, cdSize, true);
  ev.setUint32(16, offset, true);
  const out = new Uint8Array(offset + cdSize + 22);
  let p = 0;
  for (const l of locals) {
    out.set(l, p);
    p += l.length;
  }
  for (const c of centrals) {
    out.set(c, p);
    p += c.length;
  }
  out.set(eocd, p);
  return out;
}
