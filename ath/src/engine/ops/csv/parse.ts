// parse.ts — `csv.parse@1`: RFC 4180 over bytes, by hand, so the surface is pinned by this code and not a library's
// option defaults. Emits each logical row and cell with its byte span. A BOM is recorded and skipped; CRLF and LF
// both end a row; quoted fields may hold doubled quotes and newlines. `row=0` is the header (D-csv).
export const CSV_OP = "csv.parse@1";

export interface Cell {
  value: string;
  start: number;
  end: number;
}

export interface Row {
  index: number;
  start: number;
  end: number;
  cells: Cell[];
}

export interface CsvParse {
  bom: boolean;
  rows: Row[];
  /** The widest row. */
  cols: number;
}

export function parseCsv(bytes: Uint8Array): CsvParse {
  const text = new TextDecoder("utf-8", { ignoreBOM: true }).decode(bytes);
  // byte offset per code unit (prefix sum)
  const map = new Uint32Array(text.length + 1);
  let b = 0;
  for (let i = 0; i < text.length; i++) {
    map[i] = b;
    const c = text.charCodeAt(i);
    if (c < 0x80) b += 1;
    else if (c < 0x800) b += 2;
    else if (c >= 0xd800 && c <= 0xdbff) {
      b += 4;
      i++;
      map[i] = b;
    } else b += 3;
  }
  map[text.length] = b;

  const rows: Row[] = [];
  let i = 0;
  const bom = text.charCodeAt(0) === 0xfeff;
  if (bom) i = 1;
  let cols = 0;
  while (i < text.length) {
    const rowStart = i;
    const cells: Cell[] = [];
    let atRowEnd = false;
    while (!atRowEnd) {
      const cellStart = i;
      let value = "";
      if (text[i] === '"') {
        i++;
        for (;;) {
          const q = text.indexOf('"', i);
          if (q === -1) {
            value += text.slice(i);
            i = text.length;
            break;
          }
          value += text.slice(i, q);
          if (text[q + 1] === '"') {
            value += '"';
            i = q + 2;
          } else {
            i = q + 1;
            break;
          }
        }
      } else {
        let j = i;
        while (j < text.length && text[j] !== "," && text[j] !== "\n" && text[j] !== "\r") j++;
        value = text.slice(i, j);
        i = j;
      }
      cells.push({ value, start: map[cellStart]!, end: map[i]! });
      if (text[i] === ",") {
        i++;
        continue;
      }
      atRowEnd = true;
      if (text[i] === "\r") i++;
      if (text[i] === "\n") i++;
    }
    const rowEnd = i;
    if (cells.length === 1 && cells[0]!.value === "" && rowEnd === text.length && rows.length > 0 && rowStart === rowEnd) break;
    rows.push({ index: rows.length, start: map[rowStart]!, end: map[rowEnd]!, cells });
    cols = Math.max(cols, cells.length);
  }
  return { bom, rows, cols };
}

/** The surface for a quote at `row=N[&col=M]`: a cell's value, or the row's cells joined by tabs. */
export function csvSurface(p: CsvParse, row: number, col?: number): string | null {
  const r = p.rows[row];
  if (!r) return null;
  if (col === undefined) return r.cells.map((c) => c.value).join("\t");
  return r.cells[col]?.value ?? null;
}
