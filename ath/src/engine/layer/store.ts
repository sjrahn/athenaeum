// store.ts — where a subject's lines live and how a chain is read: a subject's view is the line-set union of its file
// in every layer, bottom-up; writes go to the top layer only; a corpus write at an identity a lower layer already holds
// is refused (spec §2 shadowing: refuse in the corpus, override in the ledger).
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { AthError } from "../../kit/errors.ts";
import { writeAtomic } from "../../lib/fs.ts";
import { type JsonObject, readJsonl, serializeJsonl } from "../../lib/jsonl.ts";
import { identityKey, sortLines, type Tree, validateLine } from "../model/line.ts";
import { type Chain, type Layer, TREE_DIRS } from "./config.ts";

export type SubjectKind = "corpus" | "ledger" | "ontology";

/** The file that holds a subject in one layer. */
export function subjectPath(layer: Layer, kind: SubjectKind, id: string, owner = false): string {
  const dir = join(layer.root, TREE_DIRS[kind]);
  if (kind === "corpus") return join(dir, `${id}.${owner ? "owner" : "claims"}.jsonl`);
  return join(dir, `${id}.claims.jsonl`);
}

export const lineagePath = (layer: Layer, kind: "corpus" | "ledger") => join(layer.root, TREE_DIRS[kind], "lineage.jsonl");

export interface LayeredLine {
  line: JsonObject;
  layer: Layer;
}

/** Every line of a subject across the chain, bottom-up, with its layer. Lines are validated as they load. */
export function readSubject(chain: Chain, kind: SubjectKind, id: string, owner = false): LayeredLine[] {
  const tree: Tree = owner ? "owner" : kind;
  const out: LayeredLine[] = [];
  for (const layer of chain.layers) {
    const p = subjectPath(layer, kind, id, owner);
    if (!existsSync(p)) continue;
    for (const line of readJsonl(p)) {
      const bad = validateLine(tree, line);
      if (bad) throw new AthError("CONFIG", `${p}: ${bad}: ${JSON.stringify(line).slice(0, 160)}`);
      out.push({ line, layer });
    }
  }
  return out;
}

/** The union view: for ledger subjects a higher layer's line at the same identity overrides; for corpus subjects it
 * cannot exist (refused at write), so union is plain concatenation. */
export function unionView(kind: SubjectKind, lines: LayeredLine[]): LayeredLine[] {
  const tree: Tree = kind;
  const byId = new Map<string, LayeredLine>();
  for (const l of lines) byId.set(identityKey(tree, l.line), l);
  return [...byId.values()];
}

export function listSubjects(chain: Chain, kind: SubjectKind): string[] {
  const ids = new Set<string>();
  for (const layer of chain.layers) {
    const dir = join(layer.root, TREE_DIRS[kind]);
    if (!existsSync(dir)) continue;
    for (const f of readdirSync(dir)) {
      const m = /^(.+)\.claims\.jsonl$/.exec(f);
      if (m && m[1] !== "lineage") ids.add(m[1]!);
    }
  }
  return [...ids].sort();
}

/** Write a subject's lines in the top layer (sorted, canonical). */
export function writeSubject(chain: Chain, kind: SubjectKind, id: string, lines: JsonObject[], owner = false): string {
  const tree: Tree = owner ? "owner" : kind;
  const p = subjectPath(chain.top, kind, id, owner);
  writeAtomic(p, serializeJsonl(sortLines(tree, lines)));
  return p;
}

/** The identities a subject holds below the top layer (what a corpus write may not touch). */
export function lowerIdentities(chain: Chain, kind: SubjectKind, id: string, owner = false): Set<string> {
  const tree: Tree = owner ? "owner" : kind;
  const s = new Set<string>();
  for (const l of readSubject(chain, kind, id, owner)) if (l.layer !== chain.top) s.add(identityKey(tree, l.line));
  return s;
}
