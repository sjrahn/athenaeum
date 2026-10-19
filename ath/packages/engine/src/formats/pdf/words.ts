// words.ts — `pdf.words@1`, a hint (spec §10.6.2): the words the PDF draws, each with a box normalised 0–1 in the page
// as displayed — its crop box, its rotation applied, origin top-left — banded into lines on each glyph's baseline
// origin, in column-aware reading order. Text drawn invisible (render mode 3, an OCR layer under a page image)
// contributes nothing (§10.6.3). Nothing it yields is stored or bound.
import { type Box, DECIMALS, pointInBox, SLACK } from "../../address/address.ts";
import { registerOp } from "../ops.ts";
import { openPdf, type PdfDoc } from "./pdfium.ts";

export const PDF_WORDS_OP = "pdf.words@1";

export interface Word {
  text: string;
  bbox: Box;
}

export interface PageWords {
  page: number;
  width_pt: number;
  height_pt: number;
  words: Word[];
  /** Visual lines (baseline-banded), for chrome and headings. */
  lines: Line[];
}

export interface Line {
  y: number;
  h: number;
  x0: number;
  x1: number;
  text: string;
}

const LINE_TOLERANCE = 0.004;
const r4 = (n: number) => Math.round(n * 10 ** DECIMALS) / 10 ** DECIMALS;

/** Characters → words and lines for page `index0`. Origin top-left, boxes as fractions of the page. */
export function pageWords(d: PdfDoc, index0: number): PageWords {
  const m = d.m;
  const page = m.FPDF_LoadPage(d.doc, index0);
  const tp = m.FPDFText_LoadPage(page);
  // the displayed frame: the crop box (else the media box), the page's rotation applied clockwise in quarter turns;
  // a point maps into it exactly, normalised 0–1 with the origin top-left
  const width = m.FPDF_GetPageWidthF(page);
  const height = m.FPDF_GetPageHeightF(page);
  const buf = m.pdfium.wasmExports.malloc(32);
  const box4 = (get: (p: number, l: number, b: number, r: number, t: number) => boolean) =>
    get(page, buf, buf + 4, buf + 8, buf + 12) ? [0, 4, 8, 12].map((o) => m.pdfium.getValue(buf + o, "float")) : null;
  const [cl, cb, cr, ct] = box4(m.FPDFPage_GetCropBox) ?? box4(m.FPDFPage_GetMediaBox) ?? [0, 0, width, height];
  const rotate = ((m.FPDFPage_GetRotation(page) % 4) + 4) % 4;
  const toFrame = (px: number, py: number): [number, number] => {
    const u = (px - cl!) / (cr! - cl! || 1);
    const v = (ct! - py) / (ct! - cb! || 1);
    return rotate === 1 ? [1 - v, u] : rotate === 2 ? [1 - u, 1 - v] : rotate === 3 ? [v, 1 - u] : [u, v];
  };
  /** A box in page space (left, bottom, right, top) → [x0, y0, x1, y1] in the frame. */
  const frameBox = (l: number, b: number, r: number, t: number): [number, number, number, number] => {
    const [ax, ay] = toFrame(l, b);
    const [bx, by] = toFrame(r, t);
    return [Math.min(ax, bx), Math.min(ay, by), Math.max(ax, bx), Math.max(ay, by)];
  };
  const words: Word[] = [];
  const lines: Line[] = [];
  try {
    const n = m.FPDFText_CountChars(tp);
    let chars = "";
    let box: [number, number, number, number] | null = null; // x0, y0, x1, y1 in the frame
    const flush = () => {
      if (chars && box && width > 0 && height > 0) {
        const [x0, y0, x1, y1] = box;
        words.push({ text: chars, bbox: [r4(x0), r4(y0), r4(x1 - x0), r4(y1 - y0)] });
      }
      chars = "";
      box = null;
    };
    let cur: { base: number; top: number; h: number; x0: number; x1: number; text: string } | null = null;
    for (let i = 0; i < n; i++) {
      const cp = m.FPDFText_GetUnicode(tp, i);
      const ch = String.fromCodePoint(cp);
      if (ch === "\r" || ch === "\n") {
        flush();
        cur = null;
        continue;
      }
      // drawn text only: a glyph in render mode 3 (invisible) is not what the page shows
      const obj = m.FPDFText_GetTextObject(tp, i);
      if (obj && m.FPDFTextObj_GetTextRenderMode(obj) === 3) {
        flush();
        continue;
      }
      if (!m.FPDFText_GetCharBox(tp, i, buf, buf + 8, buf + 16, buf + 24)) continue;
      const [cx0, cy0, cx1, cy1] = frameBox(
        m.pdfium.getValue(buf, "double"),
        m.pdfium.getValue(buf + 16, "double"),
        m.pdfium.getValue(buf + 8, "double"),
        m.pdfium.getValue(buf + 24, "double"),
      );
      const left = cx0;
      const right = cx1;
      const top = cy0;
      const bottom = cy1;
      // lines: banded on the glyph's baseline origin (a descender's box bottom would open a new band under a font
      // that reports tight glyph boxes); the box bottom stands in when pdfium has no origin for the char
      const base = m.FPDFText_GetCharOrigin(tp, i, buf, buf + 8)
        ? toFrame(m.pdfium.getValue(buf, "double"), m.pdfium.getValue(buf + 8, "double"))[1]
        : bottom;
      if (cur && Math.abs(base - cur.base) > LINE_TOLERANCE) cur = null;
      if (!cur) {
        cur = { base, top, h: bottom - top, x0: left, x1: right, text: "" };
        lines.push(cur as unknown as Line);
      }
      cur.text += ch;
      cur.top = Math.min(cur.top, top);
      cur.h = Math.max(cur.h, bottom - top);
      cur.x0 = Math.min(cur.x0, left);
      cur.x1 = Math.max(cur.x1, right);
      // words
      if (/\s/.test(ch)) {
        flush();
        continue;
      }
      chars += ch;
      if (!box) box = [left, top, right, bottom];
      else {
        box[0] = Math.min(box[0], left);
        box[1] = Math.min(box[1], top);
        box[2] = Math.max(box[2], right);
        box[3] = Math.max(box[3], bottom);
      }
    }
    flush();
  } finally {
    m.pdfium.wasmExports.free(buf);
    m.FPDFText_ClosePage(tp);
    m.FPDF_ClosePage(page);
  }
  const outLines: Line[] = [];
  for (const l of lines as unknown as { top: number; h: number; x0: number; x1: number; text: string }[]) {
    const text = l.text.trim();
    if (!text) continue;
    outLines.push({ y: r4(l.top), h: r4(l.h), x0: r4(l.x0), x1: r4(l.x1), text });
  }
  return { page: index0 + 1, width_pt: Math.round(width * 100) / 100, height_pt: Math.round(height * 100) / 100, words, lines: outLines };
}

export async function allPages(bytes: Uint8Array): Promise<PageWords[]> {
  const d = await openPdf(bytes);
  try {
    const out: PageWords[] = [];
    for (let i = 0; i < d.pages; i++) out.push(pageWords(d, i));
    return out;
  } finally {
    d.close();
  }
}

/** Words whose centre lies in the box (with slack), in column-aware reading order. */
export function wordsInBox(words: readonly Word[], box: Box): Word[] {
  const inside = words.filter((w) => pointInBox(box, w.bbox[0] + w.bbox[2] / 2, w.bbox[1] + w.bbox[3] / 2, SLACK));
  return readingOrder(inside, box);
}

/** Lines by y-centre clustering, each sorted by x; columns split where a vertical gap ≥ 3% of the page separates
 * x-ranges across most lines (the two-column case). */
export function readingOrder(words: readonly Word[], box: Box): Word[] {
  if (!words.length) return [];
  const cols = splitColumns(words, box);
  const out: Word[] = [];
  for (const col of cols) {
    const sorted = [...col].sort((a, b) => a.bbox[1] + a.bbox[3] / 2 - (b.bbox[1] + b.bbox[3] / 2));
    const lines: Word[][] = [];
    for (const w of sorted) {
      const cy = w.bbox[1] + w.bbox[3] / 2;
      const last = lines[lines.length - 1];
      if (last) {
        const ly = last.reduce((s, x) => s + x.bbox[1] + x.bbox[3] / 2, 0) / last.length;
        const tol = Math.max(0.005, 0.6 * Math.max(...last.map((x) => x.bbox[3])));
        if (Math.abs(cy - ly) <= tol) {
          last.push(w);
          continue;
        }
      }
      lines.push([w]);
    }
    for (const l of lines) out.push(...l.sort((a, b) => a.bbox[0] - b.bbox[0]));
  }
  return out;
}

function splitColumns(words: readonly Word[], box: Box): Word[][] {
  if (words.length < 8) return [words.slice()];
  // a gutter: an x where no word crosses, over the box's width, at least 0.03 wide, with words on both sides
  const xs = words.map((w) => [w.bbox[0], w.bbox[0] + w.bbox[2]] as const).sort((a, b) => a[0] - b[0]);
  let reach = xs[0]![1];
  for (let i = 1; i < xs.length; i++) {
    const [x0, x1] = xs[i]!;
    if (x0 - reach >= 0.03 && x0 > box[0] + box[2] * 0.25 && x0 < box[0] + box[2] * 0.75) {
      const left = words.filter((w) => w.bbox[0] + w.bbox[2] <= reach + 1e-6);
      const right = words.filter((w) => w.bbox[0] >= x0 - 1e-6);
      if (left.length >= 3 && right.length >= 3 && left.length + right.length === words.length) return [left, right];
    }
    reach = Math.max(reach, x1);
  }
  return [words.slice()];
}

export const wordsText = (ws: readonly Word[]): string => ws.map((w) => w.text).join(" ");

/** Words in a region, banded into lines, in column-aware reading order. */
export function linesInBox(words: readonly Word[], box: Box): Word[][] {
  const ordered = wordsInBox(words, box);
  const lines: Word[][] = [];
  for (const w of ordered) {
    const last = lines.at(-1);
    const prev = last?.at(-1);
    // a word left of its predecessor, or off its band, starts a line
    if (
      prev &&
      w.bbox[0] >= prev.bbox[0] &&
      Math.abs(w.bbox[1] + w.bbox[3] / 2 - (prev.bbox[1] + prev.bbox[3] / 2)) <= Math.max(0.005, 0.6 * prev.bbox[3])
    )
      last!.push(w);
    else lines.push([w]);
  }
  return lines;
}

const FULL: Box = [0, 0, 1, 1];

registerOp<PageWords[]>({
  name: PDF_WORDS_OP,
  kind: "hint",
  family: "pdf",
  parse: (bytes) => allPages(bytes),
  hint: (pages, r) => {
    const on = r.whole ? pages : r.page !== undefined ? pages.filter((p) => p.page === r.page) : [];
    if (!on.length || r.path !== undefined) return null;
    const texts: string[] = [];
    const units: { text: string; at: string }[] = [];
    for (const p of on) {
      const lines = linesInBox(p.words, r.bbox ?? FULL);
      texts.push(lines.map((l) => l.map((w) => w.text).join(" ")).join("\n"));
      for (const w of lines.flat()) units.push({ text: w.text, at: `page=${p.page}&bbox=${w.bbox.join(",")}` });
    }
    return { text: texts.filter(Boolean).join("\n"), units };
  },
});
