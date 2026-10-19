// graph.ts — what the graph verbs open: every entity of the chain, an anchor located through the viewer and custody (a
// record's reading, a structured artifact's surface, a testimony's surface; a route to an asset canonicalised to the
// asset), every evidence entry's state with the rulings' distrust applied, and from them status, standing and demand.
import { canonicalAt, formatAddress, parseAddress, type Region } from "@ath/engine/address/address.ts";
import { regionProblem } from "@ath/engine/address/anchor.ts";
import { formatOf, Parses, surfaceAt } from "@ath/engine/formats/index.ts";
import { sniffMime } from "@ath/engine/formats/sniff.ts";
import { type EntryState, entryState, type Locate, type Target } from "@ath/engine/graph/binding.ts";
import { type DemandItem, demand } from "@ath/engine/graph/demand.ts";
import { entityView, type Held, type Line } from "@ath/engine/graph/entity.ts";
import { distrusts, type Ruling, rulingsOf } from "@ath/engine/graph/rulings.ts";
import { type Statuses, statuses } from "@ath/engine/graph/status.ts";
import { chain, entityNames, holdings, type Instance, ownRecords, recordView } from "@ath/engine/instance/instance.ts";
import { passOf } from "@ath/engine/pass/coverage.ts";
import { readingAt, scopeAt } from "@ath/engine/record/tree.ts";
import { type DScope, positional } from "@ath/engine/structure/derive.ts";
import { one } from "@ath/engine/vocab/load.ts";
import { effectiveRules } from "@ath/engine/vocab/rules.ts";
import { pin } from "@ath/engine/vocab/terms.ts";
import type { KitCtx } from "@ath/kit/types.ts";
import { resolver } from "./artifacts.ts";
import { custodyIndex, localStore } from "./context.ts";
import { viewer } from "./view.ts";

export interface Graph {
  inst: Instance;
  locate: Locate;
  entities: Map<string, Held[]>;
  rulings: (Ruling & { instance: string })[];
  states: Map<Line, EntryState[]>;
  statuses: Statuses;
  demand: DemandItem[];
  pins: { corpus: string; graph: string };
  viewer: ReturnType<typeof viewer>;
  close(): void;
}

export async function openGraph(ctx: KitCtx, inst: Instance): Promise<Graph> {
  const index = custodyIndex(ctx);
  const store = localStore(ctx);
  const res = resolver(inst, store, index);
  const vw = viewer(inst, res.resolve);
  const v = vw.vocab.vocab;
  const held = holdings(inst);
  const known = new Set([...held.keys(), ...vw.containers.keys()]);
  const bytesMemo = new Map<string, Promise<Uint8Array | null>>();
  const bytesOf = (h: string, tree: "artifacts" | "testimony" = "artifacts") => {
    const k = `${tree}:${h}`;
    let p = bytesMemo.get(k);
    if (!p) {
      p =
        tree === "artifacts"
          ? res.resolve(h).then(
              (r) => r.bytes,
              () => null,
            )
          : store.get("testimony", h).catch(() => null);
      bytesMemo.set(k, p);
    }
    return p;
  };
  const locate: Locate = async (anchor) => {
    const m = /^ath:\/\/([0-9a-f]{64})(?:\?(.+))?$/.exec(anchor);
    if (!m) return { problem: `${anchor} is not an anchor with a full hash` };
    let hash = m[1]!;
    let address: ReturnType<typeof parseAddress>;
    try {
      address = parseAddress(m[2] ?? "whole");
    } catch (e) {
      return { problem: (e as Error).message };
    }
    const testimony = !known.has(hash) && (await bytesOf(hash, "testimony")) !== null;
    if (!known.has(hash) && !testimony) return { problem: `${hash} is nothing the chain holds` };
    let regions: Region[] = address.regions;
    if (!testimony) {
      // a route to an asset canonicalises to the asset's own id (§7.5.2)
      const paths = new Set(regions.map((r) => r.path));
      if (paths.size === 1 && [...paths][0] !== undefined) {
        const view = await vw.view(hash);
        const c = (view.intrinsics.constituents as { path: string; blake3: string; kind: string }[] | undefined)?.find(
          (x) => x.path === [...paths][0],
        );
        if (!c) return { problem: `${hash} has no constituent at ${[...paths][0]}` };
        if (c.kind === "asset") {
          hash = c.blake3;
          regions = regions.map(({ path: _p, ...rest }) => (Object.keys(rest).length ? rest : { whole: true as const }));
        }
      }
    }
    // a cell names the M-th cell of the row read at the rest of the address
    let col: number | undefined;
    const last = regions.at(-1)!;
    const rowLike = (r: Region) => r.row !== undefined || r.bbox !== undefined;
    if (last.col !== undefined && rowLike(last)) {
      col = last.col;
      regions = [...regions.slice(0, -1), Object.fromEntries(Object.entries(last).filter(([k]) => k !== "col")) as Region];
    }
    const at = formatAddress({ regions });
    if (testimony) {
      const b = (await bytesOf(hash, "testimony"))!;
      const mime = sniffMime(b, "testimony.yaml");
      const f = formatOf(mime);
      const parses = new Parses(b);
      return {
        hash,
        at,
        ...(address.aspect ? { aspect: address.aspect } : {}),
        ...(col !== undefined ? { col } : {}),
        kind: "testimony",
        reading: null,
        fields: null,
        intrinsics: { mime, bytes: b.length },
        surfaceOp: f.class === "structured" ? (f.ops[0] ?? null) : null,
        surface: (op) => surfaceAt(parses, op, regions),
      } satisfies Target;
    }
    const view = await vw.view(hash);
    for (const r of regions) {
      const p = regionProblem(view.intrinsics, r);
      if (p) return { problem: `${hash}: ${p}` };
    }
    const rec = view.record;
    const kind = view.format.class ?? "unregistered";
    let fields: Record<string, unknown> | null = null;
    let readsAt: string | null = null;
    let forms: string[] = [];
    if (view.tree.kind === "derived") {
      for (const { scope } of positional(view.tree.scopes as DScope[]))
        if (canonicalAt(scope.at) === at) {
          fields = scope.fields;
          readsAt = scope.reads?.at ?? null;
          forms = [scope.form].flat();
        }
    } else if (rec) {
      const s = scopeAt(rec, at);
      if (s) {
        fields = Object.fromEntries(Object.entries(s).filter(([k]) => !["form", "at", "scopes", "text", "cells", "tex"].includes(k)));
        forms = [s.form].flat();
      }
    }
    const surfaceOp =
      kind === "structured"
        ? ((forms.length ? effectiveRules(v, forms, [], view.shape.shape).surface : null) ?? view.format.ops[0] ?? null)
        : null;
    return {
      hash,
      at,
      ...(address.aspect ? { aspect: address.aspect } : {}),
      ...(col !== undefined ? { col } : {}),
      kind,
      reading: rec ? readingAt(rec, at) : null,
      fields,
      intrinsics: view.intrinsics,
      surfaceOp,
      surface: async (op) => {
        const b = await bytesOf(hash);
        return b ? surfaceAt(new Parses(b), op, readsAt ? parseAddress(readsAt).regions : regions) : null;
      },
    } satisfies Target;
  };
  // the entities, their entries' states, statuses and demand
  const entities = new Map<string, Held[]>();
  for (const n of entityNames(inst)) {
    const e = entityView(inst, n);
    if (e) entities.set(n, e);
  }
  const rulings = rulingsOf(inst);
  const d = distrusts(rulings);
  const states = new Map<Line, EntryState[]>();
  for (const [name, lines] of entities)
    for (const h of lines) {
      if (!h.line.ev?.length) continue;
      const out: EntryState[] = [];
      for (const e of h.line.ev) {
        const loc = await locate(e.anchor);
        const hash = "problem" in loc ? null : loc.hash;
        let distrusted = !!hash && d.hashes.has(hash);
        if (!distrusted && h.line.pass && d.passes.has(`${name}#${h.line.pass}`)) distrusted = true;
        if (!distrusted && hash && !("problem" in loc)) {
          const rec = recordView(inst, hash)?.record;
          const p = rec ? passOf(rec, loc.at) : null;
          if (p && d.passes.has(`${hash}#${p}`)) distrusted = true;
          for (const o of d.ops) {
            const om = /^ath:\/\/([0-9a-f]{64})\?(.+)$/.exec(o.anchor);
            if (om && om[1] === hash && canonicalAt(om[2]!) === loc.at && (!o.op || e.binding === `derived:${o.op}`)) distrusted = true;
          }
        }
        out.push(await entryState(e, loc, distrusted));
      }
      states.set(h.line, out);
    }
  const props = v.properties;
  const st = statuses({
    entities,
    stateOf: (line, i) => states.get(line)?.[i] ?? { state: "held", reason: "unbound" },
    functional: (p) => one(props.get(p), "functional") === true,
    authority: (p) => one(props.get(p), "authority") === true,
  });
  const pins = { corpus: await pin(v, "corpus"), graph: await pin(v, "graph") };
  const passes: { subject: string; id: string; vocab: string; current: string }[] = [];
  for (const x of chain(inst).slice(0, 1))
    for (const h of ownRecords(x))
      for (const [id, p] of Object.entries(recordView(inst, h)?.record.passes ?? {}))
        passes.push({ subject: h, id, vocab: p.vocab, current: pins.corpus });
  for (const [name, lines] of entities)
    for (const h of lines)
      if (h.line.pred === "pass" && h.instance === inst.config.name)
        passes.push({
          subject: name,
          id: String((h.line.val as { id: string }).id),
          vocab: String((h.line.val as { vocab: string }).vocab),
          current: pins.graph,
        });
  const dm = demand({ statuses: st, entities, vocab: v, passes, rulings });
  return { inst, locate, entities, rulings, states, statuses: st, demand: dm, pins, viewer: vw, close: () => index.close() };
}
