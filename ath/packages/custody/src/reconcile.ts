// reconcile.ts — keeping the holdings (spec §18.7): status lists every finding, plan the actions that would resolve
// them, reconcile performs them. A copy is made from the cheapest verified route to stores chosen by requirement,
// confinement, free space and declared cost; what is overdue is re-verified; the local store, above its fill level,
// sheds only copies whose policies hold without them, the remaining copies re-hashed at that moment. No other store
// loses a copy here: that is `custody remove`, one copy at a time (§9.7). Each transfer lands whole or not at all, so
// an interrupted run is resumed by planning again. A store this host cannot reach is skipped (§18.7.2).
import { AthError } from "@ath/kit/errors.ts";
import { blake3Hex } from "@ath/kit/hash.ts";
import type { Driver, Present } from "./drivers.ts";
import type { CustodyIndex, ReceiptRow } from "./index-db.ts";
import type { Tree } from "./local.ts";
import {
  applies,
  type CopyView,
  confinedAway,
  counting,
  distinctValue,
  evaluate,
  type Finding,
  holdsRequirement,
  holdsWithout,
  type Labels,
  type Policy,
} from "./policy.ts";
import { type StoreDecl, tagsMatch } from "./stores.ts";

/** A declared store as this host sees it: its driver, or null when the host cannot reach it. */
export interface Site {
  decl: StoreDecl;
  driver: Driver | null;
}

/** One artifact or testimony an instance holds, with its labels and every copy the index believes in. */
export interface Holding {
  hash: string;
  tree: Tree;
  size: number;
  labels: Labels;
  copies: CopyView[];
}

export type Action =
  | { op: "copy"; hash: string; tree: Tree; store: string; id: string; size: number; why: string }
  | { op: "verify"; hash: string; tree: Tree; store: string; id: string; held: string; why: string }
  | { op: "evict"; hash: string; tree: Tree; store: string; id: string; size: number; why: string };

export interface PlanCtx {
  sites: readonly Site[];
  policies: readonly Policy[];
  now: Date;
  /** The local store: its id, the fill level it sheds above, and its fill now (used of capacity). */
  local: { id: string; evict?: number; used: number; capacity: number | null };
  /** Free bytes per store id, where known. */
  free: ReadonlyMap<string, number>;
}

const overdue = (c: CopyView, p: Policy, now: Date) =>
  p.verify !== undefined && (!c.verified_at || now.getTime() - Date.parse(c.verified_at) > p.verify * 1000);

/** Every finding: each holding's under its policies, and each store over its capacity. */
export function status(
  holdings: readonly Holding[],
  ctx: Pick<PlanCtx, "sites" | "policies" | "now">,
  used: ReadonlyMap<string, number>,
): Finding[] {
  const out: Finding[] = [];
  for (const h of holdings) out.push(...evaluate(h.hash, h.labels, h.copies, ctx.policies, ctx.now));
  for (const s of ctx.sites) {
    const u = used.get(s.decl.id) ?? 0;
    if (s.decl.capacity !== undefined && u > s.decl.capacity)
      out.push({ kind: "capacity", store: s.decl.name, detail: `${s.decl.name} holds ${u} bytes of its ${s.decl.capacity}` });
  }
  return out;
}

/** The actions that would resolve the findings, and the findings no action this host can take resolves. */
export function plan(holdings: readonly Holding[], ctx: PlanCtx): { actions: Action[]; unmet: Finding[] } {
  const actions: Action[] = [];
  const unmet: Finding[] = [];
  const reach = new Map(ctx.sites.filter((s) => s.driver).map((s) => [s.decl.id, s.decl]));
  const free = new Map(ctx.free);
  const iso = `${ctx.now.toISOString().slice(0, 19)}Z`;
  for (const h of holdings) {
    const policies = ctx.policies.filter((p) => applies(p, h.labels));
    // re-verify what a policy finds overdue, on stores this host reaches; planning counts it as verified
    const verified = new Set<string>();
    const sim: CopyView[] = h.copies.map((c) => {
      if (c.state === "missing" || c.store.role !== "managed" || !reach.has(c.store.id)) return c;
      const p = policies.find((x) => overdue(c, x, ctx.now));
      if (!p) return c;
      const key = `${c.store.id}:${c.held}`;
      if (!verified.has(key)) {
        verified.add(key);
        actions.push({
          op: "verify",
          hash: h.hash,
          tree: h.tree,
          store: c.store.name,
          id: c.store.id,
          held: c.held,
          why: `${p.name}: verification overdue`,
        });
      }
      return { ...c, state: "verified", verified_at: iso };
    });
    const source = h.copies.some((c) => c.state !== "missing");
    for (const p of policies)
      for (const [i, r] of p.require.entries()) {
        const why = p.name === "default" ? "default: unpersisted" : `${p.name}: require[${i}]`;
        while (!holdsRequirement(r, counting(p, sim, ctx.now))) {
          const have = counting(p, sim, ctx.now).filter((c) => tagsMatch(c.store.tags, r.where));
          const values = new Set(have.map((c) => (r.distinct ? distinctValue(c.store, r.distinct) : undefined)));
          const target = [...reach.values()]
            .filter(
              (s) =>
                s.role === "managed" &&
                s.id !== ctx.local.id &&
                tagsMatch(s.tags, r.where) &&
                !confinedAway(h.labels, s, ctx.policies) &&
                !sim.some((c) => c.store.id === s.id && c.state !== "missing" && c.via !== "container") &&
                (free.get(s.id) === undefined || free.get(s.id)! >= h.size) &&
                (!r.distinct || (distinctValue(s, r.distinct) !== undefined && !values.has(distinctValue(s, r.distinct)))),
            )
            .sort((a, b) => a.cost - b.cost || (a.name < b.name ? -1 : 1))[0];
          if (!source || !target) {
            unmet.push({
              kind: p.name === "default" ? "unpersisted" : "below",
              hash: h.hash,
              policy: p.name,
              detail: !source ? "no copy anywhere to copy from" : `no store this host reaches can take a copy for ${why}`,
            });
            break;
          }
          actions.push({ op: "copy", hash: h.hash, tree: h.tree, store: target.name, id: target.id, size: h.size, why });
          if (free.has(target.id)) free.set(target.id, free.get(target.id)! - h.size);
          sim.push({
            store: target,
            state: "verified",
            verified_at: iso,
            via: "direct",
            physical: `${target.id}:${h.hash}`,
            held: h.hash,
            tree: h.tree,
          });
        }
      }
  }
  // the local store, above its fill level, sheds the largest copies its policies hold without
  const { local } = ctx;
  if (local.evict !== undefined && local.capacity) {
    let used = local.used;
    const isLocal = (h: Holding) => (c: CopyView) => c.store.id === local.id && c.held === h.hash && c.via !== "container";
    const candidates = holdings
      .filter((h) => h.copies.some((c) => isLocal(h)(c) && c.state !== "missing"))
      .filter((h) => holdsWithout(h.labels, h.copies, isLocal(h), ctx.policies, ctx.now))
      .sort((a, b) => b.size - a.size || (a.hash < b.hash ? -1 : 1));
    for (const h of candidates) {
      if (used / local.capacity <= local.evict) break;
      actions.push({
        op: "evict",
        hash: h.hash,
        tree: h.tree,
        store: "local",
        id: local.id,
        size: h.size,
        why: `local above ${Math.round(local.evict * 100)}%`,
      });
      used -= h.size;
    }
  }
  // a hardlinked copy is the first an independent copy is made of (§18.5.3)
  const linked = new Set(holdings.filter((h) => h.copies.some((c) => c.via === "linked")).map((h) => h.hash));
  const first = (a: Action) => (a.op === "copy" && linked.has(a.hash) ? 0 : 1);
  return {
    actions: actions
      .map((a, i) => ({ a, i }))
      .sort((x, y) => first(x.a) - first(y.a) || x.i - y.i)
      .map((x) => x.a),
    unmet,
  };
}

export interface PerformDeps {
  sites: readonly Site[];
  index: CustodyIndex;
  policies: readonly Policy[];
  /** Verified bytes through the cheapest route, never from the store named. */
  fetch(hash: string, tree: Tree, avoid?: string): Promise<Uint8Array>;
  /** The holding as the index now believes it. */
  holding(hash: string, tree: Tree): Holding;
  now(): Date;
}

const second = (d: Date) => `${d.toISOString().slice(0, 19)}Z`;

/** Hash what a store keeps for a copy and record the outcome; true when it verifies. A corrupt local copy is removed
 * and, where another route holds the bytes, restored (§18.5.3). */
export async function verifyCopy(site: Site, tree: Tree, held: string, deps: PerformDeps): Promise<boolean> {
  if (!site.driver) throw new AthError("EXTERNAL", `${site.decl.name} is not reachable from this host`);
  const b = await site.driver.get(tree, held);
  const ok = b !== null && (await blake3Hex(b)) === held;
  const prior = deps.index.copies(held).find((c) => c.store === site.decl.id);
  deps.index.putCopy({
    store: site.decl.id,
    tree,
    hash: held,
    state: ok ? "verified" : "missing",
    size: b?.length ?? prior?.size ?? 0,
    verified_at: ok ? second(deps.now()) : null,
    generation: prior?.generation ?? 0,
  });
  if (!ok && b !== null && site.decl.role === "managed") {
    await site.driver.remove(tree, held);
    if (site.decl.tags.includes("local")) {
      try {
        const bytes = await deps.fetch(held, tree, site.decl.id);
        await site.driver.put(tree, held, bytes);
        deps.index.putCopy({
          store: site.decl.id,
          tree,
          hash: held,
          state: "verified",
          size: bytes.length,
          verified_at: second(deps.now()),
          generation: 0,
        });
      } catch {
        // no other route holds it: the copy is lost here, and status says what that leaves
      }
    }
  }
  return ok;
}

/** Remove one copy, after re-hashing every other copy that counts, at that moment, and finding the policies hold without
 * it (§9.7, §18.1.4). */
export async function removeCopy(hash: string, tree: Tree, storeId: string, deps: PerformDeps): Promise<void> {
  const site = deps.sites.find((s) => s.decl.id === storeId);
  if (!site?.driver) throw new AthError("EXTERNAL", `${site?.decl.name ?? storeId} is not reachable from this host`);
  const h = deps.holding(hash, tree);
  const target = (c: CopyView) => c.store.id === storeId && c.held === hash && c.via !== "container";
  if (!h.copies.some((c) => target(c) && c.state !== "missing"))
    throw new AthError("NOT_FOUND", `${site.decl.name} holds no copy of ${hash}`);
  const now = deps.now();
  const fresh: CopyView[] = [];
  const checked = new Map<string, boolean>();
  for (const c of h.copies) {
    if (target(c)) {
      fresh.push(c);
      continue;
    }
    const s = deps.sites.find((x) => x.decl.id === c.store.id);
    if (c.state === "missing" || c.store.role !== "managed" || !s?.driver) continue;
    const key = `${c.store.id}:${c.held}`;
    if (!checked.has(key)) checked.set(key, await verifyCopy(s, c.via === "container" ? "artifacts" : c.tree, c.held, deps));
    if (checked.get(key)) fresh.push({ ...c, state: "verified", verified_at: second(now) });
  }
  if (!holdsWithout(h.labels, fresh, target, deps.policies, now))
    throw new AthError(
      "CONFLICT",
      `the policies of ${hash} would not hold without the copy on ${site.decl.name}, counting the copies verified now`,
    );
  await site.driver.remove(tree, hash);
  const prior = deps.index.copies(hash).find((c) => c.store === storeId);
  deps.index.putCopy({
    store: storeId,
    tree,
    hash,
    state: "missing",
    size: prior?.size ?? h.size,
    verified_at: null,
    generation: prior?.generation ?? 0,
  });
}

/** Perform a plan's actions in order; a failure is reported and the rest go on. */
export async function perform(
  actions: readonly Action[],
  deps: PerformDeps,
): Promise<{ done: Action[]; failed: { action: Action; error: string }[] }> {
  const done: Action[] = [];
  const failed: { action: Action; error: string }[] = [];
  for (const a of actions) {
    const site = deps.sites.find((s) => s.decl.id === a.id);
    try {
      if (!site?.driver) throw new AthError("EXTERNAL", `${a.store} is not reachable from this host`);
      if (a.op === "copy") {
        const bytes = await deps.fetch(a.hash, a.tree);
        await site.driver.put(a.tree, a.hash, bytes);
        deps.index.putCopy({
          store: a.id,
          tree: a.tree,
          hash: a.hash,
          state: "verified",
          size: bytes.length,
          verified_at: second(deps.now()),
          generation: 0,
        });
      } else if (a.op === "verify") {
        if (!(await verifyCopy(site, a.held === a.hash ? a.tree : "artifacts", a.held, deps)))
          throw new AthError("CONFLICT", `the copy on ${a.store} does not verify`);
      } else await removeCopy(a.hash, a.tree, a.id, deps);
      done.push(a);
    } catch (e) {
      failed.push({ action: a, error: (e as Error).message });
    }
  }
  return { done, failed };
}

/** Refresh the index from a store's inventory (§18.4): what is present is claimed (a verified copy stays verified at the
 * same size), what the index believed and is absent is missing. An observed tree's files come from its manifest. A
 * testimony the index does not know is read to find the receipts among them. */
export async function inventory(
  site: Site,
  index: CustodyIndex,
  receiptOf: (bytes: Uint8Array) => ReceiptRow | null,
  hashOf: (bytes: Uint8Array) => Promise<string> = blake3Hex,
): Promise<{ present: number; missing: number; receipts: number }> {
  if (!site.driver) throw new AthError("EXTERNAL", `${site.decl.name} is not reachable from this host`);
  const d = site.driver;
  const id = site.decl.id;
  let present: Present[];
  let generation: number;
  if (d.observed) {
    const files = d.observed();
    generation = d.manifest?.()?.generation ?? 0;
    index.putObserved(
      id,
      files.map((f) => ({ path: f.path, hash: f.hash, size: f.size, mtime: f.mtime, generation: f.generation })),
    );
    present = [...new Map(files.map((f) => [f.hash, { tree: "artifacts" as Tree, hash: f.hash, size: f.size }])).values()];
  } else {
    present = await d.inventory();
    generation = index.nextGeneration(id);
  }
  const known = new Map(index.copiesOn(id).map((c) => [c.hash, c]));
  const seen = new Set<string>();
  let receipts = 0;
  const knownReceipts = new Set(index.receipts({}).flatMap((r) => [r.receipt, ...r.testimony.map((t) => t.hash)]));
  for (const p of present) {
    seen.add(p.hash);
    const was = known.get(p.hash);
    const keep = was?.state === "verified" && was.size === p.size;
    index.putCopy({
      store: id,
      tree: p.tree,
      hash: p.hash,
      state: keep ? "verified" : "claimed",
      size: p.size,
      verified_at: keep ? was.verified_at : null,
      generation,
    });
    if (p.tree === "testimony" && !knownReceipts.has(p.hash)) {
      const b = await d.get("testimony", p.hash);
      if (b && (await hashOf(b)) === p.hash) {
        const r = receiptOf(b);
        if (r) {
          index.putReceipt({ ...r, receipt: p.hash });
          receipts++;
        }
      }
    }
  }
  let missing = 0;
  for (const c of known.values())
    if (!seen.has(c.hash) && c.state !== "missing") {
      index.putCopy({ ...c, state: "missing", verified_at: null, generation });
      missing++;
    }
  return { present: present.length, missing, receipts };
}
