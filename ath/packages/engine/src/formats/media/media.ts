// media.ts — what a recording is, from its own structures (spec §10.2, §10.3): an ISO base media file (MP4,
// QuickTime, 3GPP, M4A) gives its duration and its tracks, each a part with its codec, its frame size and rate or
// its channels and sample rate, its duration, and the BLAKE3 of its samples in decode order; an MPEG audio, ADTS,
// Ogg Opus or IVF stream gives the same of its one stream; a raw elementary stream gives its codec. Parsed here, by
// this code, so the op's output is a function of the bytes and its version is ours (§10.5.5).
import { blake3Stream } from "@ath/kit/hash.ts";
import type { Constituent, IntrinsicsResult, J } from "../format.ts";
import { type Box, boxes, child, children, str4, top, u16, u32, u64, version } from "./bmff.ts";

const us = (x: number) => Math.round(x * 1e6) / 1e6;
const gcd = (a: number, b: number): number => (b ? gcd(b, a % b) : a);
const ratio = (n: number, d: number) => {
  const g = gcd(n, d) || 1;
  return `${n / g}/${d / g}`;
};

const CODECS: Record<string, string> = {
  avc1: "h264",
  avc3: "h264",
  hvc1: "hevc",
  hev1: "hevc",
  av01: "av1",
  vp09: "vp9",
  vp08: "vp8",
  mp4v: "mpeg4",
  jpeg: "mjpeg",
  mp4a: "aac",
  Opus: "opus",
  fLaC: "flac",
  alac: "alac",
  "ac-3": "ac3",
  "ec-3": "eac3",
  ".mp3": "mp3",
  sowt: "pcm",
  twos: "pcm",
  lpcm: "pcm",
  tx3g: "tx3g",
  wvtt: "webvtt",
  c608: "eia-608",
  text: "text",
  tmcd: "timecode",
};
const HANDLERS: Record<string, string> = {
  vide: "video",
  soun: "audio",
  text: "text",
  sbtl: "subtitle",
  subt: "subtitle",
  tmcd: "timecode",
};

function headerTimes(b: Uint8Array, box: Box): { timescale: number; duration: number } {
  const v1 = version(b, box) === 1;
  return v1
    ? { timescale: u32(b, box.body + 20), duration: u64(b, box.body + 24) }
    : { timescale: u32(b, box.body + 12), duration: u32(b, box.body + 16) };
}

/** The byte ranges of a track's samples in decode order, from its sample table. */
function sampleRanges(b: Uint8Array, stbl: Box): [number, number][] {
  const stsz = child(b, stbl, "stsz");
  const stsc = child(b, stbl, "stsc");
  const stco = child(b, stbl, "stco") ?? child(b, stbl, "co64");
  if (!stsz || !stsc || !stco) return [];
  const fixed = u32(b, stsz.body + 4);
  const count = u32(b, stsz.body + 8);
  const size = (i: number) => (fixed ? fixed : u32(b, stsz.body + 12 + 4 * i));
  const runs: { first: number; per: number }[] = [];
  for (let i = 0, n = u32(b, stsc.body + 4); i < n; i++)
    runs.push({ first: u32(b, stsc.body + 8 + 12 * i), per: u32(b, stsc.body + 12 + 12 * i) });
  const wide = stco.type === "co64";
  const chunks = u32(b, stco.body + 4);
  const out: [number, number][] = [];
  let sample = 0;
  for (let c = 1; c <= chunks && sample < count; c++) {
    let per = 0;
    for (const r of runs) if (r.first <= c) per = r.per;
    let off = wide ? u64(b, stco.body + 8 + 8 * (c - 1)) : u32(b, stco.body + 8 + 4 * (c - 1));
    for (let k = 0; k < per && sample < count; k++, sample++) {
      const n = size(sample);
      out.push([off, off + n]);
      off += n;
    }
  }
  return out;
}

async function track(b: Uint8Array, trak: Box, index: number, movieScale: number): Promise<Constituent | null> {
  const mdia = child(b, trak, "mdia");
  const mdhd = child(b, mdia, "mdhd");
  const hdlr = child(b, mdia, "hdlr");
  const stbl = child(b, child(b, mdia, "minf"), "stbl");
  if (!mdhd || !hdlr || !stbl) return null;
  const { timescale, duration } = headerTimes(b, mdhd);
  const handler = str4(b, hdlr.body + 8);
  const stsd = child(b, stbl, "stsd");
  const entry = stsd ? (boxes(b, stsd.body + 8, stsd.end)[0] ?? null) : null;
  const fourcc = entry?.type ?? "";
  const facts: J = { type: HANDLERS[handler] ?? handler, codec: CODECS[fourcc] ?? fourcc.trim() };
  if (entry && handler === "vide") {
    facts.width = u16(b, entry.body + 24);
    facts.height = u16(b, entry.body + 26);
    const stts = child(b, stbl, "stts");
    if (stts && duration) {
      const n = u32(b, stts.body + 4);
      let samples = 0;
      const deltas = new Set<number>();
      for (let i = 0; i < n; i++) {
        samples += u32(b, stts.body + 8 + 8 * i);
        deltas.add(u32(b, stts.body + 12 + 8 * i));
      }
      facts.frame_rate = deltas.size === 1 ? ratio(timescale, [...deltas][0]!) : ratio(samples * timescale, duration);
    }
  } else if (entry && handler === "soun") {
    facts.channels = u16(b, entry.body + 16);
    facts.sample_rate = u16(b, entry.body + 24);
  }
  // the track's presentation duration (its header's, in the movie's timescale), which edit lists have already trimmed
  const tkhd = child(b, trak, "tkhd");
  if (tkhd && movieScale) facts.duration = us((version(b, tkhd) === 1 ? u64(b, tkhd.body + 28) : u32(b, tkhd.body + 20)) / movieScale);
  else if (timescale) facts.duration = us(duration / timescale);
  const ranges = sampleRanges(b, stbl);
  const h = await blake3Stream();
  for (const [s, e] of ranges) h.update(b.subarray(s, e));
  const read = () => {
    const total = ranges.reduce((n, [s, e]) => n + e - s, 0);
    const out = new Uint8Array(total);
    let p = 0;
    for (const [s, e] of ranges) {
      out.set(b.subarray(s, e), p);
      p += e - s;
    }
    return out;
  };
  return { path: String(index), blake3: h.digest(), kind: "part", intrinsics: facts, read };
}

async function isoMedia(b: Uint8Array): Promise<IntrinsicsResult> {
  const moov = top(b, "moov");
  if (!moov) return { facts: {} };
  const mvhd = child(b, moov, "mvhd");
  const facts: J = {};
  const movieScale = mvhd ? headerTimes(b, mvhd).timescale : 0;
  if (mvhd && movieScale) facts.duration = us(headerTimes(b, mvhd).duration / movieScale);
  const constituents: Constituent[] = [];
  let i = 0;
  for (const trak of children(b, moov, "trak")) {
    const t = await track(b, trak, i++, movieScale);
    if (t) constituents.push(t);
  }
  return { facts, constituents };
}

// ── single-stream formats ───────────────────────────────────────────────────────────────────────────────────────────

const MP3_BITRATES: Record<string, number[]> = {
  "1-1": [0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448],
  "1-2": [0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384],
  "1-3": [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
  "2-1": [0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256],
  "2-2": [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
};
const MP3_RATES: Record<number, number[]> = { 3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000] };

/** MPEG audio: frames counted from the first sync after any ID3v2 tag; a Xing or Info frame is metadata, not audio. */
function mpegAudio(b: Uint8Array): J {
  let p = 0;
  if (b[0] === 0x49 && b[1] === 0x44 && b[2] === 0x33)
    p = 10 + ((b[6]! << 21) | (b[7]! << 14) | (b[8]! << 7) | b[9]!) + (b[5]! & 0x10 ? 10 : 0);
  let frames = 0;
  let spf = 0;
  let rate = 0;
  let channels = 0;
  let first = true;
  while (p + 4 <= b.length) {
    if (b[p] !== 0xff || (b[p + 1]! & 0xe0) !== 0xe0) {
      p++;
      continue;
    }
    const ver = (b[p + 1]! >> 3) & 3;
    const layer = 4 - ((b[p + 1]! >> 1) & 3);
    const bi = b[p + 2]! >> 4;
    const si = (b[p + 2]! >> 2) & 3;
    if (ver === 1 || layer === 4 || bi === 0 || bi === 15 || si === 3) {
      p++;
      continue;
    }
    const sr = MP3_RATES[ver]![si]!;
    const br = MP3_BITRATES[ver === 3 ? `1-${layer}` : layer === 1 ? "2-1" : "2-2"]![bi]! * 1000;
    const pad = (b[p + 2]! >> 1) & 1;
    const len = layer === 1 ? (Math.floor((12 * br) / sr) + pad) * 4 : Math.floor(((layer === 3 && ver !== 3 ? 72 : 144) * br) / sr) + pad;
    const mono = b[p + 3]! >> 6 === 3;
    if (first) {
      first = false;
      const side = ver === 3 ? (mono ? 17 : 32) : mono ? 9 : 17;
      const tag = String.fromCharCode(...b.subarray(p + 4 + side, p + 8 + side));
      spf = layer === 1 ? 384 : layer === 2 || ver === 3 ? 1152 : 576;
      rate = sr;
      channels = mono ? 1 : 2;
      if (tag === "Xing" || tag === "Info") {
        p += len;
        continue;
      }
    }
    frames++;
    p += Math.max(len, 1);
  }
  return rate ? { codec: "mp3", channels, sample_rate: rate, duration: us((frames * spf) / rate) } : { codec: "mp3" };
}

const AAC_RATES = [96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000, 7350];

function adts(b: Uint8Array): J {
  let p = 0;
  let samples = 0;
  let rate = 0;
  let channels = 0;
  while (p + 7 <= b.length && b[p] === 0xff && (b[p + 1]! & 0xf0) === 0xf0) {
    rate = AAC_RATES[(b[p + 2]! >> 2) & 0xf] ?? 0;
    channels = ((b[p + 2]! & 1) << 2) | (b[p + 3]! >> 6);
    const len = ((b[p + 3]! & 3) << 11) | (b[p + 4]! << 3) | (b[p + 5]! >> 5);
    samples += 1024 * ((b[p + 6]! & 3) + 1);
    if (len < 7) break;
    p += len;
  }
  return rate ? { codec: "aac", channels, sample_rate: rate, duration: us(samples / rate) } : { codec: "aac" };
}

/** Ogg Opus: channels and pre-skip from OpusHead; the duration from the last page's granule position at 48 kHz. */
function oggOpus(b: Uint8Array): J {
  const le16 = (p: number) => b[p]! | (b[p + 1]! << 8);
  const le64 = (p: number) =>
    (b[p]! | (b[p + 1]! << 8) | (b[p + 2]! << 16)) + (b[p + 3]! * 2 ** 24 + b[p + 4]! * 2 ** 32 + b[p + 5]! * 2 ** 40);
  const head = Buffer.from(b).indexOf("OpusHead");
  if (head < 0) return { codec: "opus" };
  const channels = b[head + 9]!;
  const preSkip = le16(head + 10);
  let granule = 0;
  for (let p = 0; p + 27 <= b.length; ) {
    if (str4(b, p) !== "OggS") break;
    const g = le64(p + 6);
    if (g < 2 ** 47) granule = g;
    const n = b[p + 26]!;
    let body = 0;
    for (let i = 0; i < n; i++) body += b[p + 27 + i]!;
    p += 27 + n + body;
  }
  return { codec: "opus", channels, sample_rate: 48000, duration: us(Math.max(0, granule - preSkip) / 48000) };
}

function ivf(b: Uint8Array): J {
  const le16 = (p: number) => b[p]! | (b[p + 1]! << 8);
  const le32 = (p: number) => (b[p]! | (b[p + 1]! << 8) | (b[p + 2]! << 16) | (b[p + 3]! << 24)) >>> 0;
  const fourcc = str4(b, 8);
  const den = le32(16);
  const num = le32(20);
  const frames = le32(24);
  const out: J = { codec: { AV01: "av1", VP80: "vp8", VP90: "vp9" }[fourcc] ?? fourcc.trim(), width: le16(12), height: le16(14) };
  if (den && num) {
    out.frame_rate = ratio(den, num);
    out.duration = us((frames * num) / den);
  }
  return out;
}

export async function mediaIntrinsics(b: Uint8Array, mime: string): Promise<IntrinsicsResult> {
  if (b.length >= 12 && str4(b, 4) === "ftyp") return isoMedia(b);
  switch (mime) {
    case "audio/mpeg":
      return { facts: mpegAudio(b) };
    case "audio/aac":
      return { facts: adts(b) };
    case "audio/opus":
      return { facts: oggOpus(b) };
    case "video/av1":
    case "video/x-ivf":
      return { facts: ivf(b) };
    case "video/h264":
      return { facts: { codec: "h264" } };
    case "video/hevc":
      return { facts: { codec: "hevc" } };
    default:
      return { facts: {} };
  }
}
