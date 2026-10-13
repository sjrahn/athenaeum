// hash.ts — BLAKE3 (hash-wasm, the scanner's choice): artifact identity over bytes, a reading's rev over its body,
// the ontology pin over its canonical serialisation. Also sha256/md5 for attests, through the runtime's own hasher.
import { createBLAKE3 } from "hash-wasm";
import { compactJson } from "./jsonl.ts";

type Hasher = Awaited<ReturnType<typeof createBLAKE3>>;
let shared: Promise<Hasher> | null = null;
const hasher = (): Promise<Hasher> => (shared ??= createBLAKE3());

export async function blake3Hex(bytes: Uint8Array | string): Promise<string> {
  const h = await hasher();
  h.init();
  h.update(typeof bytes === "string" ? new TextEncoder().encode(bytes) : bytes);
  return h.digest("hex");
}

/** Streaming hash of a file; the identity of an artifact. */
export async function blake3File(path: string): Promise<{ blake3: string; bytes: number }> {
  const h = await hasher();
  h.init();
  let n = 0;
  const stream = Bun.file(path).stream();
  for await (const chunk of stream) {
    h.update(chunk);
    n += chunk.byteLength;
  }
  return { blake3: h.digest("hex"), bytes: n };
}

/** A reading's revision: `b3:` + the first 16 hex of BLAKE3 over the body — a string as UTF-8, anything else as compact JSON. */
export async function bodyRev(body: unknown): Promise<string> {
  const s = typeof body === "string" ? body : compactJson(body);
  return `b3:${(await blake3Hex(s)).slice(0, 16)}`;
}

export function sha256Hex(bytes: Uint8Array): string {
  return new Bun.CryptoHasher("sha256").update(bytes).digest("hex");
}

export function md5Hex(bytes: Uint8Array): string {
  return new Bun.CryptoHasher("md5").update(bytes).digest("hex");
}

export const isBlake3 = (s: string): boolean => /^[0-9a-f]{64}$/.test(s);
