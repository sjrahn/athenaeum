// sites.ts — custody as a verb sees it: the stores the instance and its bases declare, how this host reaches each
// (`access.yaml`), the host's local store, the policies of the chain, and for each artifact and testimony the
// instance holds its labels (§18.6.2) and every copy the index believes in, constituents held where their containers
// are (§18.6.3). Custody is handed all of it; it knows no record.
import { join } from "node:path";
import {
  type CopyView,
  type CustodyIndex,
  driverFor,
  type Holding,
  type Labels,
  type LocalDecl,
  type LocalStore,
  loadAccess,
  loadPolicies,
  loadStores,
  localDriver,
  openIndex,
  openLocalStore,
  type Policy,
  type Site,
  type StoreDecl,
  type Tree,
} from "@ath/custody";
import { entityView } from "@ath/engine/graph/entity.ts";
import { chain, containersIndex, entityNames, type Instance, ownRecords, recordView } from "@ath/engine/instance/instance.ts";
import { refinesChain } from "@ath/engine/vocab/load.ts";
import type { Vocabulary } from "@ath/engine/vocab/terms.ts";
import { AthError } from "@ath/kit/errors.ts";
import type { KitCtx } from "@ath/kit/types.ts";

export interface Sites {
  inst: Instance;
  store: LocalStore;
  index: CustodyIndex;
  local: LocalDecl;
  /** The local store as a declaration: managed, tagged `local` and what access.yaml adds, cost 0. */
  localDecl: StoreDecl;
  /** Every site: the local store first, then every declared store of the chain, the instance's own before its bases'. */
  sites: Site[];
  byId: Map<string, Site>;
  policies: Policy[];
  /** A store by name: `local`, the instance's own, then its bases'. */
  named(name: string): Site;
  close(): void;
}

export function openSites(ctx: KitCtx, inst: Instance, index?: CustodyIndex): Sites {
  const store = openLocalStore(ctx.host.data);
  const idx = index ?? openIndex(join(ctx.host.state, "index.sqlite"));
  const access = loadAccess(ctx.host.config);
  const roots = chain(inst).map((x) => ({ root: x.root, name: x.config.name }));
  const localDecl: StoreDecl = {
    name: "local",
    id: store.id,
    driver: "local",
    role: "managed",
    tags: ["local", ...access.local.tags.filter((t) => t !== "local")],
    encryption: "none",
    cost: 0,
    ...(access.local.evict !== undefined ? { evict: access.local.evict } : {}),
    ...(access.local.capacity !== undefined ? { capacity: access.local.capacity } : {}),
  };
  const sites: Site[] = [{ decl: localDecl, driver: localDriver(localDecl, store.dir) }];
  for (const d of loadStores(roots)) {
    if (d.id === store.id || sites.some((s) => s.decl.id === d.id)) continue;
    sites.push({ decl: d, driver: driverFor(d, access.stores.get(d.id)) });
  }
  const byId = new Map(sites.map((s) => [s.decl.id, s]));
  return {
    inst,
    store,
    index: idx,
    local: access.local,
    localDecl,
    sites,
    byId,
    policies: loadPolicies(roots),
    named(name) {
      const s = sites.find((x) => x.decl.name === name);
      if (!s) throw new AthError("NOT_FOUND", `no store ${name}: ${sites.map((x) => x.decl.name).join(", ")}`);
      return s;
    },
    close: () => {
      if (!index) idx.close();
    },
  };
}

/** Every copy the index believes in for a hash, as policies count them: direct, hardlinked (sharing the observed file's
 * storage), and through every container that holds it, transitively. A copy on a store no instance of the chain
 * declares is not counted. */
export function copyViews(s: Sites, hash: string, tree: Tree, containers = containersIndex(s.inst), seen = new Set<string>()): CopyView[] {
  seen.add(hash);
  const out: CopyView[] = [];
  for (const c of s.index.copies(hash)) {
    if (c.tree !== tree) continue;
    const site = s.byId.get(c.store);
    if (!site) continue;
    out.push({
      store: site.decl,
      state: c.state,
      verified_at: c.verified_at,
      via: c.link ? "linked" : "direct",
      physical: c.link ?? `${c.store}:${hash}`,
      held: hash,
      tree,
    });
  }
  if (tree === "artifacts")
    for (const ref of containers.get(hash) ?? []) {
      if (seen.has(ref.container)) continue;
      for (const c of copyViews(s, ref.container, "artifacts", containers, new Set(seen))) out.push({ ...c, via: "container" });
    }
  return out;
}

/** Which entities of the chain cite each hash, by their kinds (§18.6.2). */
export function citingKinds(inst: Instance): Map<string, Set<string>> {
  const out = new Map<string, Set<string>>();
  for (const name of entityNames(inst)) {
    const held = entityView(inst, name) ?? [];
    const kinds = held.filter((h) => h.line.pred === "is").map((h) => String(h.line.val));
    for (const h of held)
      for (const e of h.line.ev ?? []) {
        const m = /^ath:\/\/([0-9a-f]{64})/.exec(e.anchor);
        if (!m) continue;
        const set = out.get(m[1]!) ?? new Set<string>();
        for (const k of kinds) set.add(k);
        out.set(m[1]!, set);
      }
  }
  return out;
}

/** The labels of an artifact the chain holds: its shape and that shape's chain, its origins' producers, the kinds of the
 * entities citing it, its mime and size. */
export function artifactLabels(
  inst: Instance,
  vocab: Vocabulary,
  hash: string,
  shape: string | null,
  kinds: ReadonlySet<string> | undefined,
): Labels {
  const r = recordView(inst, hash)?.record;
  const tools = (r?.origins ?? [])
    .map((o) => (o as { producer?: { tool?: unknown } }).producer?.tool)
    .filter((t): t is string => typeof t === "string");
  return {
    shapes: shape ? refinesChain(vocab, "shapes", shape) : [],
    origins: [...new Set(tools)],
    kinds: [...(kinds ?? [])].sort(),
    mime: typeof r?.intrinsics?.mime === "string" ? r.intrinsics.mime : null,
    size: typeof r?.intrinsics?.bytes === "number" ? r.intrinsics.bytes : 0,
    testimony: false,
  };
}

export const testimonyLabels = (size: number): Labels => ({ shapes: [], origins: [], kinds: [], mime: null, size, testimony: true });

/** Everything the instance pointed at holds, with labels and copies: its records' artifacts, and every testimony its
 * receipts delivered, the receipts among them (§5.7). */
export async function holdingsOf(s: Sites, vocab: Vocabulary, shapeOf: (h: string) => Promise<string | null>): Promise<Holding[]> {
  const containers = containersIndex(s.inst);
  const kinds = citingKinds(s.inst);
  const out: Holding[] = [];
  for (const hash of ownRecords(s.inst)) {
    let shape: string | null = null;
    try {
      shape = await shapeOf(hash);
    } catch {
      // a shape is a label only where it can be told; an unresolvable artifact is still kept
    }
    const labels = artifactLabels(s.inst, vocab, hash, shape, kinds.get(hash));
    out.push({ hash, tree: "artifacts", size: labels.size, labels, copies: copyViews(s, hash, "artifacts", containers) });
  }
  const testimony = new Map<string, number>();
  for (const r of s.index.receipts({ instance: s.inst.config.id })) {
    testimony.set(r.receipt, 0);
    for (const t of r.testimony) testimony.set(t.hash, 0);
  }
  for (const hash of [...testimony.keys()].sort()) {
    const size = s.index.copies(hash).find((c) => c.state !== "missing")?.size ?? 0;
    out.push({ hash, tree: "testimony", size, labels: testimonyLabels(size), copies: copyViews(s, hash, "testimony", containers) });
  }
  return out;
}
