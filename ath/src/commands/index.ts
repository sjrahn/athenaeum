// index.ts — the command table: every group registers here. Add a command by importing its def and listing it once.
import { createRegistry, type Registry } from "../kit/registry.ts";
import { claimsShow, claimsSort } from "./claims.ts";
import { exportMarkdownCmd, exportNquads } from "./export.ts";
import { harvest } from "./harvest.ts";
import { imageWords } from "./image.ts";
import { ingest, ingestShow } from "./ingest.ts";
import { inspect, inspectAccept, inspectRevoke } from "./inspect.ts";
import { layerCheck, layerInit, layerShow } from "./layer.ts";
import { lint } from "./lint.ts";
import { logCommand } from "./log.ts";
import { ontologyHash, ontologyLint, ontologyList, ontologyRules, ontologyShow } from "./ontology.ts";
import { claimsAppend, passAbandon, passList, passOpen, passSign } from "./pass.ts";
import { resolveCmd } from "./resolve.ts";
import { serve } from "./serve.ts";
import { tree, treeAt } from "./tree.ts";
import { verify } from "./verify.ts";
import { whoamiCommand } from "./whoami.ts";

export function buildRegistry(): Registry {
  const r = createRegistry();
  r.registerGroup("whoami", "the caller's profile, the instance root, the tools found");
  r.registerGroup("log", "this instance's command history");
  r.registerGroup("layer", "a layer: make one, see the chain, check it");
  r.registerGroup("ingest", "bytes on disk become artifact subjects");
  r.registerGroup("ontology", "the terms: list, show, effective rules, the pin, lints");
  r.registerGroup("claims", "a subject's lines: show, sort");
  r.registerGroup("tree", "an artifact's scope table in ord; derived addresses → intrinsic");
  r.registerGroup("resolve", "the bytes, derivation or reading at an address");
  r.registerGroup("lint", "G1–G4, per-file and per-term lints");
  r.registerGroup("verify", "bindings, derived status, demand, stale passes");
  r.registerGroup("harvest", "concept lines minted into the ledger");
  r.registerGroup("export", "the markdown proxy and the N-Quads projection");
  r.registerGroup("pass", "a pass: open, stage lines, sign, abandon");
  r.registerGroup("image", "a raster: the OCR proposal");
  r.registerGroup("serve", "the read surface over HTTP, by plane");
  r.registerGroup("inspect", "L7: readings against the bytes; the owner's acceptances");
  for (const def of [
    whoamiCommand,
    logCommand,
    layerInit,
    layerShow,
    layerCheck,
    ingest,
    ingestShow,
    ontologyList,
    ontologyShow,
    ontologyRules,
    ontologyHash,
    ontologyLint,
    claimsShow,
    claimsSort,
    tree,
    treeAt,
    resolveCmd,
    lint,
    verify,
    harvest,
    exportMarkdownCmd,
    exportNquads,
    passOpen,
    passList,
    passSign,
    passAbandon,
    claimsAppend,
    inspect,
    inspectAccept,
    inspectRevoke,
    imageWords,
    serve,
  ])
    r.register(def);
  return r;
}
