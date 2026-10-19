// index.ts — custody (spec §18): the stores that keep artifacts and testimony, the host index that believes where
// they are, the policies and reconcile that keep them, and resolution by hash. Knows nothing of records or the graph;
// the labels a policy selects on are handed in.
export { type Copy, type CopyState, type CustodyIndex, openIndex, type ReceiptRow } from "./index-db.ts";
export { type LocalStore, openLocalStore, type Tree } from "./local.ts";
