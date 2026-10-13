// bytes.ts — the content-addressed store: <layer>/corpus/bytes/<ab>/<blake3>. Part IV (custody) is carried unchanged;
// this is the one local residence a layer holds. Resolution walks the chain top-down.
import { copyFileSync, existsSync, mkdirSync, symlinkSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import type { Chain, Layer } from "./config.ts";

export const bytesPath = (layer: Layer, blake3: string) => join(layer.root, "corpus", "bytes", blake3.slice(0, 2), blake3);

/** Where an artifact's bytes resolve in the chain, top-down, or null. */
export function resolveBytes(chain: Chain, blake3: string): string | null {
  for (let i = chain.layers.length - 1; i >= 0; i--) {
    const p = bytesPath(chain.layers[i]!, blake3);
    if (existsSync(p)) return p;
  }
  return null;
}

/** Place bytes in the top layer: a copy by default, a symlink to the source with `link`. Idempotent. */
export function placeBytes(chain: Chain, blake3: string, source: string, link = false): string {
  const p = bytesPath(chain.top, blake3);
  if (existsSync(p)) return p;
  mkdirSync(dirname(p), { recursive: true });
  if (link) symlinkSync(resolve(source), p);
  else copyFileSync(source, p);
  return p;
}
