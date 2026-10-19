// resolve.ts — resolution (spec §18.8): a BLAKE3 resolves through whichever route holds it, cheapest first — the
// local store, the other managed stores by declared cost, observed trees, the constituent route (the container
// resolved, then the constituent extracted), then the stores of every base — and every read is verified (§18.1). The first route whose bytes verify wins; if none does, resolution
// fails. Resolution reports the route it took, nested through containers, and every other residence the index knows.
// Custody knows no format: the containers of a hash and the extraction of a constituent are handed in.
import { AthError } from "@ath/kit/errors.ts";
import { blake3Hex } from "@ath/kit/hash.ts";
import type { CustodyIndex } from "./index-db.ts";
import type { Tree } from "./local.ts";

export interface Readable {
  id: string;
  name: string;
  tags: string[];
  get(tree: Tree, hash: string): Promise<Uint8Array | null>;
}

export interface ResolveDeps {
  /** The stores to try before the constituent route, cheapest first. */
  stores: Readable[];
  /** The stores to try after it: the bases' (§18.8.1). */
  later?: Readable[];
  /** The held containers that list `hash`, with its path in each. */
  containersOf(hash: string): { container: string; path: string }[];
  /** A constituent's bytes, decoded from its container's bytes; null when the container has no such path. */
  extract(container: Uint8Array, containerHash: string, path: string): Promise<Uint8Array | null>;
  index?: CustodyIndex;
}

export interface Trace {
  hash: string;
  route: "store" | "constituent";
  store?: { id: string; name: string; tags: string[] };
  within?: { path: string; container: Trace };
  /** Every residence the index knows, besides the route taken. */
  also: { store: string; state: string; verified_at: string | null }[];
}

export interface Resolved {
  bytes: Uint8Array;
  trace: Trace;
}

/** Resolve `hash` to verified bytes, or throw NOT_FOUND with every route tried. */
export async function resolveHash(
  hash: string,
  deps: ResolveDeps,
  tree: Tree = "artifacts",
  seen: Set<string> = new Set(),
): Promise<Resolved> {
  seen.add(hash);
  const tried: string[] = [];
  const also = (taken?: string) =>
    (deps.index?.copies(hash) ?? [])
      .filter((c) => c.store !== taken)
      .map((c) => ({ store: c.store, state: c.state, verified_at: c.verified_at }));
  const fromStores = async (stores: readonly Readable[]): Promise<Resolved | null> => {
    for (const s of stores) {
      let b: Uint8Array | null;
      try {
        b = await s.get(tree, hash);
      } catch (e) {
        tried.push(`${s.name}: ${(e as Error).message}`);
        continue;
      }
      if (!b) continue;
      if ((await blake3Hex(b)) !== hash) {
        tried.push(`${s.name}: its copy does not verify`);
        continue;
      }
      return { bytes: b, trace: { hash, route: "store", store: { id: s.id, name: s.name, tags: s.tags }, also: also(s.id) } };
    }
    return null;
  };
  const direct = await fromStores(deps.stores);
  if (direct) return direct;
  for (const c of tree === "artifacts" ? deps.containersOf(hash) : []) {
    if (seen.has(c.container)) continue;
    let outer: Resolved;
    try {
      outer = await resolveHash(c.container, deps, "artifacts", new Set(seen));
    } catch (e) {
      tried.push(`path=${c.path} in ${c.container}: ${(e as Error).message.split("\n")[0]}`);
      continue;
    }
    const b = await deps.extract(outer.bytes, c.container, c.path);
    if (!b || (await blake3Hex(b)) !== hash) {
      tried.push(`path=${c.path} in ${c.container}: the constituent does not verify`);
      continue;
    }
    return { bytes: b, trace: { hash, route: "constituent", within: { path: c.path, container: outer.trace }, also: also() } };
  }
  const later = await fromStores(deps.later ?? []);
  if (later) return later;
  throw new AthError("NOT_FOUND", `no route resolves ${hash}${tried.length ? `:\n  ${tried.join("\n  ")}` : ""}`, { tried });
}

/** The trace in the shape §18.8.2 prints it. */
export function traceLines(t: Trace, ind = ""): string[] {
  const head =
    t.route === "store"
      ? `${ind}${t.hash}  ← store ${t.store!.name} [${t.store!.tags.join(", ")}]`
      : `${ind}${t.hash}  ← path=${t.within!.path} in ${t.within!.container.hash}`;
  const out = [head];
  if (t.within)
    out.push(...traceLines(t.within.container, `${ind}    `).map((l, i) => (i === 0 ? l.replace(`${ind}    `, `${ind}    ← `) : l)));
  if (t.also.length)
    out.push(`${ind}   also: ${t.also.map((a) => `${a.store} ${a.state}${a.verified_at ? ` ${a.verified_at}` : ""}`).join(" · ")}`);
  return out;
}
