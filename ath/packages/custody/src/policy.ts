// policy.ts — how an instance keeps a selection of its holdings (spec §18.6). A policy's `select` matches labels the
// instance computes for each artifact and testimony — its shape and that shape's chain, the producers of its origins,
// the kinds of the entities that cite it, its mime and its size, `testimony: true` — and custody is handed those
// labels; it knows no record. A requirement holds when at least `copies` copies sit on stores whose tags satisfy
// `where`, across that many distinct values of `distinct`; a copy counts once per physical copy — a constituent is held
// wherever its container is, linked copies count once, observed trees and missing copies never count; `confine`
// restricts every copy; `verify` is how recent a copy's verification must be. Every instance carries the default
// policy: at least one copy on a managed store not tagged `local`.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { AthError } from "@ath/kit/errors.ts";
import { parseSize, type StoreDecl, tagsMatch } from "./stores.ts";

export type TagExpr = { all?: string[]; any?: string[]; not?: string[] };

export interface Requirement {
  copies: number;
  where?: TagExpr;
  distinct?: string;
}

export interface Policy {
  name: string;
  select: { shape?: string; origin?: string; kind?: string; mime?: string; size?: { above?: number; below?: number }; testimony?: boolean };
  require: Requirement[];
  confine?: TagExpr;
  /** Seconds a verification counts for. */
  verify?: number;
  instance?: string;
}

export interface Labels {
  shapes: string[];
  origins: string[];
  kinds: string[];
  mime: string | null;
  size: number;
  testimony: boolean;
}

/** One physical copy the index believes in, on a store, possibly through a container or shared with a link. */
export interface CopyView {
  store: StoreDecl;
  state: "claimed" | "verified" | "missing";
  verified_at: string | null;
  /** `direct`, `container` (the constituent held where its container is), `linked` (a hardlink sharing storage with
   * an observed file). */
  via: "direct" | "container" | "linked";
  /** A physical copy's identity: copies sharing one count once. */
  physical: string;
  /** What the store keeps for this copy: the hash itself, or for a container route the container's hash. */
  held: string;
  tree: "artifacts" | "testimony";
}

export const DEFAULT_POLICY: Policy = { name: "default", select: {}, require: [{ copies: 1, where: { not: ["local"] } }] };

const DUR = /^(\d+)\s*(s|m|h|d|w|y)$/;
const SECONDS: Record<string, number> = { s: 1, m: 60, h: 3600, d: 86400, w: 604800, y: 31557600 };

function tagExpr(v: unknown, where: string): TagExpr | undefined {
  if (v === undefined) return undefined;
  const o = v as Record<string, unknown>;
  if (!o || typeof o !== "object") throw new AthError("CONFIG", `${where}: a tag selection is {all, any, not}`);
  for (const k of Object.keys(o))
    if (!["all", "any", "not"].includes(k) || !Array.isArray(o[k]))
      throw new AthError("CONFIG", `${where}: a tag selection is {all, any, not}, each a list`);
  return o as TagExpr;
}

export function parsePolicy(name: string, text: string, where: string): Policy {
  let d: Record<string, unknown>;
  try {
    d = (Bun.YAML.parse(text) ?? {}) as Record<string, unknown>;
  } catch (e) {
    throw new AthError("CONFIG", `${where}: ${(e as Error).message}`);
  }
  for (const k of Object.keys(d))
    if (!["select", "require", "confine", "verify"].includes(k))
      throw new AthError("CONFIG", `${where}: \`${k}\` is not a key of a policy`);
  const sel = (d.select ?? {}) as Record<string, unknown>;
  for (const k of Object.keys(sel))
    if (!["shape", "origin", "kind", "mime", "size", "testimony"].includes(k))
      throw new AthError("CONFIG", `${where}: select: \`${k}\` is not a label`);
  const size = sel.size as { above?: string; below?: string } | undefined;
  const reqs = d.require === undefined ? [] : Array.isArray(d.require) ? d.require : [d.require];
  const p: Policy = {
    name,
    select: {
      ...(typeof sel.shape === "string" ? { shape: sel.shape } : {}),
      ...(typeof sel.origin === "string" ? { origin: sel.origin } : {}),
      ...(typeof sel.kind === "string" ? { kind: sel.kind } : {}),
      ...(typeof sel.mime === "string" ? { mime: sel.mime } : {}),
      ...(sel.testimony === true ? { testimony: true } : {}),
      ...(size
        ? {
            size: {
              ...(size.above ? { above: parseSize(size.above) ?? 0 } : {}),
              ...(size.below ? { below: parseSize(size.below) ?? 0 } : {}),
            },
          }
        : {}),
    },
    require: reqs.map((r, i) => {
      const o = r as Record<string, unknown>;
      if (typeof o.copies !== "number" || o.copies < 1) throw new AthError("CONFIG", `${where}: require[${i}].copies is a positive number`);
      return {
        copies: o.copies,
        ...(o.where ? { where: tagExpr(o.where, where) } : {}),
        ...(typeof o.distinct === "string" ? { distinct: o.distinct } : {}),
      };
    }),
  };
  const confine = tagExpr(d.confine, where);
  if (confine) p.confine = confine;
  if (d.verify !== undefined) {
    const m = DUR.exec(String(d.verify));
    if (!m) throw new AthError("CONFIG", `${where}: verify is a duration: 90d`);
    p.verify = Number(m[1]) * SECONDS[m[2]!]!;
  }
  return p;
}

export function loadPolicies(roots: readonly { root: string; name: string }[]): Policy[] {
  const out: Policy[] = [DEFAULT_POLICY];
  for (const { root, name } of roots) {
    const dir = join(root, "policies");
    if (!existsSync(dir)) continue;
    for (const f of readdirSync(dir).sort())
      if (f.endsWith(".yaml"))
        out.push({ ...parsePolicy(f.slice(0, -5), readFileSync(join(dir, f), "utf8"), join(name, "policies", f)), instance: name });
  }
  return out;
}

export function applies(p: Policy, l: Labels): boolean {
  const s = p.select;
  if (s.testimony !== undefined && s.testimony !== l.testimony) return false;
  if (s.shape && !l.shapes.includes(s.shape)) return false;
  if (s.origin && !l.origins.includes(s.origin)) return false;
  if (s.kind && !l.kinds.includes(s.kind)) return false;
  if (s.mime && l.mime !== s.mime) return false;
  if (s.size?.above !== undefined && !(l.size > s.size.above)) return false;
  if (s.size?.below !== undefined && !(l.size < s.size.below)) return false;
  return true;
}

export interface Finding {
  kind: "unpersisted" | "below" | "outside" | "overdue" | "capacity";
  /** The holding, or for `capacity` the store. */
  hash?: string;
  store?: string;
  policy?: string;
  detail: string;
}

/** The copies that count for a policy now: physical, managed, present, verified recently enough where it asks. */
export function counting(p: Policy, copies: readonly CopyView[], now: Date): CopyView[] {
  const seen = new Set<string>();
  const out: CopyView[] = [];
  for (const c of copies) {
    if (c.store.role !== "managed" || c.state === "missing") continue;
    if (p.verify !== undefined && (!c.verified_at || now.getTime() - Date.parse(c.verified_at) > p.verify * 1000)) continue;
    if (seen.has(c.physical)) continue;
    seen.add(c.physical);
    out.push(c);
  }
  return out;
}

/** Whether a requirement holds over the counting copies. */
export function holdsRequirement(r: Requirement, copies: readonly CopyView[]): boolean {
  const ok = copies.filter((c) => tagsMatch(c.store.tags, r.where));
  if (ok.length < r.copies) return false;
  if (!r.distinct) return true;
  const values = new Set(ok.map((c) => distinctValue(c.store, r.distinct!)).filter(Boolean));
  return values.size >= r.copies;
}

/** The tags-satisfying value of `distinct` a store carries, if any. */
export const distinctValue = (s: StoreDecl, key: string): string | undefined => s.tags.find((t) => t.startsWith(`${key}:`));

/** The findings for one holding under every policy that applies to it. */
export function evaluate(hash: string, labels: Labels, copies: readonly CopyView[], policies: readonly Policy[], now: Date): Finding[] {
  const out: Finding[] = [];
  for (const p of policies) {
    if (!applies(p, labels)) continue;
    const c = counting(p, copies, now);
    for (const [i, r] of p.require.entries())
      if (!holdsRequirement(r, c))
        out.push(
          p === DEFAULT_POLICY
            ? { kind: "unpersisted", hash, policy: p.name, detail: "no copy on a managed store not tagged local" }
            : {
                kind: "below",
                hash,
                policy: p.name,
                detail: `require[${i}]: ${r.copies} copies${r.where ? ` where ${JSON.stringify(r.where)}` : ""}${r.distinct ? ` across distinct ${r.distinct}` : ""}; ${c.filter((x) => tagsMatch(x.store.tags, r.where)).length} count`,
              },
        );
    if (p.confine)
      for (const x of copies)
        if (x.state !== "missing" && x.store.role === "managed" && !tagsMatch(x.store.tags, p.confine))
          out.push({
            kind: "outside",
            hash,
            policy: p.name,
            detail: `a copy on ${x.store.name} lies outside ${JSON.stringify(p.confine)}`,
          });
    if (p.verify !== undefined)
      for (const x of copies)
        if (
          x.store.role === "managed" &&
          x.state !== "missing" &&
          (!x.verified_at || now.getTime() - Date.parse(x.verified_at) > p.verify * 1000)
        )
          out.push({
            kind: "overdue",
            hash,
            policy: p.name,
            detail: `the copy on ${x.store.name} was last verified ${x.verified_at ?? "never"}`,
          });
  }
  return out;
}

/** Whether every policy that applies would still hold without one copy (§9.7, §18.7.1). */
export function holdsWithout(
  labels: Labels,
  copies: readonly CopyView[],
  without: (c: CopyView) => boolean,
  policies: readonly Policy[],
  now: Date,
): boolean {
  const rest = copies.filter((c) => !without(c));
  return policies.filter((p) => applies(p, labels)).every((p) => p.require.every((r) => holdsRequirement(r, counting(p, rest, now))));
}

/** Whether a store may hold a copy under every confining policy that applies. */
export const confinedAway = (labels: Labels, store: StoreDecl, policies: readonly Policy[]): boolean =>
  policies.some((p) => p.confine && applies(p, labels) && !tagsMatch(store.tags, p.confine));
