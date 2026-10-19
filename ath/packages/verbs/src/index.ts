// index.ts — every verb of spec §19.5, registered by group. A verb is a contract over engine and custody functions;
// nothing here decides what the system means.
import type { Registry } from "@ath/kit/registry.ts";
import { logCommand } from "./log.ts";
import { whoamiCommand } from "./whoami.ts";

export function registerVerbs(r: Registry): void {
  r.register(whoamiCommand);
  r.register(logCommand);
}
