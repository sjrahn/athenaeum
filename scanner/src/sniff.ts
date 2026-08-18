// The advisory MIME sniffer — spec/corpus.md §12.1.1 *(25)*. DELIBERATELY COARSE: this
// produces a claim, never a verdict — the corpus's own content-based format detection
// (§12.3.2) is authoritative and undisturbed. No container-member inspection (a zip is
// always application/zip, never refined into e.g. .docx/.xlsx by peeking at its central
// directory) and no exhaustive MP4/ISO-BMFF sub-brand table — just enough magic-byte
// coverage to answer "what kind of file is this, roughly" without becoming a format library.
//
// Order: magic bytes first (from the signature table below), then an extension fallback for
// common text-ish formats magic can't settle, then a last-resort "looks like text" heuristic,
// else null (unknown — the common case for a database blob, a proprietary binary format, etc).

import { open } from "node:fs/promises";

/** Bounded head read: never more than this many leading bytes are inspected or read off disk. */
export const SNIFF_HEAD_BYTES = 16 * 1024;

export interface Signature {
  readonly mime: string;
  readonly test: (head: Uint8Array) => boolean;
}

function bytesEqual(head: Uint8Array, offset: number, expected: readonly number[]): boolean {
  if (head.length < offset + expected.length) return false;
  for (let i = 0; i < expected.length; i++) if (head[offset + i] !== expected[i]) return false;
  return true;
}

function asciiEqual(head: Uint8Array, offset: number, text: string): boolean {
  return bytesEqual(head, offset, Array.from(text, (c) => c.charCodeAt(0)));
}

function ascii4(head: Uint8Array, offset: number): string | null {
  if (head.length < offset + 4) return null;
  return String.fromCharCode(head[offset]!, head[offset + 1]!, head[offset + 2]!, head[offset + 3]!);
}

/** RIFF containers (WAV/AVI/WebP) share one 12-byte header shape: "RIFF" + 4-byte size + fourCC. */
function riffFourCC(head: Uint8Array): string | null {
  if (!asciiEqual(head, 0, "RIFF")) return null;
  return ascii4(head, 8);
}

const HEIC_BRANDS = new Set(["heic", "heix", "hevc", "heim", "heis", "hevm", "hevs"]);
const HEIF_BRANDS = new Set(["mif1", "msf1"]);

/** ISO-BMFF (`ftyp` at offset 4): mp4/m4a/m4v/mov/heic/heif family, disambiguated by the
 * major brand at offset 8 where that's cheap; anything unrecognized defaults to video/mp4
 * (the common case — audio-only .m4a/.m4v get their own brand check first). */
function sniffFtyp(head: Uint8Array): string {
  const brand = ascii4(head, 8) ?? "";
  if (HEIC_BRANDS.has(brand)) return "image/heic";
  if (HEIF_BRANDS.has(brand)) return "image/heif";
  if (brand === "M4A ") return "audio/mp4";
  if (brand === "M4V ") return "video/mp4";
  if (brand === "qt  ") return "video/quicktime";
  return "video/mp4";
}

/** EBML (Matroska family: mkv/webm). Distinguished by DocType — "webm" found in the head is a
 * trivial-enough check for this coarse a claim; anything else EBML defaults to Matroska. */
function sniffEbml(head: Uint8Array): string {
  const text = Buffer.from(head.subarray(0, Math.min(head.length, 4096))).toString("latin1");
  return text.includes("webm") ? "video/webm" : "video/x-matroska";
}

// Checked in order; first match wins. `ftyp`/EBML need their own header parsing (branch on
// bytes beyond the fixed prefix) so they're resolved by sniffMime() before this table runs,
// not folded into it as ordinary fixed-signature entries.
const SIGNATURES: readonly Signature[] = [
  { mime: "image/jpeg", test: (h) => bytesEqual(h, 0, [0xff, 0xd8, 0xff]) },
  { mime: "image/png", test: (h) => bytesEqual(h, 0, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]) },
  { mime: "image/gif", test: (h) => asciiEqual(h, 0, "GIF87a") || asciiEqual(h, 0, "GIF89a") },
  { mime: "image/webp", test: (h) => riffFourCC(h) === "WEBP" },
  { mime: "audio/wav", test: (h) => riffFourCC(h) === "WAVE" },
  { mime: "video/x-msvideo", test: (h) => riffFourCC(h) === "AVI " },
  { mime: "image/bmp", test: (h) => asciiEqual(h, 0, "BM") },
  { mime: "image/tiff", test: (h) => bytesEqual(h, 0, [0x49, 0x49, 0x2a, 0x00]) || bytesEqual(h, 0, [0x4d, 0x4d, 0x00, 0x2a]) },
  { mime: "audio/mpeg", test: (h) => asciiEqual(h, 0, "ID3") || (h.length >= 2 && h[0] === 0xff && (h[1]! & 0xe0) === 0xe0) },
  { mime: "audio/flac", test: (h) => asciiEqual(h, 0, "fLaC") },
  { mime: "audio/ogg", test: (h) => asciiEqual(h, 0, "OggS") },
  { mime: "application/pdf", test: (h) => asciiEqual(h, 0, "%PDF-") },
  {
    mime: "application/zip", // deliberately not refined by member inspection — see file header
    test: (h) => bytesEqual(h, 0, [0x50, 0x4b, 0x03, 0x04]) || bytesEqual(h, 0, [0x50, 0x4b, 0x05, 0x06]) || bytesEqual(h, 0, [0x50, 0x4b, 0x07, 0x08]),
  },
  { mime: "application/gzip", test: (h) => bytesEqual(h, 0, [0x1f, 0x8b]) },
  { mime: "application/x-xz", test: (h) => bytesEqual(h, 0, [0xfd, 0x37, 0x7a, 0x58, 0x5a, 0x00]) },
  { mime: "application/zstd", test: (h) => bytesEqual(h, 0, [0x28, 0xb5, 0x2f, 0xfd]) },
  { mime: "application/x-7z-compressed", test: (h) => bytesEqual(h, 0, [0x37, 0x7a, 0xbc, 0xaf, 0x27, 0x1c]) },
  { mime: "application/x-rar-compressed", test: (h) => asciiEqual(h, 0, "Rar!") && bytesEqual(h, 4, [0x1a, 0x07]) },
  { mime: "application/x-tar", test: (h) => asciiEqual(h, 257, "ustar") },
  { mime: "application/vnd.sqlite3", test: (h) => asciiEqual(h, 0, "SQLite format 3\0") },
];

/** Small extension table for common text-ish formats magic bytes can't settle (plain
 * structured text with no fixed header). Deliberately kept small — this is a fallback for
 * cases the magic table misses, not a general extension→mime map. */
const EXTENSION_FALLBACK: Readonly<Record<string, string>> = {
  ".srt": "application/x-subrip",
  ".json": "application/json",
  ".csv": "text/csv",
  ".md": "text/markdown",
};

function looksLikeText(head: Uint8Array): boolean {
  if (head.length === 0) return false;
  if (head.includes(0)) return false; // a NUL byte is a strong binary signal
  try {
    new TextDecoder("utf-8", { fatal: true }).decode(head);
    return true;
  } catch {
    return false;
  }
}

/** Export for tests and callers that want the raw table; the two header-parsed families
 * (ftyp/EBML) aren't in it — see sniffMime()'s special-cased checks below. */
export const MAGIC_SIGNATURES: readonly Signature[] = SIGNATURES;

/**
 * Sniff an advisory MIME claim from `head` (the leading bytes of a file, up to
 * `SNIFF_HEAD_BYTES`). `filename` (basename or relative path; only the extension is used) is
 * optional and only consulted after magic bytes fail to match. Returns `null` when nothing
 * matches — an unrecognized binary format, an empty file, or anything else this coarse a
 * sniffer declines to guess at.
 */
export function sniffMime(head: Uint8Array, filename?: string): string | null {
  if (asciiEqual(head, 4, "ftyp")) return sniffFtyp(head);
  if (bytesEqual(head, 0, [0x1a, 0x45, 0xdf, 0xa3])) return sniffEbml(head);
  for (const sig of SIGNATURES) {
    if (sig.test(head)) return sig.mime;
  }
  if (filename) {
    const dot = filename.lastIndexOf(".");
    if (dot >= 0) {
      const fallback = EXTENSION_FALLBACK[filename.slice(dot).toLowerCase()];
      if (fallback) return fallback;
    }
  }
  if (looksLikeText(head)) return "text/plain";
  return null;
}

/**
 * Read up to `SNIFF_HEAD_BYTES` from the start of `abspath` — the bounded head-read used by
 * the native (b3sum) hash path and by the walk's mime_claim backfill pass, neither of which
 * otherwise touches file bytes on their own. Open/read/close, nothing streamed or cached.
 */
export async function readHead(abspath: string, maxBytes: number = SNIFF_HEAD_BYTES): Promise<Buffer> {
  const fh = await open(abspath, "r");
  try {
    const buf = Buffer.allocUnsafe(maxBytes);
    const { bytesRead } = await fh.read(buf, 0, maxBytes, 0);
    return buf.subarray(0, bytesRead);
  } finally {
    await fh.close();
  }
}
