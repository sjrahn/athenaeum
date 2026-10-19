// custody.ts — `ath custody inventory|verify|status|plan|reconcile|where|report|remove` (spec §18, §19.5). Inventory
// refreshes the host index from each reachable store or observed tree's manifest; verify re-hashes copies; status
// lists the findings, a verdict when there are any; plan lists the actions that would resolve them and reconcile
// performs them; where names every known residence of a hash; report sorts an observed tree's files by what the
// instance holds; remove takes one copy off one store, the owner's, after the policies are found to hold without it.

import { defineContract, z } from "@ath/contracts";
import {
  type Action,
  type CopyView,
  type Finding,
  type Holding,
  inventory,
  type PerformDeps,
  perform,
  plan,
  type ReceiptRow,
  removeCopy,
  type Site,
  status,
  type Tree,
  verifyCopy,
} from "@ath/custody";
import { containersIndex, holdings, resolvePrefix } from "@ath/engine/instance/instance.ts";
import { canonicalJson } from "@ath/kit/canonical.ts";
import { defineCommand } from "@ath/kit/define.ts";
import { AthError } from "@ath/kit/errors.ts";
import { UUID } from "@ath/kit/root.ts";
import type { KitCtx } from "@ath/kit/types.ts";
import { resolver } from "./artifacts.ts";
import { custodyIndex, instanceOf } from "./context.ts";
import { copyViews, holdingsOf, openSites, type Sites } from "./sites.ts";
import { viewer } from "./view.ts";

/** A receipt, recognised by its shape and its bytes being its canonical serialisation (§9.3.1). */
export function receiptOf(bytes: Uint8Array): ReceiptRow | null {
  let d: unknown;
  try {
    d = JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return null;
  }
  const r = d as Record<string, unknown>;
  if (!r || typeof r !== "object" || Object.keys(r).sort().join() !== "actor,artifact,instance,name,received,testimony") return null;
  if (typeof r.artifact !== "string" || !/^[0-9a-f]{64}$/.test(r.artifact) || typeof r.instance !== "string" || !UUID.test(r.instance))
    return null;
  if (!Array.isArray(r.testimony) || !r.testimony.every((t) => typeof t?.hash === "string" && typeof t?.name === "string")) return null;
  if (`${canonicalJson(r as never)}\n` !== new TextDecoder().decode(bytes)) return null;
  return {
    receipt: "",
    instance: r.instance,
    artifact: r.artifact,
    name: String(r.name),
    received: String(r.received),
    actor: String(r.actor),
    testimony: (r.testimony as { hash: string; name: string }[]).map((t) => ({ hash: t.hash, name: t.name })),
  };
}

/** The sites a verb works on: one named store, or every one this host reaches; the unreachable are named. */
function chosen(s: Sites, name: string | undefined): { sites: Site[]; unreachable: string[] } {
  if (name) {
    const site = s.named(name);
    if (!site.driver)
      throw new AthError("EXTERNAL", `${name} is not reachable from this host: access.yaml says nothing of ${site.decl.id}`);
    return { sites: [site], unreachable: [] };
  }
  return { sites: s.sites.filter((x) => x.driver), unreachable: s.sites.filter((x) => !x.driver).map((x) => x.decl.name) };
}

/** Everything the planning verbs need: the holdings with labels and copies, the local store's fill, free space. */
async function world(ctx: KitCtx, s: Sites) {
  const res = resolver(ctx, s.inst, s.index);
  const vw = viewer(s.inst, res.resolve);
  const held = await holdingsOf(s, vw.vocab.vocab, (h) => vw.shapeOf(h));
  const used = new Map<string, number>();
  for (const site of s.sites)
    used.set(
      site.decl.id,
      s.index
        .copiesOn(site.decl.id)
        .filter((c) => c.state !== "missing")
        .reduce((n, c) => n + c.size, 0),
    );
  const free = new Map<string, number>();
  for (const site of s.sites) {
    if (!site.driver || site.decl.role !== "managed") continue;
    if (site.decl.capacity !== undefined) free.set(site.decl.id, site.decl.capacity - (used.get(site.decl.id) ?? 0));
    else {
      const st = await site.driver.stat().catch(() => ({}) as { free?: number });
      if (st.free !== undefined) free.set(site.decl.id, st.free);
    }
  }
  let local: { id: string; evict?: number; used: number; capacity: number | null } = {
    id: s.store.id,
    used: used.get(s.store.id) ?? 0,
    capacity: s.local.capacity ?? null,
  };
  if (s.local.evict !== undefined) local.evict = s.local.evict;
  if (local.capacity === null) {
    const st = await s.sites[0]!.driver!.stat();
    if (st.used !== undefined && st.free !== undefined) local = { ...local, used: st.used, capacity: st.used + st.free };
  }
  const now = ctx.wall.now();
  const deps: PerformDeps = {
    sites: s.sites,
    index: s.index,
    policies: s.policies,
    fetch: async (h, tree, avoid) => (await res.resolve(h, tree, avoid)).bytes,
    holding: (h, tree) => {
      const was = held.find((x) => x.hash === h && x.tree === tree);
      if (!was) throw new AthError("NOT_FOUND", `the instance holds no ${tree === "testimony" ? "testimony" : "artifact"} ${h}`);
      return { ...was, copies: copyViews(s, h, tree) };
    },
    now: () => ctx.wall.now(),
  };
  return { held, used, free, local, now, deps };
}

const findingRow = z.object({
  kind: z.enum(["unpersisted", "below", "outside", "overdue", "capacity"]),
  hash: z.string().optional(),
  store: z.string().optional(),
  policy: z.string().optional(),
  detail: z.string(),
});
const actionRow = z.object({
  op: z.enum(["copy", "verify", "evict"]),
  hash: z.string(),
  tree: z.enum(["artifacts", "testimony"]),
  store: z.string(),
  why: z.string(),
});
const strip = (a: Action) => ({ op: a.op, hash: a.hash, tree: a.tree, store: a.store, why: a.why });
const findingLine = (f: Finding) => `${f.kind.padEnd(11)} ${f.hash ?? f.store ?? ""}  ${f.policy ? `${f.policy}: ` : ""}${f.detail}\n`;
const actionLine = (a: z.infer<typeof actionRow>) =>
  `${a.op.padEnd(6)} ${a.hash}  ${a.op === "copy" ? "→" : "on"} ${a.store}  (${a.why})\n`;

export const custodyInventory = defineCommand({
  meta: {
    summary: "refresh the index from each reachable store's inventory or observed tree's manifest",
    tier: "write",
    mutating: true,
    locks: ["index"],
  },
  contract: defineContract({
    key: "custody-inventory",
    args: z.object({ store: z.string().optional() }),
    argv: { positionals: [{ name: "store", help: "one store (default: every one this host reaches)" }] },
    data: z.object({
      stores: z.array(z.object({ store: z.string(), present: z.number(), missing: z.number(), receipts: z.number() })),
      unreachable: z.array(z.string()),
    }),
  }),
  async run(ctx, a) {
    const s = openSites(ctx, instanceOf(ctx));
    try {
      const { sites, unreachable } = chosen(s, a.store);
      const stores = [];
      for (const site of sites) stores.push({ store: site.decl.name, ...(await inventory(site, s.index, receiptOf)) });
      return { data: { stores, unreachable } };
    } finally {
      s.close();
    }
  },
  text(d, io) {
    for (const x of d.stores) io.out(`${x.store.padEnd(12)} ${x.present} present, ${x.missing} missing, ${x.receipts} receipts found\n`);
    for (const u of d.unreachable) io.out(`${u.padEnd(12)} unreachable, skipped\n`);
  },
});

export const custodyVerify = defineCommand({
  meta: { summary: "re-hash every copy the index believes a reachable store holds", tier: "write", mutating: true, locks: ["index"] },
  contract: defineContract({
    key: "custody-verify",
    args: z.object({ store: z.string().optional() }),
    argv: { positionals: [{ name: "store", help: "one store (default: every one this host reaches)" }] },
    data: z.object({
      verified: z.number(),
      failed: z.array(z.object({ store: z.string(), hash: z.string() })),
      unreachable: z.array(z.string()),
    }),
  }),
  async run(ctx, a) {
    const inst = instanceOf(ctx);
    const s = openSites(ctx, inst);
    try {
      const { sites, unreachable } = chosen(s, a.store);
      const res = resolver(ctx, inst, s.index);
      const deps = {
        sites: s.sites,
        index: s.index,
        policies: s.policies,
        fetch: async (h: string, t: Tree, avoid?: string) => (await res.resolve(h, t, avoid)).bytes,
        holding: () => {
          throw new Error("unused");
        },
        now: () => ctx.wall.now(),
      } as PerformDeps;
      let verified = 0;
      const failed: { store: string; hash: string }[] = [];
      for (const site of sites)
        for (const c of s.index.copiesOn(site.decl.id))
          if (c.state !== "missing") {
            if (await verifyCopy(site, c.tree, c.hash, deps)) verified++;
            else failed.push({ store: site.decl.name, hash: c.hash });
          }
      return { data: { verified, failed, unreachable }, ...(failed.length ? { exitCode: 1 } : {}) };
    } finally {
      s.close();
    }
  },
  text(d, io) {
    io.out(`${d.verified} verified\n`);
    for (const f of d.failed) io.out(`failed  ${f.store}  ${f.hash}\n`);
  },
});

export const custodyStatus = defineCommand({
  meta: {
    summary: "every finding: unpersisted, below a requirement, outside a confinement, overdue, over capacity; any is a verdict",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "custody-status",
    args: z.object({}),
    argv: {},
    data: z.object({ holdings: z.number(), findings: z.array(findingRow), unreachable: z.array(z.string()) }),
  }),
  async run(ctx) {
    const s = openSites(ctx, instanceOf(ctx), custodyIndex(ctx));
    try {
      const w = await world(ctx, s);
      const findings = status(w.held, { sites: s.sites, policies: s.policies, now: w.now }, w.used);
      return {
        data: { holdings: w.held.length, findings, unreachable: s.sites.filter((x) => !x.driver).map((x) => x.decl.name) },
        ...(findings.length ? { exitCode: 1 } : {}),
      };
    } finally {
      s.index.close();
    }
  },
  text(d, io) {
    if (!d.findings.length) io.out(`${d.holdings} held; every policy holds\n`);
    for (const f of d.findings) io.out(findingLine(f));
  },
});

export const custodyPlan = defineCommand({
  meta: {
    summary: "the actions that would resolve the findings, and those no action this host can take resolves",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "custody-plan",
    args: z.object({}),
    argv: {},
    data: z.object({ actions: z.array(actionRow), unmet: z.array(findingRow) }),
  }),
  async run(ctx) {
    const s = openSites(ctx, instanceOf(ctx), custodyIndex(ctx));
    try {
      const w = await world(ctx, s);
      const p = plan(w.held, { sites: s.sites, policies: s.policies, now: w.now, local: w.local, free: w.free });
      return { data: { actions: p.actions.map(strip), unmet: p.unmet } };
    } finally {
      s.index.close();
    }
  },
  text(d, io) {
    if (!d.actions.length && !d.unmet.length) io.out("nothing to do\n");
    for (const a of d.actions) io.out(actionLine(a));
    for (const f of d.unmet) io.out(`unmet  ${findingLine(f)}`);
  },
});

export const custodyReconcile = defineCommand({
  meta: {
    summary: "perform the plan: copy, re-verify, evict from the local store; never removes a copy elsewhere",
    tier: "write",
    mutating: true,
    locks: ["index"],
  },
  contract: defineContract({
    key: "custody-reconcile",
    args: z.object({}),
    argv: {},
    data: z.object({
      done: z.array(actionRow),
      failed: z.array(actionRow.extend({ error: z.string() })),
      unmet: z.array(findingRow),
    }),
  }),
  async run(ctx) {
    const s = openSites(ctx, instanceOf(ctx), custodyIndex(ctx));
    try {
      const w = await world(ctx, s);
      const p = plan(w.held, { sites: s.sites, policies: s.policies, now: w.now, local: w.local, free: w.free });
      const r = await perform(p.actions, w.deps);
      return {
        data: { done: r.done.map(strip), failed: r.failed.map((f) => ({ ...strip(f.action), error: f.error })), unmet: p.unmet },
        ...(r.failed.length ? { exitCode: 1 } : {}),
      };
    } finally {
      s.index.close();
    }
  },
  text(d, io) {
    if (!d.done.length && !d.failed.length) io.out("nothing to do\n");
    for (const a of d.done) io.out(actionLine(a));
    for (const f of d.failed) io.out(`failed ${f.op} ${f.hash} ${f.store}: ${f.error}\n`);
    for (const f of d.unmet) io.out(`unmet  ${findingLine(f)}`);
  },
});

const residence = z.object({
  store: z.string(),
  state: z.string(),
  verified_at: z.string().nullable(),
  via: z.string(),
  within: z.string().optional(),
});

export const custodyWhere = defineCommand({
  meta: { summary: "every residence the index knows of a hash, whether or not the instance holds it", tier: "read", mutating: false },
  contract: defineContract({
    key: "custody-where",
    args: z.object({ hash: z.string() }),
    argv: { positionals: [{ name: "hash", required: true, help: "a BLAKE3, or a prefix of 8 or more hex digits" }] },
    data: z.object({
      hash: z.string(),
      copies: z.array(residence),
      observed: z.array(z.object({ store: z.string(), path: z.string(), link: z.string().nullable() })),
    }),
  }),
  run(ctx, a) {
    const inst = instanceOf(ctx);
    const s = openSites(ctx, inst);
    try {
      const containers = containersIndex(inst);
      const known = new Set([
        ...s.index.hashes("artifacts"),
        ...s.index.hashes("testimony"),
        ...containers.keys(),
        ...holdings(inst).keys(),
      ]);
      const hash = resolvePrefix(a.hash.replace(/^(b3:|ath:\/\/)/, ""), known);
      const name = (id: string) => s.byId.get(id)?.decl.name ?? id;
      const copies: z.infer<typeof residence>[] = [];
      for (const c of s.index.copies(hash))
        copies.push({ store: name(c.store), state: c.state, verified_at: c.verified_at, via: c.link ? "linked" : "direct" });
      const tree: Tree = copies.length || containers.has(hash) || holdings(inst).has(hash) ? "artifacts" : "testimony";
      for (const v of copyViews(s, hash, tree).filter((x: CopyView) => x.via === "container"))
        copies.push({ store: v.store.name, state: v.state, verified_at: v.verified_at, via: "container", within: v.held });
      const observed = s.index.observed({ hash }).map((o) => ({ store: name(o.store), path: o.path, link: o.link }));
      if (!copies.length && !observed.length) throw new AthError("NOT_FOUND", `the index knows no residence of ${hash}`);
      return { data: { hash, copies, observed } };
    } finally {
      s.close();
    }
  },
  text(d, io) {
    io.out(`${d.hash}\n`);
    for (const c of d.copies)
      io.out(
        `  ${c.store.padEnd(12)} ${c.state.padEnd(8)} ${c.verified_at ?? ""}${c.within ? `  in ${c.within}` : c.via === "linked" ? "  (hardlinked)" : ""}\n`,
      );
    for (const o of d.observed) io.out(`  ${o.store.padEnd(12)} observed ${o.path}${o.link ? `  → ${o.link}` : ""}\n`);
  },
});

const fileRow = z.object({ path: z.string(), hash: z.string(), link: z.string().nullable() });

export const custodyReport = defineCommand({
  meta: {
    summary: "an observed tree's files: held also in a managed store, held only there (at risk), not held (candidates)",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "custody-report",
    args: z.object({ store: z.string() }),
    argv: { positionals: [{ name: "store", required: true }] },
    data: z.object({
      store: z.string(),
      also: z.array(fileRow.extend({ stores: z.array(z.string()) })),
      at_risk: z.array(fileRow),
      candidates: z.array(fileRow),
    }),
  }),
  run(ctx, a) {
    const inst = instanceOf(ctx);
    const s = openSites(ctx, inst);
    try {
      const site = s.named(a.store);
      if (site.decl.role !== "observed") throw new AthError("USAGE", `${a.store} is a managed store; a report is of an observed tree`);
      const held = new Set([...holdings(inst).keys(), ...containersIndex(inst).keys()]);
      const out = {
        store: a.store,
        also: [] as (z.infer<typeof fileRow> & { stores: string[] })[],
        at_risk: [] as z.infer<typeof fileRow>[],
        candidates: [] as z.infer<typeof fileRow>[],
      };
      for (const o of s.index.observed({ store: site.decl.id })) {
        const row = { path: o.path, hash: o.hash, link: o.link };
        if (!held.has(o.hash)) {
          out.candidates.push(row);
          continue;
        }
        const managed = copyViews(s, o.hash, "artifacts").filter((c) => c.store.role === "managed" && c.state !== "missing");
        if (managed.length) out.also.push({ ...row, stores: [...new Set(managed.map((c) => c.store.name))] });
        else out.at_risk.push(row);
      }
      return { data: out };
    } finally {
      s.close();
    }
  },
  text(d, io) {
    for (const f of d.also) io.out(`also     ${f.path}  [${f.stores.join(", ")}]${f.link ? `  ${f.link.split(" ")[1]}` : ""}\n`);
    for (const f of d.at_risk) io.out(`at risk  ${f.path}\n`);
    for (const f of d.candidates) io.out(`ingest?  ${f.path}\n`);
  },
});

export const custodyRemove = defineCommand({
  meta: {
    summary: "remove one copy from one store, refused unless the policies hold without it, the other copies verified now",
    tier: "admin",
    mutating: true,
    locks: ["index"],
  },
  contract: defineContract({
    key: "custody-remove",
    args: z.object({ hash: z.string(), from: z.string() }),
    argv: {
      positionals: [{ name: "hash", required: true }],
      flags: { from: { type: "string", help: "the store to remove the copy from" } },
    },
    data: z.object({ hash: z.string(), store: z.string() }),
  }),
  async run(ctx, a) {
    const s = openSites(ctx, instanceOf(ctx), custodyIndex(ctx));
    try {
      const site = s.named(a.from);
      if (site.decl.role !== "managed") throw new AthError("USAGE", `${a.from} is an observed tree: custody never removes from it`);
      const w = await world(ctx, s);
      const hash = resolvePrefix(
        a.hash.replace(/^(b3:|ath:\/\/)/, ""),
        w.held.map((h) => h.hash),
      );
      const h = w.held.find((x: Holding) => x.hash === hash)!;
      await removeCopy(hash, h.tree, site.decl.id, w.deps);
      return { data: { hash, store: a.from } };
    } finally {
      s.index.close();
    }
  },
  text(d, io) {
    io.out(`removed  ${d.hash}  from ${d.store}\n`);
  },
});
