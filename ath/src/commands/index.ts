// index.ts — the command table: every group registers here. Add a command by importing its def and listing it once.
import { createRegistry, type Registry } from "../kit/registry.ts";
import { logCommand } from "./log.ts";
import { whoamiCommand } from "./whoami.ts";

export function buildRegistry(): Registry {
  const r = createRegistry();
  r.registerGroup("whoami", "the caller's profile, the instance root, the tools found");
  r.registerGroup("log", "this instance's command history");
  for (const def of [whoamiCommand, logCommand]) r.register(def);
  return r;
}
