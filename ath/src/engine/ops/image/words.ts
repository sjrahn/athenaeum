// words.ts — `image.words@1`: tesseract's word boxes over a raster, normalised on the pixel grid (D-ocr). A proposal,
// never a derivation: a raster root declares no derivation, so nothing binds to this; a pass accepts the lines it
// proposes into manifests + reads_as, and L7 lists every image reading for inspection. The engine version rides in
// the proposal so the pass note can carry it.
import { AthError } from "../../../kit/errors.ts";
import { runLocal } from "../../../lib/spawn.ts";
import type { Box } from "../../model/address.ts";
import { fmt } from "../../model/address.ts";
import { imageDims } from "./headers.ts";

export const IMAGE_WORDS_OP = "image.words@1";

export interface OcrWord {
  text: string;
  bbox: Box;
  conf: number;
}

export interface OcrLine {
  bbox: Box;
  words: OcrWord[];
  text: string;
}

export interface OcrResult {
  engine: string;
  width: number;
  height: number;
  lines: OcrLine[];
}

export function tesseractVersion(): string | null {
  if (!Bun.which("tesseract")) return null;
  const r = runLocal(["tesseract", "--version"], { allowFail: true });
  const first = new TextDecoder().decode(r.stdout).split("\n")[0] || r.stderr.split("\n")[0] || "";
  return first.trim() || "tesseract";
}

/** Parse tesseract's TSV (level 5 = words) into lines of words with boxes normalised by the image size. */
export function parseTsv(tsv: string, width: number, height: number): OcrLine[] {
  const lines = new Map<string, OcrLine>();
  const rows = tsv.split("\n").slice(1);
  for (const row of rows) {
    const c = row.split("\t");
    if (c.length < 12 || c[0] !== "5") continue;
    const text = c[11]!.trim();
    if (!text) continue;
    const key = `${c[2]}/${c[3]}/${c[4]}`;
    const left = Number(c[6]);
    const top = Number(c[7]);
    const w = Number(c[8]);
    const h = Number(c[9]);
    const word: OcrWord = { text, bbox: [r4(left / width), r4(top / height), r4(w / width), r4(h / height)], conf: Number(c[10]) };
    const l = lines.get(key) ?? { bbox: word.bbox, words: [], text: "" };
    l.words.push(word);
    lines.set(key, l);
  }
  const out: OcrLine[] = [];
  for (const l of lines.values()) {
    const x0 = Math.min(...l.words.map((w) => w.bbox[0]));
    const y0 = Math.min(...l.words.map((w) => w.bbox[1]));
    const x1 = Math.max(...l.words.map((w) => w.bbox[0] + w.bbox[2]));
    const y1 = Math.max(...l.words.map((w) => w.bbox[1] + w.bbox[3]));
    out.push({ bbox: [x0, y0, r4(x1 - x0), r4(y1 - y0)], words: l.words, text: l.words.map((w) => w.text).join(" ") });
  }
  return out.sort((a, b) => a.bbox[1] - b.bbox[1] || a.bbox[0] - b.bbox[0]);
}

const r4 = (n: number) => Number(fmt(n));

export function ocrWords(bytes: Uint8Array, mime: string): OcrResult {
  const dims = imageDims(mime, bytes);
  if (!dims) throw new AthError("EXTERNAL", `image.words@1: cannot read the dimensions of ${mime}`);
  const engine = tesseractVersion();
  if (!engine) throw new AthError("EXTERNAL", "tesseract is not on PATH");
  const r = runLocal(["tesseract", "stdin", "stdout", "--psm", "6", "tsv"], { stdin: bytes });
  return { engine, width: dims.width, height: dims.height, lines: parseTsv(new TextDecoder().decode(r.stdout), dims.width, dims.height) };
}

/** The proposal as claim lines: one `label` scope per OCR line with its text, placed in whole in reading order. */
export function proposalLines(res: OcrResult, term = "label"): Record<string, unknown>[] {
  const out: Record<string, unknown>[] = [];
  res.lines.forEach((l, i) => {
    const at = `bbox=${l.bbox.map(fmt).join(",")}`;
    out.push({ at, predicate: "manifests", term });
    out.push({ at, predicate: "in", value: { at: "whole", ord: i } });
    out.push({ at, predicate: "reads_as", aspect: "text", body: l.text });
  });
  return out;
}
