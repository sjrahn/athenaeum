// index.ts — custody (spec §18): the stores that keep artifacts and testimony, the host index that believes where
// they are, the policies and reconcile that keep them, and resolution by hash. Knows nothing of records or the graph;
// the labels a policy selects on are handed in.
export { type Driver, driverFor, localDriver, type ManifestInfo, type ObservedFile, observedDriver, rcloneDriver } from "./drivers.ts";
export { type Copy, type CopyState, type CustodyIndex, type ObservedRow, openIndex, type ReceiptRow } from "./index-db.ts";
export { type LocalStore, openLocalStore, type Tree } from "./local.ts";
export {
  applies,
  type CopyView,
  confinedAway,
  counting,
  DEFAULT_POLICY,
  evaluate,
  type Finding,
  holdsWithout,
  type Labels,
  loadPolicies,
  type Policy,
  parsePolicy,
} from "./policy.ts";
export {
  type Action,
  type Holding,
  inventory,
  type PerformDeps,
  type PlanCtx,
  perform,
  plan,
  removeCopy,
  type Site,
  status,
  verifyCopy,
} from "./reconcile.ts";
export { type Readable, type ResolveDeps, type Resolved, resolveHash, type Trace, traceLines } from "./resolve.ts";
export {
  type Access,
  emitAccess,
  emitStore,
  type LocalDecl,
  loadAccess,
  loadStores,
  parseSize,
  parseStore,
  type StoreDecl,
  tagsMatch,
} from "./stores.ts";
