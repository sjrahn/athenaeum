// index.ts — the command table: every group registers here. Add a command by importing its def and listing it once.
import { createRegistry, type Registry } from "../kit/registry.ts";
import { claimsShow, claimsSort } from "./claims.ts";
import { ingest, ingestShow } from "./ingest.ts";
import { layerCheck, layerInit, layerShow } from "./layer.ts";
import { logCommand } from "./log.ts";
import { ontologyHash, ontologyLint, ontologyList, ontologyRules, ontologyShow } from "./ontology.ts";
import { whoamiCommand } from "./whoami.ts";

export function buildRegistry(): Registry {
  const r = createRegistry();
  r.registerGroup("whoami", "the caller's profile, the instance root, the tools found");
  r.registerGroup("log", "this instance's command history");
  r.registerGroup("layer", "a layer: make one, see the chain, check it");
  r.registerGroup("ingest", "bytes on disk become artifact subjects");
  r.registerGroup("ontology", "the terms: list, show, effective rules, the pin, lints");
  r.registerGroup("claims", "a subject's lines: show, sort");
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
  ])
    r.register(def);
  return r;
}
