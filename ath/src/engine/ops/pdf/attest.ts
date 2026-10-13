// attest.ts — what a PDF is: page count, file version, the first page's size in points, the /Info strings, sha256.
import { sha256Hex } from "../../../lib/hash.ts";
import { type AttestResult, registerAttester } from "../registry.ts";
import { fileVersion, metaText, openPdf, pageSize, pdfDate } from "./pdfium.ts";

export async function attestPdf(bytes: Uint8Array, mime: string): Promise<AttestResult> {
  const d = await openPdf(bytes);
  try {
    const info: Record<string, string> = {};
    for (const k of ["Title", "Author", "Subject", "Keywords", "Creator", "Producer", "CreationDate", "ModDate"]) {
      const v = metaText(d, k);
      if (v) info[k] = k.endsWith("Date") ? pdfDate(v) : v;
    }
    const [w, h] = d.pages > 0 ? pageSize(d, 0) : [0, 0];
    const value: Record<string, unknown> = {
      mime,
      bytes: bytes.length,
      page_count: d.pages,
      pdf_version: fileVersion(d) ?? undefined,
      page_size_pt: [Math.round(w * 100) / 100, Math.round(h * 100) / 100],
    };
    if (Object.keys(info).length) value.info = info;
    value.sha256 = sha256Hex(bytes);
    if (value.pdf_version === undefined) delete value.pdf_version;
    return { value };
  } finally {
    d.close();
  }
}

registerAttester("application/pdf", attestPdf);
