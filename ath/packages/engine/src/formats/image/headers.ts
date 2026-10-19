// headers.ts — what a raster is, from its header alone: dimensions (JPEG SOF, PNG IHDR, GIF, WebP) and the EXIF
// orientation of a JPEG. No decoder: boxes on a raster are in the stored frame, orientation rides on the reading.
import { type AttestResult, registerAttester } from "../registry.ts";

export interface Dims {
  width: number;
  height: number;
  orientation?: number;
}

function jpegDims(b: Uint8Array): Dims | null {
  let i = 2;
  let orientation: number | undefined;
  while (i + 4 <= b.length) {
    if (b[i] !== 0xff) {
      i++;
      continue;
    }
    const marker = b[i + 1]!;
    if (marker === 0xd8 || (marker >= 0xd0 && marker <= 0xd7) || marker === 0x01 || marker === 0xff) {
      i += 2;
      continue;
    }
    const len = (b[i + 2]! << 8) | b[i + 3]!;
    if (marker === 0xe1 && b[i + 4] === 0x45 && b[i + 5] === 0x78 && b[i + 6] === 0x69 && b[i + 7] === 0x66) {
      // Exif: TIFF header at i+10
      const t = i + 10;
      const le = b[t] === 0x49 && b[t + 1] === 0x49;
      const u16 = (p: number) => (le ? b[p]! | (b[p + 1]! << 8) : (b[p]! << 8) | b[p + 1]!);
      const u32 = (p: number) =>
        le
          ? (b[p]! | (b[p + 1]! << 8) | (b[p + 2]! << 16) | (b[p + 3]! << 24)) >>> 0
          : ((b[p]! << 24) | (b[p + 1]! << 16) | (b[p + 2]! << 8) | b[p + 3]!) >>> 0;
      const ifd = t + u32(t + 4);
      if (ifd + 2 <= b.length) {
        const n = u16(ifd);
        for (let k = 0; k < n; k++) {
          const e = ifd + 2 + k * 12;
          if (e + 12 > b.length) break;
          if (u16(e) === 0x0112) orientation = u16(e + 8);
        }
      }
    }
    if (
      (marker >= 0xc0 && marker <= 0xc3) ||
      (marker >= 0xc5 && marker <= 0xc7) ||
      (marker >= 0xc9 && marker <= 0xcb) ||
      (marker >= 0xcd && marker <= 0xcf)
    ) {
      const height = (b[i + 5]! << 8) | b[i + 6]!;
      const width = (b[i + 7]! << 8) | b[i + 8]!;
      return orientation !== undefined ? { width, height, orientation } : { width, height };
    }
    i += 2 + len;
  }
  return null;
}

function pngDims(b: Uint8Array): Dims | null {
  if (b.length < 24) return null;
  const u32 = (p: number) => ((b[p]! << 24) | (b[p + 1]! << 16) | (b[p + 2]! << 8) | b[p + 3]!) >>> 0;
  return { width: u32(16), height: u32(20) };
}

function gifDims(b: Uint8Array): Dims | null {
  if (b.length < 10) return null;
  return { width: b[6]! | (b[7]! << 8), height: b[8]! | (b[9]! << 8) };
}

export function imageDims(mime: string, b: Uint8Array): Dims | null {
  if (mime === "image/jpeg") return jpegDims(b);
  if (mime === "image/png") return pngDims(b);
  if (mime === "image/gif") return gifDims(b);
  return null;
}

export async function attestImage(bytes: Uint8Array, mime: string): Promise<AttestResult> {
  const d = imageDims(mime, bytes);
  const value: Record<string, unknown> = { mime, bytes: bytes.length };
  if (d) {
    value.width = d.width;
    value.height = d.height;
    if (d.orientation !== undefined && d.orientation !== 1) value.orientation = d.orientation;
  }
  return { value };
}

registerAttester("image/*", attestImage);
