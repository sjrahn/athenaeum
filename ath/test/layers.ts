// layers.ts — test helpers: a foundation carrying the testdata ontology, and an extension over it.
import { cpSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { serializeConfig } from "../src/engine/layer/config.ts";
import { scratch } from "./harness.ts";

export const TESTDATA = join(import.meta.dir, "../../testdata");
export const ONTOLOGY_DIR = join(TESTDATA, "ontology");

/** A foundation layer with the regression ontology copied in. */
export function foundation(withOntology = true): string {
  const root = join(scratch("ath-foundation-"), "foundation");
  mkdirSync(root, { recursive: true });
  for (const d of ["ontology", "corpus", "ledger", ".ath"]) mkdirSync(join(root, d), { recursive: true });
  if (withOntology) cpSync(ONTOLOGY_DIR, join(root, "ontology"), { recursive: true });
  writeFileSync(join(root, "athenaeum.yaml"), serializeConfig({ successor: true, name: "foundation", layer: "foundation" }));
  return root;
}

export function extension(foundationRoot: string, name = "mine"): string {
  const root = join(scratch("ath-extension-"), name);
  mkdirSync(root, { recursive: true });
  for (const d of ["ontology", "corpus", "ledger", ".ath"]) mkdirSync(join(root, d), { recursive: true });
  writeFileSync(
    join(root, "athenaeum.yaml"),
    serializeConfig({ successor: true, name, layer: "extension", extends: foundationRoot, tier: "private" }),
  );
  return root;
}
