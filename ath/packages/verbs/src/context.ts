// context.ts — what a verb opens: the instance and its chain, the host's local store and custody index.
import { join } from "node:path";
import { type CustodyIndex, type LocalStore, openIndex, openLocalStore } from "@ath/custody";
import { type Instance, openInstance } from "@ath/engine/instance/instance.ts";
import { AthError } from "@ath/kit/errors.ts";
import type { KitCtx } from "@ath/kit/types.ts";

export function instanceOf(ctx: KitCtx): Instance {
  if (!ctx.root) throw new AthError("CONFIG", "no instance (--root, $ATHENAEUM_ROOT, or an athenaeum.yaml above the cwd)");
  return openInstance(ctx.root, ctx.host);
}

export const localStore = (ctx: KitCtx): LocalStore => openLocalStore(ctx.host.data);
export const custodyIndex = (ctx: KitCtx): CustodyIndex => openIndex(join(ctx.host.state, "index.sqlite"));
