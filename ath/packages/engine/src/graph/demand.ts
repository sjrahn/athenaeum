// demand.ts — the work the instance owes, derived and never stored (spec §14.6): a held entry is a reading owed over its
// region, or a re-bind owed where its quote still lies there; a confirmed `same-as` is a merge owed; an unmet `owes`
// of an entity's kind is a search; an unsupported claim is an acquisition; a stale pass is a re-run; a `seek` ruling
// demands what it names. The owner orders demand with `defer` and removes it with `decline` (§13.5).
import { all, refinesChain } from "../vocab/load.ts";
import type { Vocabulary } from "../vocab/terms.ts";
import type { Held } from "./entity.ts";
import type { Ruling } from "./rulings.ts";
import type { Statuses } from "./status.ts";

export interface DemandItem {
  kind: "reading" | "re-bind" | "merge" | "search" | "acquisition" | "re-run" | "seek";
  subject: string;
  detail: string;
  /** The ruling that created it (seek), or that defers it. */
  ruling?: string;
  deferred?: string;
}

export const demandKey = (d: DemandItem) => `${d.kind}:${d.subject}:${d.detail}`;

export interface DemandInput {
  statuses: Statuses;
  entities: Map<string, Held[]>;
  vocab: Vocabulary;
  /** Every pass, record or entity, with the pin it read against and the current pin of its side. */
  passes: { subject: string; id: string; vocab: string; current: string }[];
  rulings: readonly Ruling[];
}

/** The kinds an entity is, with every kind they refine. */
const kindsOf = (lines: readonly Held[], v: Vocabulary): string[] => [
  ...new Set(
    lines
      .filter((h) => h.line.pred === "is" && typeof h.line.val === "string")
      .flatMap((h) => refinesChain(v, "kinds", h.line.val as string)),
  ),
];

const owesOf = (kinds: readonly string[], v: Vocabulary): string[] => [
  ...new Set(kinds.flatMap((k) => all(v.kinds.get(k), "owes").flat() as string[])),
];

export function demand(d: DemandInput): DemandItem[] {
  const out: DemandItem[] = [];
  const s = d.statuses;
  for (const c of s.claims) {
    for (const e of c.entries) {
      if (e.state.state !== "held") continue;
      if (e.state.rebind) out.push({ kind: "re-bind", subject: c.entity, detail: `${c.pred} ← ${e.entry.anchor}` });
      else out.push({ kind: "reading", subject: e.entry.anchor.replace(/^ath:\/\//, "").split("?")[0]!, detail: e.entry.anchor });
    }
    const st = s.status.get(c.key);
    if (c.pred === "same-as" && st === "confirmed") out.push({ kind: "merge", subject: c.entity, detail: String(c.val) });
    if (st === "unsupported") out.push({ kind: "acquisition", subject: c.entity, detail: `${c.pred} ${JSON.stringify(c.val)}` });
  }
  const has = (entity: string, pred: string) =>
    s.claims.some(
      (c) => c.entity === entity && c.pred === pred && s.status.get(c.key) !== "unsupported" && s.status.get(c.key) !== "refuted",
    );
  for (const [entity, lines] of d.entities)
    for (const p of owesOf(kindsOf(lines, d.vocab), d.vocab)) if (!has(entity, p)) out.push({ kind: "search", subject: entity, detail: p });
  for (const p of d.passes) if (p.vocab !== p.current) out.push({ kind: "re-run", subject: p.subject, detail: p.id });
  for (const r of d.rulings) {
    if (r.pred !== "seek") continue;
    const sel = r.val.select as Record<string, unknown>;
    const owes = (r.val.owes as string[] | undefined) ?? [];
    if (typeof sel.kind === "string")
      for (const [entity, lines] of d.entities)
        if (kindsOf(lines, d.vocab).includes(sel.kind))
          for (const p of owes) if (!has(entity, p)) out.push({ kind: "seek", subject: entity, detail: p, ruling: r.id });
    if (typeof sel.entity === "string")
      for (const p of owes)
        if (!has(sel.entity.replace(/^ath:\/\//, ""), p))
          out.push({ kind: "seek", subject: sel.entity.replace(/^ath:\/\//, ""), detail: p, ruling: r.id });
  }
  // decline removes, defer orders after everything not deferred
  const matches = (r: Ruling, x: DemandItem): boolean => {
    const on = typeof r.val.on === "string" ? r.val.on.replace(/^ath:\/\//, "") : null;
    if (on !== null && !(x.subject === on || demandKey(x) === on || x.detail === r.val.on)) return false;
    if (typeof r.val.demand === "string" && r.val.demand !== x.kind) return false;
    const sel = r.val.select as Record<string, unknown> | undefined;
    if (sel && typeof sel.kind === "string" && !kindsOf(d.entities.get(x.subject) ?? [], d.vocab).includes(sel.kind)) return false;
    return on !== null || !!sel;
  };
  const kept = out.filter((x) => !d.rulings.some((r) => r.pred === "decline" && matches(r, x)));
  for (const x of kept) {
    const r = d.rulings.find((y) => y.pred === "defer" && matches(y, x));
    if (r) x.deferred = r.id;
  }
  const seen = new Set<string>();
  const ordered: DemandItem[] = [];
  for (const x of [...kept.filter((y) => !y.deferred), ...kept.filter((y) => y.deferred)]) {
    if (seen.has(demandKey(x))) continue;
    seen.add(demandKey(x));
    ordered.push(x);
  }
  return ordered;
}
