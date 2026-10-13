// sniff.ts — the mime of bytes, from magic first and the file name second. Only the mimes the ontology's roots know
// need a name here; everything else is application/octet-stream and manifests nothing until a term claims it.
const text = (b: Uint8Array, n = 512): string => new TextDecoder("latin1").decode(b.subarray(0, n));

export function sniffMime(bytes: Uint8Array, name = ""): string {
  const b = bytes;
  const starts = (sig: number[], off = 0) => sig.every((v, i) => b[off + i] === v);
  if (starts([0x25, 0x50, 0x44, 0x46])) return "application/pdf"; // %PDF
  if (starts([0xff, 0xd8, 0xff])) return "image/jpeg";
  if (starts([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) return "image/png";
  if (starts([0x47, 0x49, 0x46, 0x38])) return "image/gif";
  if (starts([0x52, 0x49, 0x46, 0x46]) && starts([0x57, 0x45, 0x42, 0x50], 8)) return "image/webp";
  if (starts([0x50, 0x4b, 0x03, 0x04]) || starts([0x50, 0x4b, 0x05, 0x06])) {
    const ext = name.toLowerCase();
    if (ext.endsWith(".epub")) return "application/epub+zip";
    if (ext.endsWith(".docx")) return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    if (ext.endsWith(".xlsx")) return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    return "application/zip";
  }
  if (starts([0x1f, 0x8b])) return "application/gzip";
  const head = text(b, 2048).replace(/^﻿/, "").trimStart().toLowerCase();
  if (/^(<\?xml[^>]*\?>\s*(<!--[\s\S]*?-->\s*)*)?<svg[\s>]/.test(head) || /^<!doctype svg/.test(head)) return "image/svg+xml";
  if (/^(<!doctype html|<html|<head|<meta |<\?xml[^>]*\?>\s*<html)/.test(head) || /<html[\s>]/.test(head.slice(0, 1024)))
    return "text/html";
  const ext = name.toLowerCase().split(".").pop() ?? "";
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
    mp4: "video/mp4",
    mov: "video/quicktime",
    mp3: "audio/mpeg",
    opus: "audio/opus",
    m4a: "audio/mp4",
  };
  if (byExt[ext]) return byExt[ext]!;
  // text or binary?
  const sample = b.subarray(0, 4096);
  let control = 0;
  for (const c of sample) if (c < 9 || (c > 13 && c < 32)) control++;
  return control > sample.length / 64 ? "application/octet-stream" : "text/plain";
}
