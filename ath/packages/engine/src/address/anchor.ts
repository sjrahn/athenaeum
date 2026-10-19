// anchor.ts — an anchor (spec §14.3.1): `ath://<blake3>?<at>[&<aspect>]`, a subject and an intrinsic address in it,
// the hash in full; and the check that an address names a region the artifact has (§7.4.3) — a page past its count,
// a byte past its end, a time past its duration, a row past its rows, a route to a path the container lacks.
import { AthError } from "@ath/kit/errors.ts";
import { type Address, formatAddress, parseAddress, type Region } from "./address.ts";

export interface Anchor {
  hash: string;
  address: Address;
}

/** Parse an anchor, or a bare hash (its `whole`). A prefix is the terminal's to resolve, never an anchor's. */
export function parseAnchor(s: string): Anchor {
  const m = /^(?:ath:\/\/)?(?:b3:)?([0-9a-f]{64})(?:\?(.+))?$/.exec(s.trim());
  if (!m) throw new AthError("USAGE", `'${s}' is not an anchor: ath://<blake3>?<at>`);
  return { hash: m[1]!, address: parseAddress(m[2] ?? "whole") };
}

export const formatAnchor = (a: Anchor): string => {
  const at = formatAddress(a.address);
  return at === "whole" ? `ath://${a.hash}` : `ath://${a.hash}?${at}`;
};

type J = Record<string, unknown>;

/** Why a region is not one the artifact has, by its intrinsics, or null. A route's rest is checked in its constituent. */
export function regionProblem(intrinsics: J, r: Region): string | null {
  if (r.whole) return null;
  if (r.path !== undefined) {
    const cs = (intrinsics.constituents as { path: string }[] | undefined) ?? [];
    return cs.some((c) => c.path === r.path) ? null : `the container has no constituent at path ${r.path}`;
  }
  const size = Number(intrinsics.bytes);
  if (r.bytes && r.bytes[1] > size) return `bytes=${r.bytes[0]},${r.bytes[1]} runs past the artifact's ${size} bytes`;
  if (r.page !== undefined) {
    const n = Number(intrinsics.page_count);
    if (!Number.isFinite(n)) return "the artifact has no pages";
    if (r.page > n) return `page ${r.page} is past its ${n} pages`;
  }
  if (r.row !== undefined && Number.isFinite(Number(intrinsics.rows)) && r.row >= Number(intrinsics.rows))
    return `row ${r.row} is past its ${intrinsics.rows} rows`;
  if (r.col !== undefined && Number.isFinite(Number(intrinsics.columns)) && r.row !== undefined && r.col >= Number(intrinsics.columns))
    return `col ${r.col} is past its ${intrinsics.columns} columns`;
  if (r.t && Number.isFinite(Number(intrinsics.duration)) && r.t[1] > Number(intrinsics.duration) + 1e-6)
    return `t=${r.t[0]},${r.t[1]} runs past its ${intrinsics.duration} s`;
  return null;
}
