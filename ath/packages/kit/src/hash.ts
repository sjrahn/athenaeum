// hash.ts — BLAKE3 (hash-wasm, the scanner's choice): an artifact's identity over its bytes (§7.1), a reading's
// revision over its body (§6.5), a pin over a vocabulary (§11.8). sha256 for what a format defines with one.
import { createBLAKE3 } from "hash-wasm";
import { canonicalJson } from "./canonical.ts";

type Hasher = Awaited<ReturnType<typeof createBLAKE3>>;
let shared: Promise<Hasher> | null = null;
const hasher = (): Promise<Hasher> => (shared ??= createBLAKE3());

export async function blake3Hex(bytes: Uint8Array | string): Promise<string> {
  const h = await hasher();
  h.init();
  h.update(typeof bytes === "string" ? new TextEncoder().encode(bytes) : bytes);
  return h.digest("hex");
}

/** An incremental BLAKE3, for hashing a stream as it is read or written (§18.1 guarantee 2). */
export async function blake3Stream(): Promise<{ update(chunk: Uint8Array): void; digest(): string }> {
  const h = await createBLAKE3();
  h.init();
  return { update: (c) => void h.update(c), digest: () => h.digest("hex") };
}

/** Streaming hash of a file; the identity of an artifact. */
export async function blake3File(path: string): Promise<{ blake3: string; bytes: number }> {
  const h = await blake3Stream();
  let n = 0;
  for await (const chunk of Bun.file(path).stream()) {
    h.update(chunk);
    n += chunk.byteLength;
  }
  return { blake3: h.digest(), bytes: n };
}

/** `b3:` and the first 16 hex digits of the BLAKE3 of a string (UTF-8) or a JSON value (canonical form): a revision, a pin. */
export async function short(body: unknown): Promise<string> {
  const s = typeof body === "string" ? body : canonicalJson(body);
  return `b3:${(await blake3Hex(s)).slice(0, 16)}`;
}

export function sha256Hex(bytes: Uint8Array): string {
  return new Bun.CryptoHasher("sha256").update(bytes).digest("hex");
}

export const isBlake3 = (s: string): boolean => /^[0-9a-f]{64}$/.test(s);
