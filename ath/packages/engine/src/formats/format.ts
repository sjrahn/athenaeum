// format.ts — what the tooling knows of each format it registers (spec §10.4.3): its class, the axes of its addresses
// and which are physical, its surface or hint ops, whether it is a container, and its intrinsics op. Nothing here
// says what data means. A format with no row is held and addressable at `whole` only, and its intrinsics op is
// `bytes.intrinsics@1` (§10.4.4).
import { AthError } from "@ath/kit/errors.ts";

export type J = Record<string, unknown>;
export type FormatClass = "rendered" | "structured";
export type Axis = "page" | "bbox" | "bytes" | "row" | "col" | "t" | "path";

/** One constituent of a container (§7.2.2, §10.3): its path in the format's own terms, its hash, its kind, the fields
 * the format defines for it; a part also carries its own intrinsics. `read` yields its decoded bytes, never stored. */
export interface Constituent {
  path: string;
  blake3: string;
  kind: "asset" | "part";
  fields?: J;
  /** A part's own intrinsics, inline (§10.2.1). */
  intrinsics?: J;
  read: () => Uint8Array;
  /** The name the container gives it, to sniff by (§10.1.3). */
  name?: string;
}

/** What an intrinsics op yields: the format's facts (without `op`, `mime`, `bytes`, `encoding`, `constituents`, which
 * the registry adds in that order) and the constituents. */
export interface IntrinsicsResult {
  facts: J;
  encoding?: string;
  constituents?: Constituent[];
}

export interface Format {
  /** The format's name: the first word of its ops (`pdf` → `pdf.intrinsics@1`). */
  name: string;
  mimes: readonly string[];
  /** Absent on the fallback for formats with no row. */
  class?: FormatClass;
  axes: readonly Axis[];
  physical: readonly Axis[];
  /** The surface op (structured) or the hint ops (rendered) the format gives (§10.5, §10.6). */
  ops: readonly string[];
  container: "assets" | "parts" | "both" | null;
  /** Its intrinsics op's version; the op is `<name>.intrinsics@<version>` (§10.2.4). */
  version: number;
  intrinsics(bytes: Uint8Array, mime: string): Promise<IntrinsicsResult> | IntrinsicsResult;
}

const byMime = new Map<string, Format>();
const byName = new Map<string, Format>();

export function registerFormat(f: Format): void {
  if (byName.has(f.name)) throw new AthError("INTERNAL", `format ${f.name} is registered twice`);
  byName.set(f.name, f);
  for (const m of f.mimes) {
    if (byMime.has(m)) throw new AthError("INTERNAL", `mime ${m} belongs to two formats`);
    byMime.set(m, f);
  }
}

/** Every text mime with no row of its own is plain text (§10.4.4). */
const PLAIN_TEXT = /^text\//;

/** The format a mime belongs to: its row, plain text for any other text, else the fallback. */
export function formatOf(mime: string): Format {
  const f = byMime.get(mime);
  if (f) return f;
  if (PLAIN_TEXT.test(mime) && byName.has("text")) return byName.get("text")!;
  return byName.get("bytes")!;
}

export const formatNamed = (name: string): Format | undefined => byName.get(name);
export const formats = (): Format[] => [...byName.values()];
export const intrinsicsOp = (f: Format): string => `${f.name}.intrinsics@${f.version}`;

/** The op name and version of an `intrinsics` value's `op` (`pdf.intrinsics@1` → pdf, 1), or null. */
export function parseIntrinsicsOp(op: unknown): { name: string; version: number } | null {
  const m = typeof op === "string" ? /^([a-z0-9]+)\.intrinsics@([1-9]\d*)$/.exec(op) : null;
  return m ? { name: m[1]!, version: Number(m[2]) } : null;
}

/** A text encoding as the bytes declare it: a byte-order mark, else UTF-8 where the bytes are valid UTF-8, else
 * ISO-8859-1 (§10.2). */
export function textEncoding(b: Uint8Array): string {
  if (b[0] === 0xef && b[1] === 0xbb && b[2] === 0xbf) return "utf-8";
  if (b[0] === 0xff && b[1] === 0xfe) return "utf-16le";
  if (b[0] === 0xfe && b[1] === 0xff) return "utf-16be";
  try {
    new TextDecoder("utf-8", { fatal: true }).decode(b);
    return "utf-8";
  } catch {
    return "iso-8859-1";
  }
}

/** A constituent as its container's intrinsics list it: path, hash, kind, then what the format defines. */
export function constituentEntry(c: Constituent): J {
  return { path: c.path, blake3: c.blake3, kind: c.kind, ...(c.fields ?? {}), ...(c.intrinsics ? { intrinsics: c.intrinsics } : {}) };
}
