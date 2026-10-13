// index.ts — every lint over one artifact: generic (G1–G3), per-file, per-term. G4 runs from the ledger side (verify).
import type { Artifact } from "../corpus/derive.ts";
import { fileLintsCorpus } from "./file.ts";
import { g1Unit, g2Tree, g3Cover } from "./generic.ts";
import type { Finding } from "./report.ts";
import { termLints } from "./term.ts";

export function lintArtifact(a: Artifact, pin: string | null, o: { generic?: boolean; file?: boolean; term?: boolean } = {}): Finding[] {
  const all = !o.generic && !o.file && !o.term;
  const out: Finding[] = [];
  if (all || o.generic) out.push(...g1Unit(a), ...g2Tree(a), ...g3Cover(a));
  if (all || o.file) out.push(...fileLintsCorpus(a, pin));
  if (all || o.term) out.push(...termLints(a));
  return out;
}
