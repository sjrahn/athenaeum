// context.ts — what a command needs from its kit context: the loaded chain (from the root the kit found) and the
// ontology as loaded, each once per invocation.
import { AthError } from "../kit/errors.ts";
import type { KitCtx } from "../kit/types.ts";
import { type Chain, loadChain } from "./layer/config.ts";
import { loadOntology, type Ontology } from "./ontology/load.ts";

export function openChain(ctx: KitCtx): Chain {
  if (!ctx.root)
    throw new AthError(
      "CONFIG",
      "no layer here (--root PATH, $ATHENAEUM_ROOT, or an athenaeum.yaml above the cwd; `ath layer init` makes one)",
    );
  return loadChain(ctx.root);
}

export function openOntology(chain: Chain): Ontology {
  return loadOntology(chain);
}

export const BLAKE3_RE = /^[0-9a-f]{64}$/;

export function requireBlake3(s: string): string {
  const v = s.replace(/^corpus:\/\//, "").split("?")[0]!;
  if (!BLAKE3_RE.test(v)) throw new AthError("USAGE", `not a blake3 subject: '${s}'`);
  return v;
}
