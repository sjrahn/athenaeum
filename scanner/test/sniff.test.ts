// The advisory mime sniffer (src/sniff.ts): magic-byte coverage, ftyp/EBML disambiguation,
// extension fallback, the last-resort text heuristic, and "unknown binary -> null". These are
// pure-function tests against synthetic headers — no filesystem involved (readHead's
// bounded-read behavior is exercised indirectly by scanner.test.ts/catalog.test.ts).

import { test, expect } from "bun:test";
import { sniffMime, MAGIC_SIGNATURES, SNIFF_HEAD_BYTES } from "../src/sniff.ts";

const ascii = (s: string): Uint8Array => new Uint8Array(Buffer.from(s, "latin1"));
const bytes = (...b: number[]): Uint8Array => Uint8Array.from(b);
const concat = (...parts: Uint8Array[]): Uint8Array => {
  const total = parts.reduce((n, p) => n + p.length, 0);
  const out = new Uint8Array(total);
  let off = 0;
  for (const p of parts) {
    out.set(p, off);
    off += p.length;
  }
  return out;
};

// ── magic-byte formats ───────────────────────────────────────────────────────────────────

test("jpeg", () => {
  expect(sniffMime(bytes(0xff, 0xd8, 0xff, 0xe0, 0, 0, 0))).toBe("image/jpeg");
});

test("png", () => {
  expect(sniffMime(bytes(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0))).toBe("image/png");
});

test("gif87a and gif89a", () => {
  expect(sniffMime(ascii("GIF87a..."))).toBe("image/gif");
  expect(sniffMime(ascii("GIF89a..."))).toBe("image/gif");
});

test("bmp", () => {
  expect(sniffMime(ascii("BM") as Uint8Array)).toBe("image/bmp");
});

test("tiff (both byte orders)", () => {
  expect(sniffMime(bytes(0x49, 0x49, 0x2a, 0x00, 0, 0))).toBe("image/tiff"); // little-endian "II*\0"
  expect(sniffMime(bytes(0x4d, 0x4d, 0x00, 0x2a, 0, 0))).toBe("image/tiff"); // big-endian "MM\0*"
});

function riff(fourCC: string): Uint8Array {
  return concat(ascii("RIFF"), bytes(0, 0, 0, 0), ascii(fourCC));
}

test("riff family: webp, wav, avi", () => {
  expect(sniffMime(riff("WEBP"))).toBe("image/webp");
  expect(sniffMime(riff("WAVE"))).toBe("audio/wav");
  expect(sniffMime(riff("AVI "))).toBe("video/x-msvideo");
});

test("mp4/m4a/m4v/mov distinguished by ftyp brand where cheap, else video/mp4", () => {
  const ftyp = (brand: string) => concat(bytes(0, 0, 0, 0), ascii("ftyp"), ascii(brand));
  expect(sniffMime(ftyp("isom"))).toBe("video/mp4"); // generic brand -> default video/mp4
  expect(sniffMime(ftyp("M4A "))).toBe("audio/mp4");
  expect(sniffMime(ftyp("M4V "))).toBe("video/mp4");
  expect(sniffMime(ftyp("qt  "))).toBe("video/quicktime");
});

test("heic/heif brands", () => {
  const ftyp = (brand: string) => concat(bytes(0, 0, 0, 0), ascii("ftyp"), ascii(brand));
  expect(sniffMime(ftyp("heic"))).toBe("image/heic");
  expect(sniffMime(ftyp("heix"))).toBe("image/heic");
  expect(sniffMime(ftyp("mif1"))).toBe("image/heif");
  expect(sniffMime(ftyp("msf1"))).toBe("image/heif");
});

test("ebml: matroska default, webm when DocType is findable in the head", () => {
  const ebml = bytes(0x1a, 0x45, 0xdf, 0xa3);
  expect(sniffMime(concat(ebml, ascii("....matroska stuff....")))).toBe("video/x-matroska");
  expect(sniffMime(concat(ebml, ascii("....webm....")))).toBe("video/webm");
});

test("mp3: ID3 tag or raw frame sync", () => {
  expect(sniffMime(concat(ascii("ID3"), bytes(3, 0, 0, 0, 0, 0, 0)))).toBe("audio/mpeg");
  expect(sniffMime(bytes(0xff, 0xfb, 0x90, 0x00))).toBe("audio/mpeg"); // 11-bit frame sync, no ID3
});

test("flac and ogg", () => {
  expect(sniffMime(ascii("fLaC...."))).toBe("audio/flac");
  expect(sniffMime(ascii("OggS...."))).toBe("audio/ogg");
});

test("pdf", () => {
  expect(sniffMime(ascii("%PDF-1.4\n"))).toBe("application/pdf");
});

test("zip: local file header, empty-archive, and spanned signatures — no member refinement", () => {
  expect(sniffMime(bytes(0x50, 0x4b, 0x03, 0x04, 0, 0))).toBe("application/zip");
  expect(sniffMime(bytes(0x50, 0x4b, 0x05, 0x06, 0, 0))).toBe("application/zip");
  expect(sniffMime(bytes(0x50, 0x4b, 0x07, 0x08, 0, 0))).toBe("application/zip");
});

test("gzip, xz, zstd, 7z, rar", () => {
  expect(sniffMime(bytes(0x1f, 0x8b, 0x08, 0))).toBe("application/gzip");
  expect(sniffMime(bytes(0xfd, 0x37, 0x7a, 0x58, 0x5a, 0x00, 0))).toBe("application/x-xz");
  expect(sniffMime(bytes(0x28, 0xb5, 0x2f, 0xfd, 0))).toBe("application/zstd");
  expect(sniffMime(bytes(0x37, 0x7a, 0xbc, 0xaf, 0x27, 0x1c, 0))).toBe("application/x-7z-compressed");
  expect(sniffMime(concat(ascii("Rar!"), bytes(0x1a, 0x07, 0x00)))).toBe("application/x-rar-compressed");
});

test("tar: ustar magic at offset 257", () => {
  const head = new Uint8Array(262);
  head.set(ascii("ustar"), 257);
  expect(sniffMime(head)).toBe("application/x-tar");
});

test("a short head that can't reach offset 257 is not misdetected as tar", () => {
  expect(sniffMime(ascii("just some short content"))).not.toBe("application/x-tar");
});

test("sqlite3", () => {
  expect(sniffMime(concat(ascii("SQLite format 3\0"), bytes(0, 0, 0, 0)))).toBe("application/vnd.sqlite3");
});

// ── extension fallback ──────────────────────────────────────────────────────────────────

test("extension fallback for text-ish formats magic can't settle", () => {
  const plainAscii = ascii("1\n00:00:01,000 --> 00:00:02,000\nHello\n");
  // .srt content is plain text and WOULD match the text/plain heuristic too — extension
  // fallback must win (it's checked first).
  expect(sniffMime(plainAscii, "movie.srt")).toBe("application/x-subrip");
  expect(sniffMime(ascii('{"a":1}'), "data.json")).toBe("application/json");
  expect(sniffMime(ascii("a,b,c\n1,2,3\n"), "table.csv")).toBe("text/csv");
  expect(sniffMime(ascii("# Title\n"), "notes.md")).toBe("text/markdown");
});

test("extension fallback is case-insensitive and only applies when magic bytes didn't already match", () => {
  expect(sniffMime(ascii("plain text body"), "NOTES.MD")).toBe("text/markdown");
  // a real PDF named ".json" must still be detected as a pdf — magic wins over extension
  expect(sniffMime(ascii("%PDF-1.4\n"), "sneaky.json")).toBe("application/pdf");
});

// ── text heuristic (last resort) and unknown ────────────────────────────────────────────

test("plain UTF-8/ASCII text with no NUL and no extension match -> text/plain", () => {
  expect(sniffMime(ascii("just some plain ascii content, no special bytes"))).toBe("text/plain");
  expect(sniffMime(new TextEncoder().encode("héllo wörld — unicode text"))).toBe("text/plain");
});

test("unknown binary -> null", () => {
  // random-looking bytes, no NUL, but not valid UTF-8 either (a lone continuation byte).
  expect(sniffMime(bytes(0xde, 0xad, 0xbe, 0xef, 0x80, 0x81, 0x82))).toBeNull();
});

test("a NUL byte anywhere in the head defeats the text heuristic", () => {
  expect(sniffMime(bytes(0x61, 0x62, 0x00, 0x63))).toBeNull();
});

test("empty head -> null", () => {
  expect(sniffMime(new Uint8Array(0))).toBeNull();
});

// ── the exported table ──────────────────────────────────────────────────────────────────

test("MAGIC_SIGNATURES is exported and non-empty; every entry's mime is a plausible mime string", () => {
  expect(MAGIC_SIGNATURES.length).toBeGreaterThan(10);
  for (const sig of MAGIC_SIGNATURES) {
    expect(sig.mime).toMatch(/^[a-z]+\/[a-z0-9.+-]+$/);
  }
});

test("SNIFF_HEAD_BYTES is the documented 16 KiB bound", () => {
  expect(SNIFF_HEAD_BYTES).toBe(16 * 1024);
});
