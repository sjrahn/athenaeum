// status.ts — a claim's status, derived (spec §14.5), and standing, derived (§14.4.4). A claim is its lines across
// passes, its evidence their union. The first row that holds: refuted (no bound entry, an upheld challenge); disputed
// (a challenge stands); conflicting (a bound sibling claim disagrees on a functional property); confirmed (a bound
// authoritative entry, or bound entries from two artifacts that are not one source); provisional, inferred or
// reported (by the best bound entry's mode); unsupported. Authority is grounded: conferred in rounds from none, each
// round only by authority claims confirmed in the round before, until a round changes nothing. Two artifacts are one
// source when they manifest one entity.
import { canonicalJson, type JsonObject } from "@ath/kit/canonical.ts";
import type { EntryState } from "./binding.ts";
import { claimKey, type EvidenceEntry, type Held, type Line } from "./entity.ts";

export type Status = "refuted" | "disputed" | "conflicting" | "confirmed" | "provisional" | "inferred" | "reported" | "unsupported";

export interface Claim {
  entity: string;
  key: string;
  pred: string;
  val: unknown;
  qual?: JsonObject;
  lines: Held[];
  entries: { entry: EvidenceEntry; state: EntryState; line: Held }[];
}

export interface GraphInput {
  entities: Map<string, Held[]>;
  /** The state of each entry, by line and position. */
  stateOf(line: Line, index: number): EntryState;
  functional: (pred: string) => boolean;
  authority: (pred: string) => boolean;
}

const MODES = ["stated", "inferred", "reported"] as const;

export function claimsOf(entities: Map<string, Held[]>, stateOf: GraphInput["stateOf"]): Claim[] {
  const out = new Map<string, Claim>();
  for (const [entity, lines] of entities)
    for (const h of lines) {
      if (h.line.pred === "pass" || h.line.pred === "is") continue;
      const key = `${entity}\u0000${claimKey(h.line)}`;
      let c = out.get(key);
      if (!c) {
        c = { entity, key, pred: h.line.pred, val: h.line.val, ...(h.line.qual ? { qual: h.line.qual } : {}), lines: [], entries: [] };
        out.set(key, c);
      }
      c.lines.push(h);
      for (const [i, entry] of (h.line.ev ?? []).entries()) c.entries.push({ entry, state: stateOf(h.line, i), line: h });
    }
  return [...out.values()];
}

/** Artifacts grouped into sources: two that manifest one entity are one source (§14.2.2). */
export function sources(claims: readonly Claim[]): (a: string) => string {
  const parent = new Map<string, string>();
  const find = (a: string): string => {
    const p = parent.get(a);
    if (!p || p === a) return a;
    const r = find(p);
    parent.set(a, r);
    return r;
  };
  const byEntity = new Map<string, string[]>();
  for (const c of claims)
    if (c.pred === "manifests" && typeof c.val === "string" && /^ath:\/\/[0-9a-f]{64}$/.test(c.val))
      byEntity.set(c.entity, [...(byEntity.get(c.entity) ?? []), c.val.slice(6)]);
  for (const arts of byEntity.values()) for (const a of arts.slice(1)) parent.set(find(a), find(arts[0]!));
  return find;
}

/** What a challenge names (§14.2.2): {pred, val, qual?, of?} — a claim of `of`, else of its own entity. */
function target(c: Claim): string | null {
  const v = c.val as JsonObject | null;
  if (!v || typeof v !== "object" || typeof v.pred !== "string") return null;
  return `${typeof v.of === "string" ? v.of.replace(/^ath:\/\//, "") : c.entity}\u0000${v.pred}\u0000${canonicalJson(v.val)}\u0000${canonicalJson(v.qual ?? null)}`;
}

export interface Statuses {
  status: Map<string, Status>;
  /** Per entity, the artifacts its confirmed authority claims name. */
  authorized: Map<string, Set<string>>;
  claims: Claim[];
  rounds: number;
}

export function statuses(g: GraphInput): Statuses {
  const claims = claimsOf(g.entities, g.stateOf);
  const source = sources(claims);
  const challengesOf = new Map<string, Claim[]>();
  for (const c of claims)
    if (c.pred === "challenges") {
      const t = target(c);
      if (t) challengesOf.set(t, [...(challengesOf.get(t) ?? []), c]);
    }
  let authorized = new Map<string, Set<string>>();
  let status = new Map<string, Status>();
  let rounds = 0;
  for (;;) {
    rounds++;
    const memo = new Map<string, Status>();
    const of = (c: Claim, stack: Set<string>): Status => {
      const m = memo.get(c.key);
      if (m) return m;
      if (stack.has(c.key)) return "unsupported";
      stack.add(c.key);
      const bound = c.entries.filter((e) => e.state.state === "bound");
      const chs = challengesOf.get(c.key) ?? [];
      const stands = chs.filter((x) => x.entries.some((e) => e.state.state === "bound"));
      const upheld = chs.some((x) => of(x, stack) === "confirmed");
      let s: Status;
      if (!bound.length && upheld) s = "refuted";
      else if (stands.length) s = "disputed";
      else if (
        g.functional(c.pred) &&
        claims.some(
          (o) =>
            o !== c &&
            o.entity === c.entity &&
            o.pred === c.pred &&
            canonicalJson(o.val) !== canonicalJson(c.val) &&
            o.entries.some((e) => e.state.state === "bound"),
        )
      )
        s = "conflicting";
      else if (
        bound.some((e) => e.state.artifact && authorized.get(c.entity)?.has(e.state.artifact)) ||
        new Set(bound.map((e) => (e.state.artifact ? source(e.state.artifact) : ""))).size >= 2
      )
        s = "confirmed";
      else if (bound.length) {
        const best = MODES.find((m) => bound.some((e) => e.entry.mode === m)) ?? "stated";
        s = best === "stated" ? "provisional" : best;
      } else s = "unsupported";
      stack.delete(c.key);
      memo.set(c.key, s);
      return s;
    };
    const next = new Map<string, Status>(claims.map((c) => [c.key, of(c, new Set())]));
    // a round confers the authority of the claims confirmed in the round before it
    const conferred = new Map<string, Set<string>>();
    for (const c of claims)
      if (g.authority(c.pred) && next.get(c.key) === "confirmed" && typeof c.val === "string" && /^ath:\/\/[0-9a-f]{64}$/.test(c.val)) {
        const set = conferred.get(c.entity) ?? new Set<string>();
        set.add(c.val.slice(6));
        conferred.set(c.entity, set);
      }
    const same =
      conferred.size === authorized.size &&
      [...conferred].every(([e, s]) => authorized.get(e)?.size === s.size && [...s].every((a) => authorized.get(e)!.has(a)));
    status = next;
    if (same || rounds > 32) break;
    authorized = conferred;
  }
  return { status, authorized, claims, rounds };
}

/** Whether a bound entry is authoritative: anchored in an artifact a confirmed authority claim of its entity names. */
export const standing = (s: Statuses, entity: string, artifact: string | undefined): "authoritative" | "independent" =>
  artifact && s.authorized.get(entity)?.has(artifact) ? "authoritative" : "independent";
