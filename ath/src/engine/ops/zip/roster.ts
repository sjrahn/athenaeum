// roster.ts — a zip's member roster (spec §5.1): every member's path, size and blake3; each member becomes its own
// subject whose captured_from names the container and path. yauzl reads the central directory; nothing is extracted
// to disk here.
import { Buffer } from "node:buffer";
import { fromBufferPromise, type ZipFile } from "yauzl";
import { blake3Hex } from "../../../lib/hash.ts";
import { type AttestResult, registerAttester } from "../registry.ts";

export interface MemberBytes {
  path: string;
  bytes: Uint8Array;
  blake3: string;
}

async function readAll(zip: ZipFile, entry: Parameters<ZipFile["openReadStream"]>[0]): Promise<Uint8Array> {
  const stream = await new Promise<NodeJS.ReadableStream>((res, rej) => zip.openReadStream(entry, (e, s) => (e ? rej(e) : res(s))));
  const chunks: Uint8Array[] = [];
  for await (const c of stream) chunks.push(typeof c === "string" ? new TextEncoder().encode(c) : new Uint8Array(c));
  const out = new Uint8Array(chunks.reduce((n, c) => n + c.length, 0));
  let o = 0;
  for (const c of chunks) {
    out.set(c, o);
    o += c.length;
  }
  return out;
}

export async function zipMembers(bytes: Uint8Array): Promise<MemberBytes[]> {
  const zip = await fromBufferPromise(Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength), { lazyEntries: true });
  const out: MemberBytes[] = [];
  await new Promise<void>((resolve, reject) => {
    zip.on("entry", (entry) => {
      void (async () => {
        try {
          if (!entry.fileName.endsWith("/")) {
            const b = await readAll(zip, entry);
            out.push({ path: entry.fileName, bytes: b, blake3: await blake3Hex(b) });
          }
          zip.readEntry();
        } catch (e) {
          reject(e);
        }
      })();
    });
    zip.on("end", resolve);
    zip.on("error", reject);
    zip.readEntry();
  });
  zip.close();
  return out;
}

export async function attestZip(bytes: Uint8Array, mime: string): Promise<AttestResult> {
  const members = await zipMembers(bytes);
  return {
    value: {
      mime,
      bytes: bytes.length,
      members: members.map((m) => ({ path: m.path, bytes: m.bytes.length, blake3: m.blake3 })),
    },
    members,
  };
}

registerAttester("application/zip", attestZip);
registerAttester("application/epub+zip", attestZip);
