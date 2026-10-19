// entity.ts — `ath entity split|merge|rename` (spec §14.1.3): verbs that rewrite every reference in the instance at once,
// journaled so no reader sees a partial rewrite (§19.3.1). A rename moves the file and every `ath://<name>` in the
// instance's entity files and rulings; a merge folds one entity's lines into another's, its passes renumbered past the
// other's; a split moves the claims named to a new entity, with the pass lines they need. An extension renames none of
// its base's entities.
import { defineContract, z } from "@ath/contracts";
import { isEntityName, type Line, ownEntity, serializeEntity } from "@ath/engine/graph/entity.ts";
import { ownRulings, rulingsPath } from "@ath/engine/graph/rulings.ts";
import { entityPath, type Instance, ownEntities } from "@ath/engine/instance/instance.ts";
import { canonicalLine } from "@ath/kit/canonical.ts";
import { defineCommand } from "@ath/kit/define.ts";
import { AthError } from "@ath/kit/errors.ts";
import { commitJournal, type JournalWrite } from "@ath/kit/journal.ts";
import { instanceState } from "@ath/kit/xdg.ts";
import { instanceOf } from "./context.ts";

/** Rewrite `ath://<from>` to `ath://<to>` wherever a string value holds it. */
function rewrite<T>(v: T, from: string, to: string): T {
  if (typeof v === "string") return (v === `ath://${from}` ? `ath://${to}` : v) as T;
  if (Array.isArray(v)) return v.map((x) => rewrite(x, from, to)) as T;
  if (v && typeof v === "object")
    return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, k === "of" && x === from ? to : rewrite(x, from, to)])) as T;
  return v;
}

/** The writes that point every reference to `from` at `to`, across this instance's entities and rulings. */
function references(inst: Instance, from: string, to: string, skip: Set<string>): JournalWrite[] {
  const out: JournalWrite[] = [];
  for (const n of ownEntities(inst)) {
    if (skip.has(n)) continue;
    const lines = ownEntity(inst, n)!;
    const next = lines.map((l) => rewrite(l, from, to));
    if (JSON.stringify(next) !== JSON.stringify(lines)) out.push({ path: entityPath(inst, n), content: serializeEntity(next) });
  }
  const rs = ownRulings(inst);
  const nr = rs.map((r) => rewrite(r, from, to));
  if (JSON.stringify(nr) !== JSON.stringify(rs))
    out.push({ path: rulingsPath(inst), content: nr.map((r) => `${canonicalLine(r)}\n`).join("") });
  return out;
}

function own(inst: Instance, name: string): Line[] {
  if (!isEntityName(name)) throw new AthError("USAGE", `'${name}' is not an entity name`);
  const lines = ownEntity(inst, name);
  if (!lines)
    throw new AthError(
      "NOT_FOUND",
      `${inst.config.name} has no entity ${name}${inst.base ? " of its own (a base's entity is the base's to change)" : ""}`,
    );
  return lines;
}

const journal = (ctx: Parameters<typeof instanceOf>[0], inst: Instance, writes: JournalWrite[]) =>
  commitJournal(instanceState(ctx.host, inst.config.id), writes);

export const entityRename = defineCommand({
  meta: {
    summary: "rename an entity, rewriting every reference in the instance at once",
    tier: "write",
    mutating: true,
    locks: ["repository"],
  },
  contract: defineContract({
    key: "entity-rename",
    args: z.object({ from: z.string(), to: z.string() }),
    argv: {
      positionals: [
        { name: "from", required: true },
        { name: "to", required: true },
      ],
    },
    data: z.object({ from: z.string(), to: z.string(), files: z.number() }),
  }),
  run(ctx, a) {
    const inst = instanceOf(ctx);
    const lines = own(inst, a.from);
    if (!isEntityName(a.to)) throw new AthError("USAGE", `'${a.to}' is not an entity name`);
    if (ownEntity(inst, a.to)) throw new AthError("CONFLICT", `${a.to} exists; merge into it instead`);
    const writes: JournalWrite[] = [
      { path: entityPath(inst, a.to), content: serializeEntity(lines.map((l) => rewrite(l, a.from, a.to))) },
      { path: entityPath(inst, a.from), content: null },
      ...references(inst, a.from, a.to, new Set([a.from])),
    ];
    journal(ctx, inst, writes);
    return { data: { from: a.from, to: a.to, files: writes.length } };
  },
  text: (d, io) => io.out(`renamed ${d.from} → ${d.to} (${d.files} files)\n`),
});

export const entityMerge = defineCommand({
  meta: {
    summary: "merge one entity into another: its lines folded in, its passes renumbered, every reference rewritten",
    tier: "write",
    mutating: true,
    locks: ["repository"],
  },
  contract: defineContract({
    key: "entity-merge",
    args: z.object({ from: z.string(), into: z.string() }),
    argv: {
      positionals: [
        { name: "from", required: true },
        { name: "into", required: true },
      ],
    },
    data: z.object({ from: z.string(), into: z.string(), lines: z.number() }),
  }),
  run(ctx, a) {
    const inst = instanceOf(ctx);
    const src = own(inst, a.from);
    const dst = own(inst, a.into);
    let n = Math.max(0, ...dst.filter((l) => l.pred === "pass").map((l) => Number(String((l.val as { id: string }).id).slice(1))));
    const ids = new Map<string, string>();
    for (const l of src) if (l.pred === "pass") ids.set(String((l.val as { id: string }).id), `p${++n}`);
    const moved = src.map((l) => {
      const r = rewrite(l, a.from, a.into);
      if (r.pred === "pass") return { ...r, val: { ...(r.val as object), id: ids.get(String((l.val as { id: string }).id)) } };
      return r.pass ? { ...r, pass: ids.get(r.pass) ?? r.pass } : r;
    });
    const writes: JournalWrite[] = [
      { path: entityPath(inst, a.into), content: serializeEntity([...dst, ...moved]) },
      { path: entityPath(inst, a.from), content: null },
      ...references(inst, a.from, a.into, new Set([a.from, a.into])),
    ];
    journal(ctx, inst, writes);
    return { data: { from: a.from, into: a.into, lines: moved.length } };
  },
  text: (d, io) => io.out(`merged ${d.from} into ${d.into} (${d.lines} lines)\n`),
});

export const entitySplit = defineCommand({
  meta: {
    summary: "split the claims named off into a new entity, with the pass and is lines they need",
    tier: "write",
    mutating: true,
    locks: ["repository"],
    examples: ["ath entity split bo-calder bo-calder-junior --claim birth-date"],
  },
  contract: defineContract({
    key: "entity-split",
    args: z.object({ from: z.string(), to: z.string(), claim: z.array(z.string()).min(1) }),
    argv: {
      positionals: [
        { name: "from", required: true },
        { name: "to", required: true },
      ],
      flags: { claim: { type: "string", repeat: true, metavar: "PRED[=VAL]", help: "the claims to move" } },
    },
    data: z.object({ from: z.string(), to: z.string(), moved: z.number() }),
  }),
  run(ctx, a) {
    const inst = instanceOf(ctx);
    const lines = own(inst, a.from);
    if (!isEntityName(a.to) || ownEntity(inst, a.to)) throw new AthError("CONFLICT", `${a.to} is not a new entity name`);
    const picks = a.claim.map((c) => {
      const eq = c.indexOf("=");
      return eq < 0 ? { pred: c } : { pred: c.slice(0, eq), val: c.slice(eq + 1) };
    });
    const hit = (l: Line) =>
      l.pred !== "pass" && l.pred !== "is" && picks.some((p) => p.pred === l.pred && (p.val === undefined || String(l.val) === p.val));
    const moving = lines.filter(hit);
    if (!moving.length) throw new AthError("NOT_FOUND", `${a.from} has no claim ${a.claim.join(", ")}`);
    const need = new Set(moving.map((l) => l.pass));
    const passes = lines.filter((l) => l.pred === "pass" && need.has(String((l.val as { id: string }).id)));
    const kinds = lines.filter((l) => l.pred === "is");
    journal(ctx, inst, [
      { path: entityPath(inst, a.to), content: serializeEntity([...passes, ...kinds, ...moving]) },
      { path: entityPath(inst, a.from), content: serializeEntity(lines.filter((l) => !hit(l))) },
    ]);
    return { data: { from: a.from, to: a.to, moved: moving.length } };
  },
  text: (d, io) => io.out(`split ${d.moved} claim lines from ${d.from} into ${d.to}\n`),
});
