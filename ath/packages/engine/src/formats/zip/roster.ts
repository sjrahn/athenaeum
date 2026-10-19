// roster.ts — a zip's entries (spec §10.3): every file entry's name and decoded bytes. A reader of our own over the
// central directory, so the op is pinned by this code: store (0), deflate (8) and zstd (93); a ZIP64 archive is
// refused rather than misread.
import { inflateRawSync } from "node:zlib";
import { AthError } from "@ath/kit/errors.ts";
import { blake3Hex } from "@ath/kit/hash.ts";

export interface MemberBytes {
  path: string;
  bytes: Uint8Array;
  blake3: string;
}

interface Entry {
  path: string;
  method: number;
  compressed: number;
  size: number;
  localOffset: number;
  flags: number;
}

const u16 = (b: Uint8Array, p: number) => b[p]! | (b[p + 1]! << 8);
const u32 = (b: Uint8Array, p: number) => (b[p]! | (b[p + 1]! << 8) | (b[p + 2]! << 16) | (b[p + 3]! << 24)) >>> 0;

function findEocd(b: Uint8Array): number {
  const min = Math.max(0, b.length - 22 - 65535);
  for (let i = b.length - 22; i >= min; i--) if (u32(b, i) === 0x06054b50) return i;
  throw new AthError("CONFLICT", "zip: no end-of-central-directory record");
}

export function readCentralDirectory(b: Uint8Array): Entry[] {
  const eocd = findEocd(b);
  const count = u16(b, eocd + 10);
  const cdSize = u32(b, eocd + 12);
  const cdOffset = u32(b, eocd + 16);
  if (count === 0xffff || cdSize === 0xffffffff || cdOffset === 0xffffffff)
    throw new AthError("CONFLICT", "zip: zip64 archives are not supported yet");
  const out: Entry[] = [];
  let p = cdOffset;
  const dec = new TextDecoder("utf-8");
  const latin = new TextDecoder("latin1");
  for (let i = 0; i < count; i++) {
    if (u32(b, p) !== 0x02014b50) throw new AthError("CONFLICT", `zip: bad central directory entry at ${p}`);
    const flags = u16(b, p + 8);
    const method = u16(b, p + 10);
    const compressed = u32(b, p + 20);
    const size = u32(b, p + 24);
    const nameLen = u16(b, p + 28);
    const extraLen = u16(b, p + 30);
    const commentLen = u16(b, p + 32);
    const localOffset = u32(b, p + 42);
    const nameBytes = b.subarray(p + 46, p + 46 + nameLen);
    const path = flags & 0x800 ? dec.decode(nameBytes) : latin.decode(nameBytes);
    if (compressed === 0xffffffff || size === 0xffffffff || localOffset === 0xffffffff)
      throw new AthError("CONFLICT", "zip: zip64 entries are not supported yet");
    out.push({ path, method, compressed, size, localOffset, flags });
    p += 46 + nameLen + extraLen + commentLen;
  }
  return out;
}

function memberData(b: Uint8Array, e: Entry): Uint8Array {
  const p = e.localOffset;
  if (u32(b, p) !== 0x04034b50) throw new AthError("CONFLICT", `zip: bad local header for ${e.path}`);
  const nameLen = u16(b, p + 26);
  const extraLen = u16(b, p + 28);
  const start = p + 30 + nameLen + extraLen;
  const raw = b.subarray(start, start + e.compressed);
  switch (e.method) {
    case 0:
      return raw;
    case 8:
      return new Uint8Array(inflateRawSync(raw));
    case 93:
      return new Uint8Array(Bun.zstdDecompressSync(raw));
    default:
      throw new AthError("CONFLICT", `zip: ${e.path} uses compression method ${e.method}, which is not supported`);
  }
}

export async function zipMembers(bytes: Uint8Array): Promise<MemberBytes[]> {
  const out: MemberBytes[] = [];
  for (const e of readCentralDirectory(bytes)) {
    if (e.path.endsWith("/")) continue;
    const data = memberData(bytes, e);
    if (data.length !== e.size) throw new AthError("CONFLICT", `zip: ${e.path} decompressed to ${data.length} bytes, expected ${e.size}`);
    out.push({ path: e.path, bytes: data, blake3: await blake3Hex(data) });
  }
  return out;
}

/** Every file entry with its hash, decoded once to hash it and again only when read. */
export async function zipEntries(bytes: Uint8Array): Promise<{ path: string; blake3: string; read: () => Uint8Array }[]> {
  const out: { path: string; blake3: string; read: () => Uint8Array }[] = [];
  for (const e of readCentralDirectory(bytes)) {
    if (e.path.endsWith("/")) continue;
    const read = () => {
      const data = memberData(bytes, e);
      if (data.length !== e.size) throw new AthError("CONFLICT", `zip: ${e.path} decompressed to ${data.length} bytes, expected ${e.size}`);
      return data;
    };
    out.push({ path: e.path, blake3: await blake3Hex(read()), read });
  }
  return out;
}
