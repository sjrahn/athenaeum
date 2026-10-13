// server.ts — the read surface (spec §12): planes over the chain. The public plane serves the foundation layers and
// confirmed claims; an audience plane adds the extension layers its grant names; the owner plane serves the whole
// chain, the owner files and every lint. Read-only; the server re-reads the layer on every request.

import { ATH_VERSION } from "../../kit/version.ts";
import { loadArtifact } from "../corpus/derive.ts";
import { derivationAt } from "../corpus/resolve.ts";
import { resolveBytes } from "../layer/bytes.ts";
import type { Chain, Layer } from "../layer/config.ts";
import { listSubjects, readSubject, type SubjectKind, unionView } from "../layer/store.ts";
import { ArtifactCache } from "../ledger/bind.ts";
import { readConcept } from "../ledger/file.ts";
import { ontologyPin } from "../ontology/hash.ts";
import { loadOntology, type Ontology, toJson } from "../ontology/load.ts";
import { verifyConcept } from "../verify.ts";

export type Plane = { kind: "public" } | { kind: "audience"; name: string } | { kind: "owner" };

/** The layers a plane may see. An audience sees the foundation plus every extension whose tier its grant names. */
export function layersFor(chain: Chain, plane: Plane): Layer[] {
  if (plane.kind === "owner") return chain.layers;
  if (plane.kind === "public") return chain.layers.filter((l) => l.config.layer === "foundation");
  const grants = new Set<string>();
  for (const l of chain.layers) for (const t of l.config.audiences?.[plane.name] ?? []) grants.add(t);
  return chain.layers.filter((l) => l.config.layer === "foundation" || (l.config.tier !== undefined && grants.has(l.config.tier)));
}

const json = (v: unknown, status = 200) =>
  new Response(JSON.stringify(v), { status, headers: { "content-type": "application/json; charset=utf-8" } });
const notFound = (what: string) => json({ error: "NOT_FOUND", message: what }, 404);

export interface ServeOptions {
  chain: Chain;
  plane: Plane;
  port?: number;
  hostname?: string;
}

export function createServer(o: ServeOptions) {
  const { chain, plane } = o;
  const visible = layersFor(chain, plane);
  const inPlane = (l: { layer: Layer }) => visible.includes(l.layer);
  const ont = (): Ontology => loadOntology(chain);
  const subjectLines = (kind: SubjectKind, id: string) => unionView(kind, readSubject(chain, kind, id).filter(inPlane)).map((l) => l.line);

  return Bun.serve({
    port: o.port ?? 0,
    hostname: o.hostname ?? "127.0.0.1",
    async fetch(req) {
      const url = new URL(req.url);
      const parts = url.pathname.split("/").filter(Boolean);
      try {
        if (parts.length === 0 || parts[0] === "instance") {
          const o2 = ont();
          return json({
            version: ATH_VERSION,
            plane: plane.kind,
            layers: visible.map((l) => ({ name: l.config.name, layer: l.config.layer, tier: l.config.tier ?? null })),
            ontology: await ontologyPin(o2),
            terms: o2.terms.size,
          });
        }
        if (parts[0] === "ontology") {
          const o2 = ont();
          if (parts.length === 1) return json({ terms: [...o2.terms.keys()].sort() });
          const lines = (o2.terms.get(parts[1]!) ?? []).filter(inPlane).map(toJson);
          return lines.length ? json({ term: parts[1], lines }) : notFound(`term ${parts[1]}`);
        }
        if (parts[0] === "corpus") {
          if (parts.length === 1)
            return json({ subjects: listSubjects(chain, "corpus").filter((id) => subjectLines("corpus", id).length) });
          const id = parts[1]!;
          const lines = subjectLines("corpus", id);
          if (!lines.length) return notFound(`corpus://${id}`);
          if (parts[2] === "tree") {
            const art = await loadArtifact(chain, ont(), id);
            return json({
              subject: id,
              root: art.root,
              tree: art.tree,
              scopes: art.table.walk().map((s) => ({
                at: s.at,
                terms: s.terms,
                fields: s.fields,
                parent: s.parent,
                ord: s.ord,
                derived: s.derived,
                readings: s.readings.map((r) => ({ aspect: r.aspect, rev: r.rev, body: r.body })),
              })),
            });
          }
          if (parts[2] === "owner") {
            if (plane.kind !== "owner") return notFound(`corpus://${id}/owner`);
            return json({ subject: id, lines: unionView("corpus", readSubject(chain, "corpus", id, true)).map((l) => l.line) });
          }
          return json({ subject: id, lines });
        }
        if (parts[0] === "resolve" && parts[1] === "corpus" && parts[2]) {
          const id = parts[2];
          if (!subjectLines("corpus", id).length) return notFound(`corpus://${id}`);
          const at = url.searchParams.get("at") ?? "whole";
          const art = await loadArtifact(chain, ont(), id);
          const d = derivationAt(art, at);
          return d ? json({ subject: id, at, source: d.source, text: d.text }) : notFound(`no derivation at ${at}`);
        }
        if (parts[0] === "bytes" && parts[1]) {
          if (!subjectLines("corpus", parts[1]).length) return notFound(`corpus://${parts[1]}`);
          const p = resolveBytes(chain, parts[1]);
          if (!p) return notFound("bytes not resident");
          return new Response(Bun.file(p));
        }
        if (parts[0] === "ledger") {
          if (parts.length === 1)
            return json({ subjects: listSubjects(chain, "ledger").filter((id) => subjectLines("ledger", id).length) });
          const slug = parts[1]!;
          const c = readConcept(chain, slug);
          if (!c) return notFound(`ledger://${slug}`);
          const o2 = ont();
          const r = await verifyConcept(chain, o2, new ArtifactCache(chain, o2), c);
          const rung = plane.kind === "owner" ? null : "confirmed";
          const claims = r.judged
            .filter((j) => (rung ? j.status === rung : true) && visible.some((l) => l.config.name === j.claim.layer))
            .map((j) => ({ ...j.claim.line, status: j.status, bindings: j.bindings.map((b) => b.state) }));
          const body: Record<string, unknown> = { subject: slug, terms: c.terms, manifested_by: c.manifestedBy, claims };
          if (plane.kind === "owner") {
            body.demand = r.demand;
            body.findings = r.findings;
          }
          return json(body);
        }
        return notFound(url.pathname);
      } catch (e) {
        return json({ error: "INTERNAL", message: (e as Error).message }, 500);
      }
    },
  });
}
