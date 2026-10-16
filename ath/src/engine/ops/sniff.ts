// sniff.ts — the mime of bytes, from magic first and the file name second (D-sniff). Only the mimes the ontology's
// roots know need a name here; everything else is application/octet-stream and manifests nothing until a term
// claims it. A zip is told apart by what it holds (the OCF `mimetype` member, an OOXML part), not by its extension.
import { readCentralDirectory } from "./zip/roster.ts";

const text = (b: Uint8Array, n = 512): string => new TextDecoder("latin1").decode(b.subarray(0, n));

const BRANDS: Record<string, string> = {
  heic: "image/heic",
  heix: "image/heic",
  hevc: "image/heic",
  hevx: "image/heic",
  mif1: "image/heic",
  msf1: "image/heic",
  avif: "image/avif",
  avis: "image/avif",
  "M4A ": "audio/mp4",
  "M4B ": "audio/mp4",
  "qt  ": "video/quicktime",
  "3gp4": "video/3gpp",
  "3gp5": "video/3gpp",
};

/** A zip's kind from its roster: epub by the OCF mimetype member, OOXML by its parts; else a plain zip. */
function zipKind(b: Uint8Array): string {
  let names: string[];
  try {
    names = readCentralDirectory(b).map((e) => e.path);
  } catch {
    return "application/zip";
  }
  if (names.includes("mimetype") && names.includes("META-INF/container.xml")) {
    // the OCF mimetype member is stored first, uncompressed: its content sits right after the local header
    const nameLen = b[26]! | (b[27]! << 8);
    const extraLen = b[28]! | (b[29]! << 8);
    const at = 30 + nameLen + extraLen;
    if (
      text(b.subarray(0, 30 + nameLen), 30 + nameLen).endsWith("mimetype") &&
      text(b.subarray(at, at + 20), 20) === "application/epub+zip"
    )
      return "application/epub+zip";
  }
  if (names.includes("[Content_Types].xml")) {
    if (names.some((n) => n.startsWith("xl/"))) return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    if (names.some((n) => n.startsWith("word/"))) return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    if (names.some((n) => n.startsWith("ppt/"))) return "application/vnd.openxmlformats-officedocument.presentationml.presentation";
  }
  return "application/zip";
}

const HEADER_LINE = /^[!-9;-~]+:[ \t]/;
const MAIL_FIELDS = /(^|\n)(received|from|date|message-id|subject|to|mime-version|return-path|delivered-to|x-gm-thrid):/i;

function looksLikeMessage(head: string): boolean {
  const firstLine = head.split("\n", 1)[0] ?? "";
  if (!HEADER_LINE.test(firstLine)) return false;
  return MAIL_FIELDS.test(head.slice(0, 8192));
}

function looksLikeMbox(head: string): boolean {
  if (!head.startsWith("From ")) return false;
  const second = head.split("\n")[1] ?? "";
  return HEADER_LINE.test(second);
}

function looksLikeJson(b: Uint8Array): "object" | "lines" | null {
  const head = text(b, 64)
    .replace(/^\xef\xbb\xbf/, "")
    .trimStart();
  if (!(head.startsWith("{") || head.startsWith("["))) return null;
  const whole = new TextDecoder("utf-8").decode(b.subarray(0, Math.min(b.length, 4 * 1024 * 1024)));
  if (b.length <= 4 * 1024 * 1024) {
    try {
      JSON.parse(whole);
      return "object";
    } catch {
      // maybe lines
    }
  }
  const first = whole.split("\n", 1)[0] ?? "";
  try {
    JSON.parse(first);
    return whole.includes("\n") ? "lines" : null;
  } catch {
    return null;
  }
}

export function sniffMime(bytes: Uint8Array, name = ""): string {
  const b = bytes;
  const ext = name.toLowerCase().split(".").pop() ?? "";
  const starts = (sig: number[], off = 0) => sig.every((v, i) => b[off + i] === v);
  if (starts([0x25, 0x50, 0x44, 0x46])) return "application/pdf"; // %PDF
  if (starts([0xff, 0xd8, 0xff])) return "image/jpeg";
  if (starts([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) return "image/png";
  if (starts([0x47, 0x49, 0x46, 0x38])) return "image/gif";
  if (starts([0x52, 0x49, 0x46, 0x46]) && starts([0x57, 0x45, 0x42, 0x50], 8)) return "image/webp";
  if (starts([0x50, 0x4b, 0x03, 0x04]) || starts([0x50, 0x4b, 0x05, 0x06])) return zipKind(b);
  if (starts([0x1f, 0x8b])) return "application/gzip";
  if (starts([0x49, 0x49, 0x2a, 0x00]) || starts([0x4d, 0x4d, 0x00, 0x2a]))
    return ext === "arw" ? "image/x-sony-arw" : ext === "dng" ? "image/x-adobe-dng" : "image/tiff";
  if (starts([0x52, 0x61, 0x72, 0x21, 0x1a, 0x07])) return "application/vnd.rar";
  if (starts([0x37, 0x7a, 0xbc, 0xaf, 0x27, 0x1c])) return "application/x-7z-compressed";
  if (starts([0x4d, 0x5a])) return "application/x-msdownload";
  if (starts([0x7f, 0x45, 0x4c, 0x46])) return "application/x-executable";
  if (b.length >= 12 && starts([0x66, 0x74, 0x79, 0x70], 4)) {
    const brand = text(b.subarray(8, 12), 4);
    return BRANDS[brand] ?? (ext === "m4a" ? "audio/mp4" : ext === "mov" ? "video/quicktime" : "video/mp4");
  }
  const head = text(b, 8192).replace(/^\xef\xbb\xbf/, "");
  const lower = head.trimStart().toLowerCase();
  // a message starts with header lines; it may well mention <html> within its first kilobyte
  if (looksLikeMbox(head)) return "application/mbox";
  if (looksLikeMessage(head)) return "message/rfc822";
  if (/^(<\?xml[^>]*\?>\s*(<!--[\s\S]*?-->\s*)*)?<svg[\s>]/.test(lower) || /^<!doctype svg/.test(lower)) return "image/svg+xml";
  if (
    /^(<!doctype html|<html|<head|<meta |<\?xml[^>]*\?>\s*(<!doctype[^>]*>\s*)?<html)/.test(lower) ||
    /<html[\s>]/.test(lower.slice(0, 1024))
  )
    return "text/html";
  if (lower.startsWith("<?xml")) return "application/xml";
  if (head.startsWith("BEGIN:VCARD")) return "text/vcard";
  if (head.startsWith("BEGIN:VCALENDAR")) return "text/calendar";
  if (head.startsWith("ISO-10303-21;")) return "application/p21";
  if (/^\s*0\r?\nSECTION\r?\n/.test(head)) return "image/vnd.dxf";
  const json = looksLikeJson(b);
  if (json === "object" && !(ext === "jsonl" || ext === "ndjson")) return "application/json";
  if (json === "lines" || ((ext === "jsonl" || ext === "ndjson") && json !== null)) return "application/x-ndjson";
  const byExt: Record<string, string> = {
    csv: "text/csv",
    tsv: "text/tab-separated-values",
    md: "text/markdown",
    markdown: "text/markdown",
    txt: "text/plain",
    json: "application/json",
    jsonl: "application/x-ndjson",
    ndjson: "application/x-ndjson",
    xml: "application/xml",
    html: "text/html",
    htm: "text/html",
    xhtml: "application/xhtml+xml",
    eml: "message/rfc822",
    mbox: "application/mbox",
    vcf: "text/vcard",
    ics: "text/calendar",
    css: "text/css",
    js: "text/javascript",
    mjs: "text/javascript",
    ts: "text/typescript",
    py: "text/x-python",
    mp4: "video/mp4",
    mov: "video/quicktime",
    mp3: "audio/mpeg",
    opus: "audio/opus",
    m4a: "audio/mp4",
    p21: "application/p21",
    cfg: "text/plain",
    conf: "text/plain",
    log: "text/plain",
    gpx: "application/xml",
    tcx: "application/xml",
    ifc: "application/p21",
    step: "application/p21",
    stp: "application/p21",
  };
  if (byExt[ext]) return byExt[ext]!;
  // text or binary?
  const sample = b.subarray(0, 4096);
  let control = 0;
  for (const c of sample) if (c < 9 || (c > 13 && c < 32)) control++;
  return control > sample.length / 64 ? "application/octet-stream" : "text/plain";
}
