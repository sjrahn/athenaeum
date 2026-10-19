// pdfium.ts — pdfium (the same engine as v52's pypdfium2) through @embedpdf/pdfium's wasm, embedded in the binary.
// One initialised module per process; documents are loaded from memory and must be closed.

import { AthError } from "@ath/kit/errors.ts";
import { init, type WrappedPdfiumModule } from "@embedpdf/pdfium";
import wasmPath from "@embedpdf/pdfium/pdfium.wasm" with { type: "file" };

let mod: Promise<WrappedPdfiumModule> | null = null;

export async function pdfium(): Promise<WrappedPdfiumModule> {
  if (!mod) {
    mod = (async () => {
      const wasmBinary = await Bun.file(wasmPath).arrayBuffer();
      const m = await init({ wasmBinary });
      m.FPDF_InitLibrary();
      return m;
    })();
  }
  return mod;
}

export interface PdfDoc {
  m: WrappedPdfiumModule;
  doc: number;
  ptr: number;
  pages: number;
  close(): void;
}

export async function openPdf(bytes: Uint8Array): Promise<PdfDoc> {
  const m = await pdfium();
  const ptr = m.pdfium.wasmExports.malloc(bytes.length);
  (m.pdfium as unknown as { HEAPU8: Uint8Array }).HEAPU8.set(bytes, ptr);
  const doc = m.FPDF_LoadMemDocument(ptr, bytes.length, "");
  if (!doc) {
    m.pdfium.wasmExports.free(ptr);
    throw new AthError("EXTERNAL", `pdfium could not open the document (error ${m.FPDF_GetLastError()})`);
  }
  return {
    m,
    doc,
    ptr,
    pages: m.FPDF_GetPageCount(doc),
    close() {
      m.FPDF_CloseDocument(doc);
      m.pdfium.wasmExports.free(ptr);
    },
  };
}

/** A document-info string (`Title`, `Author`, `Creator`, `Producer`, `CreationDate`, …) or null. */
export function metaText(d: PdfDoc, key: string): string | null {
  const m = d.m;
  const n = m.FPDF_GetMetaText(d.doc, key, 0, 0);
  if (n <= 2) return null;
  const buf = m.pdfium.wasmExports.malloc(n);
  try {
    m.FPDF_GetMetaText(d.doc, key, buf, n);
    const s = m.pdfium.UTF16ToString(buf);
    return s || null;
  } finally {
    m.pdfium.wasmExports.free(buf);
  }
}

export function fileVersion(d: PdfDoc): string | null {
  const m = d.m;
  const buf = m.pdfium.wasmExports.malloc(4);
  try {
    if (!m.FPDF_GetFileVersion(d.doc, buf)) return null;
    const v = m.pdfium.getValue(buf, "i32");
    return `${Math.floor(v / 10)}.${v % 10}`;
  } finally {
    m.pdfium.wasmExports.free(buf);
  }
}

export function pageSize(d: PdfDoc, index0: number): [number, number] {
  const m = d.m;
  const buf = m.pdfium.wasmExports.malloc(16);
  try {
    m.FPDF_GetPageSizeByIndexF(d.doc, index0, buf);
    return [m.pdfium.getValue(buf, "float"), m.pdfium.getValue(buf + 4, "float")];
  } finally {
    m.pdfium.wasmExports.free(buf);
  }
}

/** A PDF date (`D:20170927121839+02'00'`) as ISO-8601, or the raw string. */
export function pdfDate(s: string): string {
  const m = /^D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([Zz]|[+-]\d{2}'?\d{2}'?)?/.exec(s);
  if (!m) return s;
  const [, y, mo = "01", d = "01", h = "00", mi = "00", se = "00", tz] = m;
  let z = "Z";
  if (tz && tz !== "Z" && tz !== "z") z = `${tz[0]}${tz.slice(1, 3)}:${tz.slice(3).replace(/'/g, "").padEnd(2, "0")}`;
  return `${y}-${mo}-${d}T${h}:${mi}:${se}${z}`;
}
