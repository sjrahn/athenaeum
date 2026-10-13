// attest.ts — what a CSV is: rows (data rows, header excluded), cols, header_row 0, encoding, BOM.
import { type AttestResult, registerAttester } from "../registry.ts";
import { parseCsv } from "./parse.ts";

export async function attestCsv(bytes: Uint8Array, mime: string): Promise<AttestResult> {
  const p = parseCsv(bytes);
  return {
    value: {
      mime,
      bytes: bytes.length,
      rows: Math.max(0, p.rows.length - 1),
      header_row: 0,
      cols: p.cols,
      encoding: "utf-8",
      ...(p.bom ? { bom: true } : {}),
    },
  };
}

registerAttester("text/csv", attestCsv);
registerAttester("text/tab-separated-values", attestCsv);
