// intrinsics.ts — what a delimited sheet defines about itself (spec §10.2): its physical rows, its columns (the
// widest row), its delimiter, whether a byte-order mark is present. Which row is a header is a shape's to say.
import type { IntrinsicsResult } from "../format.ts";
import { delimiterFor, parseCsv } from "./parse.ts";

export function csvIntrinsics(bytes: Uint8Array, mime: string): IntrinsicsResult {
  const delimiter = delimiterFor(mime);
  const p = parseCsv(bytes, delimiter);
  return { encoding: "utf-8", facts: { rows: p.rows.length, columns: p.cols, delimiter, bom: p.bom } };
}
