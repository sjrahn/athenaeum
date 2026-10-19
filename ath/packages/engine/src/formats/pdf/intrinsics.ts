// intrinsics.ts — what a PDF defines about itself (spec §10.2): its version, its page count, each page's size in
// points as displayed — the crop box with the page's rotation applied, the frame `bbox` is normalised in — and the
// document information dictionary as recorded.
import type { IntrinsicsResult, J } from "../format.ts";
import { fileVersion, metaText, openPdf, pageSize } from "./pdfium.ts";

const INFO = ["Title", "Author", "Subject", "Keywords", "Creator", "Producer", "CreationDate", "ModDate", "Trapped"];
const r2 = (n: number) => Math.round(n * 100) / 100;

export async function pdfIntrinsics(bytes: Uint8Array): Promise<IntrinsicsResult> {
  const d = await openPdf(bytes);
  try {
    const facts: J = {};
    const v = fileVersion(d);
    if (v) facts.pdf_version = v;
    facts.page_count = d.pages;
    facts.page_sizes = Array.from({ length: d.pages }, (_, i) => pageSize(d, i).map(r2));
    const info: J = {};
    for (const k of INFO) {
      const s = metaText(d, k);
      if (s) info[k] = s;
    }
    if (Object.keys(info).length) facts.info = info;
    return { facts };
  } finally {
    d.close();
  }
}
