// image.ts — what a raster is, from its own structures (spec §10.2): the stored pixel grid's width and height (PNG,
// JPEG, GIF, WebP, TIFF and its raw kin, HEIC and AVIF by their primary item, ICO by its largest image), and the
// format's embedded metadata as recorded — the EXIF tags (strings as written, rationals as `n/d`), the XMP packet,
// the ICC profile's size and description. No pixel is decoded; boxes on a raster are in the stored grid (§7.3.1).
import { inflateSync } from "node:zlib";
import type { IntrinsicsResult, J } from "../format.ts";
import { u16 as be16, u32 as be32, boxes, child, str4, top } from "../media/bmff.ts";

const latin1 = new TextDecoder("latin1");
const utf8 = new TextDecoder("utf-8");

// ── EXIF (a TIFF structure) ─────────────────────────────────────────────────────────────────────────────────────────

const TAGS: Record<number, string> = {
  270: "ImageDescription",
  271: "Make",
  272: "Model",
  274: "Orientation",
  282: "XResolution",
  283: "YResolution",
  296: "ResolutionUnit",
  305: "Software",
  306: "DateTime",
  315: "Artist",
  33432: "Copyright",
  33434: "ExposureTime",
  33437: "FNumber",
  34850: "ExposureProgram",
  34855: "ISOSpeedRatings",
  36867: "DateTimeOriginal",
  36868: "DateTimeDigitized",
  36880: "OffsetTime",
  36881: "OffsetTimeOriginal",
  36882: "OffsetTimeDigitized",
  37377: "ShutterSpeedValue",
  37378: "ApertureValue",
  37380: "ExposureBiasValue",
  37383: "MeteringMode",
  37385: "Flash",
  37386: "FocalLength",
  40962: "PixelXDimension",
  40963: "PixelYDimension",
  41987: "WhiteBalance",
  41989: "FocalLengthIn35mmFilm",
  42016: "ImageUniqueID",
  42035: "LensMake",
  42036: "LensModel",
};
const GPS_TAGS: Record<number, string> = {
  1: "GPSLatitudeRef",
  2: "GPSLatitude",
  3: "GPSLongitudeRef",
  4: "GPSLongitude",
  5: "GPSAltitudeRef",
  6: "GPSAltitude",
  7: "GPSTimeStamp",
  29: "GPSDateStamp",
};
const SIZES: Record<number, number> = { 1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8 };

interface Tiff {
  le: boolean;
  u16(p: number): number;
  u32(p: number): number;
}

function tiffAt(b: Uint8Array, t: number): Tiff | null {
  if (t + 8 > b.length) return null;
  const le = b[t] === 0x49 && b[t + 1] === 0x49;
  if (!le && !(b[t] === 0x4d && b[t + 1] === 0x4d)) return null;
  return {
    le,
    u16: (p) => (le ? b[t + p]! | (b[t + p + 1]! << 8) : (b[t + p]! << 8) | b[t + p + 1]!),
    u32: (p) =>
      le
        ? (b[t + p]! | (b[t + p + 1]! << 8) | (b[t + p + 2]! << 16) | (b[t + p + 3]! << 24)) >>> 0
        : ((b[t + p]! << 24) | (b[t + p + 1]! << 16) | (b[t + p + 2]! << 8) | b[t + p + 3]!) >>> 0,
  };
}

interface Ifd {
  tags: Map<number, { type: number; count: number; at: number }>;
  next: number;
}

function readIfd(b: Uint8Array, t: number, x: Tiff, off: number): Ifd | null {
  if (!off || t + off + 2 > b.length) return null;
  const n = x.u16(off);
  const tags = new Map<number, { type: number; count: number; at: number }>();
  for (let k = 0; k < n; k++) {
    const e = off + 2 + 12 * k;
    if (t + e + 12 > b.length) break;
    const type = x.u16(e + 2);
    const count = x.u32(e + 4);
    const size = (SIZES[type] ?? 0) * count;
    tags.set(x.u16(e), { type, count, at: size <= 4 ? e + 8 : x.u32(e + 8) });
  }
  const end = off + 2 + 12 * n;
  return { tags, next: t + end + 4 <= b.length ? x.u32(end) : 0 };
}

function tagValue(b: Uint8Array, t: number, x: Tiff, e: { type: number; count: number; at: number }): unknown {
  const { type, count, at } = e;
  if (t + at + (SIZES[type] ?? 0) * count > b.length) return undefined;
  if (type === 2)
    return latin1
      .decode(b.subarray(t + at, t + at + count))
      .replace(/\0+$/, "")
      .trimEnd();
  const vals: unknown[] = [];
  for (let i = 0; i < count && i < 64; i++) {
    if (type === 3) vals.push(x.u16(at + 2 * i));
    else if (type === 8) vals.push((x.u16(at + 2 * i) << 16) >> 16);
    else if (type === 4) vals.push(x.u32(at + 4 * i));
    else if (type === 9) vals.push(x.u32(at + 4 * i) | 0);
    else if (type === 5) vals.push(`${x.u32(at + 8 * i)}/${x.u32(at + 8 * i + 4)}`);
    else if (type === 10) vals.push(`${x.u32(at + 8 * i) | 0}/${x.u32(at + 8 * i + 4) | 0}`);
    else return undefined;
  }
  return vals.length === 1 ? vals[0] : vals;
}

/** The named EXIF tags of a TIFF structure at `t`: IFD0, its Exif IFD and its GPS IFD. */
export function exifAt(b: Uint8Array, t: number): J {
  const x = tiffAt(b, t);
  if (!x) return {};
  const out: J = {};
  const ifd0 = readIfd(b, t, x, x.u32(4));
  if (!ifd0) return out;
  const take = (ifd: Ifd, names: Record<number, string>) => {
    for (const [tag, e] of ifd.tags) {
      const name = names[tag];
      if (!name) continue;
      const v = tagValue(b, t, x, e);
      if (v !== undefined && v !== "") out[name] = v;
    }
  };
  take(ifd0, TAGS);
  for (const [tag, names] of [
    [0x8769, TAGS],
    [0x8825, GPS_TAGS],
  ] as const) {
    const e = ifd0.tags.get(tag);
    if (!e) continue;
    const sub = readIfd(b, t, x, tagValue(b, t, x, e) as number);
    if (sub) take(sub, names);
  }
  return out;
}

// ── ICC ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

/** An ICC profile's size and its description (`desc`: v2 text description, v4 multi-localised). */
export function iccOf(p: Uint8Array): J {
  const out: J = { size: p.length };
  if (p.length < 132) return out;
  const n = be32(p, 128);
  for (let i = 0; i < n && 132 + 12 * i + 12 <= p.length; i++) {
    const e = 132 + 12 * i;
    if (str4(p, e) !== "desc") continue;
    const off = be32(p, e + 4);
    const kind = str4(p, off);
    if (kind === "desc") out.description = latin1.decode(p.subarray(off + 12, off + 12 + be32(p, off + 8))).replace(/\0+$/, "");
    else if (kind === "mluc" && be32(p, off + 8) > 0) {
      const len = be32(p, off + 20);
      const at = be32(p, off + 24);
      const s = p.subarray(off + at, off + at + len);
      let t = "";
      for (let k = 0; k + 1 < s.length; k += 2) t += String.fromCharCode((s[k]! << 8) | s[k + 1]!);
      out.description = t.replace(/\0+$/, "");
    }
  }
  return out;
}

// ── formats ─────────────────────────────────────────────────────────────────────────────────────────────────────────

interface Raster {
  width?: number;
  height?: number;
  exif?: J;
  xmp?: string;
  icc?: J;
  more?: J;
}

const XMP_ID = "http://ns.adobe.com/xap/1.0/\0";

function jpeg(b: Uint8Array): Raster {
  const r: Raster = {};
  const icc: Uint8Array[] = [];
  let i = 2;
  while (i + 4 <= b.length) {
    if (b[i] !== 0xff) {
      i++;
      continue;
    }
    const marker = b[i + 1]!;
    if (marker === 0xd8 || (marker >= 0xd0 && marker <= 0xd7) || marker === 0x01 || marker === 0xff) {
      i += 2;
      continue;
    }
    if (marker === 0xda || marker === 0xd9) break;
    const len = be16(b, i + 2);
    const seg = b.subarray(i + 4, i + 2 + len);
    if (marker === 0xe1 && latin1.decode(seg.subarray(0, 6)) === "Exif\0\0") r.exif = exifAt(b, i + 10);
    else if (marker === 0xe1 && latin1.decode(seg.subarray(0, XMP_ID.length)) === XMP_ID) r.xmp = utf8.decode(seg.subarray(XMP_ID.length));
    else if (marker === 0xe2 && latin1.decode(seg.subarray(0, 12)) === "ICC_PROFILE\0") icc.push(seg.subarray(14));
    else if (marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc && r.width === undefined) {
      r.height = be16(b, i + 5);
      r.width = be16(b, i + 7);
    }
    i += 2 + len;
  }
  if (icc.length) r.icc = iccOf(Buffer.concat(icc));
  return r;
}

function png(b: Uint8Array): Raster {
  const r: Raster = { width: be32(b, 16), height: be32(b, 20) };
  for (let p = 8; p + 8 <= b.length; ) {
    const len = be32(b, p);
    const type = str4(b, p + 4);
    const data = b.subarray(p + 8, p + 8 + len);
    if (type === "eXIf") r.exif = exifAt(data, 0);
    else if (type === "iTXt" && latin1.decode(data.subarray(0, 17)) === "XML:com.adobe.xmp") {
      // keyword\0, compression flag, method, language\0, translated keyword\0, text
      let q = 18 + 2;
      q = data.indexOf(0, q) + 1;
      q = data.indexOf(0, q) + 1;
      r.xmp = utf8.decode(data[18] ? inflateSync(data.subarray(q)) : data.subarray(q));
    } else if (type === "iCCP") {
      const q = data.indexOf(0) + 2;
      try {
        r.icc = iccOf(new Uint8Array(inflateSync(data.subarray(q))));
      } catch {
        // an undecodable profile is not recorded
      }
    } else if (type === "IEND") break;
    p += 12 + len;
  }
  return r;
}

const gif = (b: Uint8Array): Raster => ({ width: b[6]! | (b[7]! << 8), height: b[8]! | (b[9]! << 8) });

function webp(b: Uint8Array): Raster {
  const r: Raster = {};
  const le24 = (p: number) => b[p]! | (b[p + 1]! << 8) | (b[p + 2]! << 16);
  for (let p = 12; p + 8 <= b.length; ) {
    const type = str4(b, p);
    const len = (b[p + 4]! | (b[p + 5]! << 8) | (b[p + 6]! << 16) | (b[p + 7]! << 24)) >>> 0;
    const d = p + 8;
    if (type === "VP8X") {
      r.width = le24(d + 4) + 1;
      r.height = le24(d + 7) + 1;
    } else if (type === "VP8 " && r.width === undefined) {
      r.width = (b[d + 6]! | (b[d + 7]! << 8)) & 0x3fff;
      r.height = (b[d + 8]! | (b[d + 9]! << 8)) & 0x3fff;
    } else if (type === "VP8L" && r.width === undefined) {
      const v = (b[d + 1]! | (b[d + 2]! << 8) | (b[d + 3]! << 16) | (b[d + 4]! << 24)) >>> 0;
      r.width = (v & 0x3fff) + 1;
      r.height = ((v >>> 14) & 0x3fff) + 1;
    } else if (type === "EXIF") r.exif = exifAt(b, latin1.decode(b.subarray(d, d + 6)) === "Exif\0\0" ? d + 6 : d);
    else if (type === "XMP ") r.xmp = utf8.decode(b.subarray(d, d + len));
    else if (type === "ICCP") r.icc = iccOf(b.subarray(d, d + len));
    p = d + len + (len & 1);
  }
  return r;
}

function tiff(b: Uint8Array): Raster {
  const x = tiffAt(b, 0);
  if (!x) return {};
  const ifd = readIfd(b, 0, x, x.u32(4));
  if (!ifd) return {};
  const v = (tag: number) => {
    const e = ifd.tags.get(tag);
    return e ? tagValue(b, 0, x, e) : undefined;
  };
  const r: Raster = { exif: exifAt(b, 0) };
  const w = v(256);
  const h = v(257);
  if (typeof w === "number") r.width = w;
  if (typeof h === "number") r.height = h;
  const xmp = ifd.tags.get(700);
  if (xmp) r.xmp = utf8.decode(b.subarray(xmp.at, xmp.at + xmp.count));
  const icc = ifd.tags.get(34675);
  if (icc) r.icc = iccOf(b.subarray(icc.at, icc.at + icc.count));
  return r;
}

/** HEIC and AVIF: the primary item's spatial extent (`ispe`) and rotation (`irot`), through `pitm` and `ipma`. */
function heif(b: Uint8Array): Raster {
  const meta = top(b, "meta");
  if (!meta) return {};
  const pitm = child(b, meta, "pitm", 4);
  const primary = pitm ? (b[pitm.body] === 0 ? be16(b, pitm.body + 4) : be32(b, pitm.body + 4)) : 1;
  const iprp = child(b, meta, "iprp", 4);
  const ipco = child(b, iprp, "ipco");
  const ipma = child(b, iprp, "ipma");
  if (!ipco || !ipma) return {};
  const props = boxes(b, ipco.body, ipco.end);
  const v = b[ipma.body]!;
  const flags = b[ipma.body + 3]!;
  let p = ipma.body + 4;
  const n = be32(b, p);
  p += 4;
  const r: Raster = {};
  for (let i = 0; i < n; i++) {
    const item = v < 1 ? be16(b, p) : be32(b, p);
    p += v < 1 ? 2 : 4;
    const count = b[p++]!;
    for (let k = 0; k < count; k++) {
      const idx = flags & 1 ? be16(b, p) & 0x7fff : b[p]! & 0x7f;
      p += flags & 1 ? 2 : 1;
      if (item !== primary || !idx) continue;
      const prop = props[idx - 1];
      if (prop?.type === "ispe") {
        r.width = be32(b, prop.body + 4);
        r.height = be32(b, prop.body + 8);
      } else if (prop?.type === "irot") r.more = { ...r.more, rotation: (b[prop.body]! & 3) * 90 };
    }
  }
  return r;
}

function ico(b: Uint8Array): Raster {
  const n = b[4]! | (b[5]! << 8);
  const images: J[] = [];
  for (let i = 0; i < n; i++) {
    const e = 6 + 16 * i;
    if (e + 16 > b.length) break;
    images.push({ width: b[e] || 256, height: b[e + 1] || 256, bits: b[e + 6]! | (b[e + 7]! << 8) });
  }
  const big = images.reduce<J | undefined>(
    (m, x) => (!m || (x.width as number) * (x.height as number) > (m.width as number) * (m.height as number) ? x : m),
    undefined,
  );
  return { width: big?.width as number | undefined, height: big?.height as number | undefined, more: { images } };
}

export function rasterIntrinsics(b: Uint8Array, mime: string): IntrinsicsResult {
  const r: Raster =
    mime === "image/jpeg"
      ? jpeg(b)
      : mime === "image/png"
        ? png(b)
        : mime === "image/gif"
          ? gif(b)
          : mime === "image/webp"
            ? webp(b)
            : mime === "image/heic" || mime === "image/avif"
              ? heif(b)
              : mime === "image/x-icon"
                ? ico(b)
                : tiff(b);
  const facts: J = {};
  if (r.width !== undefined) facts.width = r.width;
  if (r.height !== undefined) facts.height = r.height;
  Object.assign(facts, r.more ?? {});
  if (r.exif && Object.keys(r.exif).length) facts.exif = r.exif;
  if (r.xmp) facts.xmp = r.xmp;
  if (r.icc) facts.icc = r.icc;
  return { facts };
}
