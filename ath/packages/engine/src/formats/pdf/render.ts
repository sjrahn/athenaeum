// render.ts — a PDF page as a reader sees it: the page rendered by pdfium at a scale, in the displayed frame (its
// crop box, its rotation applied), cropped to a box when one is given, encoded as PNG. A reader looks at this; it is
// never a reading and never stored (§8.3.6).
import { deflateSync } from "node:zlib";
import { AthError } from "@ath/kit/errors.ts";
import type { Box } from "../../address/address.ts";
import { openPdf } from "./pdfium.ts";

const CRC = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(b: Uint8Array): number {
  let c = 0xffffffff;
  for (const x of b) c = CRC[(c ^ x) & 0xff]! ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function chunk(type: string, data: Uint8Array): Uint8Array {
  const out = new Uint8Array(12 + data.length);
  const dv = new DataView(out.buffer);
  dv.setUint32(0, data.length);
  out.set(new TextEncoder().encode(type), 4);
  out.set(data, 8);
  dv.setUint32(8 + data.length, crc32(out.subarray(4, 8 + data.length)));
  return out;
}

/** RGB rows → a PNG. */
export function encodePng(width: number, height: number, rgb: Uint8Array): Uint8Array {
  const raw = new Uint8Array((width * 3 + 1) * height);
  for (let y = 0; y < height; y++) raw.set(rgb.subarray(y * width * 3, (y + 1) * width * 3), y * (width * 3 + 1) + 1);
  const ihdr = new Uint8Array(13);
  const dv = new DataView(ihdr.buffer);
  dv.setUint32(0, width);
  dv.setUint32(4, height);
  ihdr.set([8, 2, 0, 0, 0], 8);
  const sig = Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  return Buffer.concat([sig, chunk("IHDR", ihdr), chunk("IDAT", new Uint8Array(deflateSync(raw))), chunk("IEND", new Uint8Array())]);
}

/** Page `page` (1-based) at `scale` pixels per point, cropped to `box` (0–1 of the displayed frame) when given. */
export async function renderPage(bytes: Uint8Array, page: number, scale = 2, box?: Box): Promise<Uint8Array> {
  const d = await openPdf(bytes);
  const m = d.m;
  try {
    if (page < 1 || page > d.pages) throw new AthError("USAGE", `page ${page} is past the document's ${d.pages} pages`);
    const p = m.FPDF_LoadPage(d.doc, page - 1);
    try {
      const W = Math.max(1, Math.round(m.FPDF_GetPageWidthF(p) * scale));
      const H = Math.max(1, Math.round(m.FPDF_GetPageHeightF(p) * scale));
      const bmp = m.FPDFBitmap_Create(W, H, 0);
      try {
        m.FPDFBitmap_FillRect(bmp, 0, 0, W, H, 0xffffffff);
        m.FPDF_RenderPageBitmap(bmp, p, 0, 0, W, H, 0, 0x01 | 0x10);
        const stride = m.FPDFBitmap_GetStride(bmp);
        const buf = m.FPDFBitmap_GetBuffer(bmp);
        const heap = (m.pdfium as unknown as { HEAPU8: Uint8Array }).HEAPU8;
        const [x0, y0, x1, y1] = box
          ? [Math.floor(box[0] * W), Math.floor(box[1] * H), Math.ceil((box[0] + box[2]) * W), Math.ceil((box[1] + box[3]) * H)]
          : [0, 0, W, H];
        const w = Math.max(1, Math.min(W, x1) - x0);
        const h = Math.max(1, Math.min(H, y1) - y0);
        const rgb = new Uint8Array(w * h * 3);
        for (let y = 0; y < h; y++)
          for (let x = 0; x < w; x++) {
            const s = buf + (y0 + y) * stride + (x0 + x) * 4;
            const o = (y * w + x) * 3;
            rgb[o] = heap[s + 2]!;
            rgb[o + 1] = heap[s + 1]!;
            rgb[o + 2] = heap[s]!;
          }
        return encodePng(w, h, rgb);
      } finally {
        m.FPDFBitmap_Destroy(bmp);
      }
    } finally {
      m.FPDF_ClosePage(p);
    }
  } finally {
    d.close();
  }
}
