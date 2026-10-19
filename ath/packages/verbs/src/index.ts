// index.ts — every verb of spec §19.5, registered by group. A verb is a contract over engine and custody functions;
// nothing here decides what the system means.
import type { Registry } from "@ath/kit/registry.ts";
import { ingestCommand } from "./ingest.ts";
import { instanceCheck, instanceInit, instanceRepin, instanceReshard, instanceShow } from "./instance.ts";
import { logCommand } from "./log.ts";
import { proposeCommand } from "./propose.ts";
import { holdingsCommand, provenanceCommand, recordCommand, showCommand, sortCommand, sweepCommand } from "./records.ts";
import { resolveCommand } from "./resolve.ts";
import { treeCommand } from "./tree.ts";
import { vocabAdd, vocabCheck, vocabEdit, vocabList, vocabPin, vocabRemove, vocabRules, vocabShow } from "./vocab.ts";
import { whoamiCommand } from "./whoami.ts";

export function registerVerbs(r: Registry): void {
  r.registerGroup("instance", "the instance and what it builds on");
  for (const c of [instanceInit, instanceShow, instanceCheck, instanceRepin, instanceReshard]) r.register(c);
  for (const c of [
    ingestCommand,
    holdingsCommand,
    recordCommand,
    provenanceCommand,
    showCommand,
    sortCommand,
    sweepCommand,
    resolveCommand,
    proposeCommand,
    treeCommand,
  ])
    r.register(c);
  r.registerGroup("vocab", "the forms, shapes, kinds and properties");
  for (const c of [vocabList, vocabShow, vocabRules, vocabPin, vocabCheck, vocabAdd, vocabEdit, vocabRemove]) r.register(c);
  r.register(whoamiCommand);
  r.register(logCommand);
}
