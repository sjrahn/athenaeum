// The streaming hasher: a minimal two-method interface (update / digest) with a hash-wasm
// BLAKE3 implementation. The interface is the leaf-swap point — a native binding can
// replace the factory without touching the scanner if an NVMe-backed residence ever
// out-runs WASM's ~1 GB/s. hashing is in-process by settled design: the pipeline is
// disk-bound, so WASM throughput is sufficient and the embedded-binary hazards
// (temp-extraction, noexec mounts, per-arch blobs, spawn management) are avoided.

import { createBLAKE3, type IHasher } from "hash-wasm";

export interface Hasher {
  /** Feed a chunk. hash-wasm copies into WASM memory synchronously, so the caller may reuse the buffer. */
  update(chunk: Uint8Array): void;
  /** Finalize and return the lowercase hex digest. Single-use; discard after calling. */
  digest(): string;
}

export interface HasherFactory {
  readonly name: string;
  /** A fresh, initialized hasher for one file. */
  create(): Promise<Hasher>;
}

/** BLAKE3-256 via hash-wasm, in-process. */
export const blake3Factory: HasherFactory = {
  name: "hash-wasm/blake3",
  async create(): Promise<Hasher> {
    const h: IHasher = await createBLAKE3();
    h.init();
    return {
      update: (chunk) => h.update(chunk),
      digest: () => h.digest("hex"),
    };
  },
};

/**
 * Wraps a factory to count how many hashers it hands out — i.e. how many files were
 * actually hashed. Tests assert this stays at zero across renames and hardlink discovery.
 */
export function countingFactory(inner: HasherFactory): HasherFactory & { readonly count: number } {
  let count = 0;
  return {
    name: inner.name,
    get count() {
      return count;
    },
    async create() {
      count++;
      return inner.create();
    },
  };
}
