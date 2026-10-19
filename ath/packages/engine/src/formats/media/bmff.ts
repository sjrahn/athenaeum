// bmff.ts — the ISO base media file format's boxes (ISO/IEC 14496-12), read from the bytes: what MP4, QuickTime,
// 3GPP, M4A, HEIC and AVIF are made of. A box is a size, a four-character type and a payload; a full box adds a
// version and flags. Nothing is decoded here beyond the box headers.
import { AthError } from "@ath/kit/errors.ts";

export interface Box {
  type: string;
  /** Offset of the box header. */
  start: number;
  /** Offset of the payload (after size, type, and a 64-bit size where present). */
  body: number;
  end: number;
}

const fourcc = (b: Uint8Array, p: number) => String.fromCharCode(b[p]!, b[p + 1]!, b[p + 2]!, b[p + 3]!);
export const u8 = (b: Uint8Array, p: number) => b[p]!;
export const u16 = (b: Uint8Array, p: number) => (b[p]! << 8) | b[p + 1]!;
export const u24 = (b: Uint8Array, p: number) => (b[p]! << 16) | (b[p + 1]! << 8) | b[p + 2]!;
export const u32 = (b: Uint8Array, p: number) => ((b[p]! << 24) | (b[p + 1]! << 16) | (b[p + 2]! << 8) | b[p + 3]!) >>> 0;
export const u64 = (b: Uint8Array, p: number) => u32(b, p) * 2 ** 32 + u32(b, p + 4);
export const str4 = fourcc;

/** The boxes directly inside [from, to). */
export function boxes(b: Uint8Array, from: number, to: number): Box[] {
  const out: Box[] = [];
  let p = from;
  while (p + 8 <= to) {
    let size = u32(b, p);
    const type = fourcc(b, p + 4);
    let body = p + 8;
    if (size === 1) {
      if (p + 16 > to) break;
      size = u64(b, p + 8);
      body = p + 16;
    } else if (size === 0) size = to - p;
    if (size < body - p || p + size > to) throw new AthError("CONFLICT", `bmff: box '${type}' at ${p} runs past its parent`);
    out.push({ type, start: p, body, end: p + size });
    p += size;
  }
  return out;
}

/** The first child of `parent` with `type`, or null. Children of a full box start after its version and flags. */
export function child(b: Uint8Array, parent: Box | null, type: string, skip = 0): Box | null {
  if (!parent) return null;
  return boxes(b, parent.body + skip, parent.end).find((x) => x.type === type) ?? null;
}

export function children(b: Uint8Array, parent: Box, type: string, skip = 0): Box[] {
  return boxes(b, parent.body + skip, parent.end).filter((x) => x.type === type);
}

/** Follow a path of box types from the top level: `path(b, "moov", "trak")`. */
export function top(b: Uint8Array, type: string): Box | null {
  return boxes(b, 0, b.length).find((x) => x.type === type) ?? null;
}

/** A full box's version. */
export const version = (b: Uint8Array, box: Box) => b[box.body]!;
