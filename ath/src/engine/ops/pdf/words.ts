// words.ts — `pdf.words@1`, the quote surface of a PDF scope: the text layer's characters grouped into words with a
// box each (the same pdfium calls v52's pypdfium2 wrapped, so boxes agree to rounding), lines banded on the
// baseline, words-in-box in column-aware reading order, and chrome by repetition across pages (D-chrome).
import { type Box, DECIMALS, pointInBox, SLACK } from "../../model/address.ts";
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
const CHROME_PAGE_RATIO = 0.4;
const r4 = (n: number) => Math.round(n * 10 ** DECIMALS) / 10 ** DECIMALS;

/** Characters → words and lines for page `index0`. Origin top-left, boxes as fractions of the page. */
export function pageWords(d: PdfDoc, index0: number): PageWords {
  const m = d.m;
  const page = m.FPDF_LoadPage(d.doc, index0);
  const tp = m.FPDFText_LoadPage(page);
  const width = m.FPDF_GetPageWidthF(page);
  const height = m.FPDF_GetPageHeightF(page);
  const buf = m.pdfium.wasmExports.malloc(32);
  const words: Word[] = [];
  const lines: Line[] = [];
  try {
    const n = m.FPDFText_CountChars(tp);
    let chars = "";
    let box: [number, number, number, number] | null = null; // left, bottom, right, top in points
    const flush = () => {
      if (chars && box && width > 0 && height > 0) {
        const [left, bottom, right, top] = box;
        words.push({
          text: chars,
          bbox: [r4(left / width), r4((height - top) / height), r4((right - left) / width), r4((top - bottom) / height)],
        });
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
      if (!m.FPDFText_GetCharBox(tp, i, buf, buf + 8, buf + 16, buf + 24)) continue;
      const left = m.pdfium.getValue(buf, "double");
      const right = m.pdfium.getValue(buf + 8, "double");
      const bottom = m.pdfium.getValue(buf + 16, "double");
      const top = m.pdfium.getValue(buf + 24, "double");
      // lines (baseline banding)
      const base = 1 - bottom / height;
      if (cur && Math.abs(base - cur.base) > LINE_TOLERANCE) cur = null;
      if (!cur) {
        cur = { base, top: 1 - top / height, h: (top - bottom) / height, x0: left / width, x1: right / width, text: "" };
        lines.push(cur as unknown as Line);
      }
      cur.text += ch;
      cur.top = Math.min(cur.top, 1 - top / height);
      cur.h = Math.max(cur.h, (top - bottom) / height);
      cur.x0 = Math.min(cur.x0, left / width);
      cur.x1 = Math.max(cur.x1, right / width);
      // words
      if (/\s/.test(ch)) {
        flush();
        continue;
      }
      chars += ch;
      if (!box) box = [left, bottom, right, top];
      else {
        box[0] = Math.min(box[0], left);
        box[1] = Math.min(box[1], bottom);
        box[2] = Math.max(box[2], right);
        box[3] = Math.max(box[3], top);
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

export interface ChromeLine {
  page: number;
  box: Box;
  text: string;
  role: "running-header" | "running-footer" | "page-number";
}

const mask = (t: string) => t.replace(/\d+/g, "#");
const r3 = (n: number) => Math.round(n * 1000) / 1000;

/** Chrome by repetition: a line whose digit-masked text and 3-decimal box recur on ≥ max(3, 0.4·pages) pages. */
export function detectChrome(pages: readonly PageWords[]): ChromeLine[] {
  const seen = new Map<string, { pages: Set<number>; lines: { page: number; line: Line }[] }>();
  for (const p of pages) {
    for (const l of p.lines) {
      if (l.text.length >= 90) continue;
      const key = `${mask(l.text)}|${r3(l.y)}|${r3(l.x0)}`;
      const e = seen.get(key) ?? { pages: new Set(), lines: [] };
      e.pages.add(p.page);
      e.lines.push({ page: p.page, line: l });
      seen.set(key, e);
    }
  }
  const threshold = Math.max(3, pages.length * CHROME_PAGE_RATIO);
  const out: ChromeLine[] = [];
  for (const e of seen.values()) {
    if (e.pages.size < threshold) continue;
    for (const { page, line } of e.lines) {
      const role = /^(#\s+of\s+#|Page\s+#|#)$/.test(mask(line.text)) ? "page-number" : line.y < 0.5 ? "running-header" : "running-footer";
      out.push({ page, box: [line.x0, line.y, r4(line.x1 - line.x0), line.h], text: line.text, role });
    }
  }
  return out.sort((a, b) => a.page - b.page || a.box[1] - b.box[1]);
}

export function isChromeWord(chrome: readonly ChromeLine[], page: number, w: Word): boolean {
  const cx = w.bbox[0] + w.bbox[2] / 2;
  const cy = w.bbox[1] + w.bbox[3] / 2;
  return chrome.some((c) => c.page === page && pointInBox(c.box, cx, cy, 0.004));
}
