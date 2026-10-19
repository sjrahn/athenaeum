// address.ts — the intrinsic address `at` (spec §7.3, §7.4): parse, canonicalise, order, contain. Every axis is a
// coordinate in the bytes as stored. A union `a;b;c` is one scope made of several regions; a route `path=p` may stand
// anywhere in a region and the rest of the region applies in that constituent; a trailing `&text|&cells|&tex` names
// the reading a quote is taken from and is never part of a scope's identity.
//
// Canonical form: a number in its shortest form (a box at most 4 decimals; a page, row, column or byte offset an
// integer; no sign); the axes of a region in one order — path, page, row, t, bbox, bytes, col — so `page=N&bbox=…`,
// `row=N&col=M`, `t=a,b&bbox=…`, `path=p&bytes=a,b` and a row's cell `…&col=M` read as §7.3.1 spells them; the
// regions of a union sorted by page, then row, then time, then y, then x, then byte start, `path` last, none twice;
// a `path` value percent-encoded where it holds `;`, `&`, `=`, `%` or a code point outside printable ASCII.
import { AthError } from "@ath/kit/errors.ts";

export type Aspect = "text" | "cells" | "tex";
export const ASPECTS: readonly Aspect[] = ["text", "cells", "tex"];

export type Box = readonly [x: number, y: number, w: number, h: number];

/** One region: the axes it has. `whole` is a region of its own and stands alone. */
export interface Region {
  whole?: true;
  path?: string;
  page?: number;
  row?: number;
  t?: readonly [number, number];
  bbox?: Box;
  bytes?: readonly [number, number];
  col?: number;
}

export interface Address {
  regions: Region[];
  aspect?: Aspect;
}

export const DECIMALS = 4;
export const SLACK = 0.002;

const bad = (m: string): never => {
  throw new AthError("USAGE", `address: ${m}`);
};

/** A box coordinate as the files spell it: at most 4 decimals, no trailing zeros, no exponent, no sign. */
export function fmt(n: number): string {
  const r = Math.round(n * 10 ** DECIMALS) / 10 ** DECIMALS;
  return Object.is(r, -0) ? "0" : String(r);
}

/** A time in seconds in its shortest form. */
const fmtTime = (n: number): string => (Object.is(n, -0) ? "0" : String(n));

function num(s: string, what: string): number {
  if (!/^\d+(\.\d+)?$/.test(s)) bad(`${what} is not a non-negative number: '${s}'`);
  return Number(s);
}

function int(s: string, what: string): number {
  if (!/^\d+$/.test(s)) bad(`${what} is not an integer: '${s}'`);
  return Number(s);
}

function pair(s: string, what: string, parse: (x: string, w: string) => number): [number, number] {
  const p = s.split(",");
  if (p.length !== 2) bad(`${what} needs a,b: '${s}'`);
  const a = parse(p[0]!, `${what} start`);
  const b = parse(p[1]!, `${what} end`);
  if (b < a) bad(`${what} ends before it starts: ${s}`);
  return [a, b];
}

function parseBox(s: string): Box {
  const p = s.split(",");
  if (p.length !== 4) bad(`bbox needs x,y,w,h: '${s}'`);
  const b = [num(p[0]!, "bbox x"), num(p[1]!, "bbox y"), num(p[2]!, "bbox w"), num(p[3]!, "bbox h")] as const;
  if (b[0] > 1 || b[1] > 1 || b[0] + b[2] > 1 + SLACK || b[1] + b[3] > 1 + SLACK) bad(`bbox lies outside the frame: '${s}'`);
  return b;
}

const SAFE = /^[\x20-\x7e]$/u;
const RESERVED = new Set([";", "&", "=", "%"]);

/** Percent-encode a path where it holds `;`, `&`, `=`, `%` or a code point outside printable ASCII (§7.4.3). */
export function encodePath(p: string): string {
  let out = "";
  for (const ch of p) {
    if (SAFE.test(ch) && !RESERVED.has(ch)) out += ch;
    else for (const b of new TextEncoder().encode(ch)) out += `%${b.toString(16).toUpperCase().padStart(2, "0")}`;
  }
  return out;
}

export function decodePath(p: string): string {
  try {
    return decodeURIComponent(p);
  } catch {
    return bad(`path is not valid percent-encoding: '${p}'`);
  }
}

function parseRegion(s: string): Region {
  if (s === "whole") return { whole: true };
  const r: Region = {};
  for (const part of s.split("&")) {
    const eq = part.indexOf("=");
    if (eq === -1) bad(`'${part}' has no value`);
    const k = part.slice(0, eq);
    const v = part.slice(eq + 1);
    if (k in r) bad(`'${k}' is given twice in one region`);
    switch (k) {
      case "path":
        if (!v) bad("path is empty");
        r.path = decodePath(v);
        break;
      case "page":
        r.page = int(v, "page");
        if (r.page < 1) bad("page is 1-based");
        break;
      case "row":
        r.row = int(v, "row");
        break;
      case "col":
        r.col = int(v, "col");
        break;
      case "t":
        r.t = pair(v, "t", num);
        break;
      case "bbox":
        r.bbox = parseBox(v);
        break;
      case "bytes":
        r.bytes = pair(v, "bytes", int);
        break;
      default:
        bad(`'${k}' is not an axis`);
    }
  }
  const has = (k: keyof Region) => r[k] !== undefined;
  const axes = (["page", "row", "t", "bbox", "bytes"] as const).filter(has);
  const ok =
    axes.length === 0
      ? has("col") || has("path")
      : (axes.length === 1 && (axes[0] !== "t" || !has("col"))) ||
        (axes.length === 2 && ((has("page") && has("bbox")) || (has("t") && has("bbox") && !has("col"))));
  if (!ok) bad(`'${s}' combines axes no format has`);
  if (has("bytes") && has("col")) bad(`'${s}': a byte span has no columns`);
  return r;
}

/** Parse an `at`, optionally with a trailing aspect. */
export function parseAddress(at: string): Address {
  let s = at.trim();
  if (!s) bad("empty");
  let aspect: Aspect | undefined;
  const m = /&(text|cells|tex)$/.exec(s);
  if (m) {
    aspect = m[1] as Aspect;
    s = s.slice(0, -m[0].length);
  }
  const regions = s.split(";").map((p) => parseRegion(p.trim()));
  if (regions.length > 1 && regions.some((x) => x.whole)) bad("'whole' cannot be part of a union");
  const a: Address = { regions };
  if (aspect) a.aspect = aspect;
  return a;
}

export function formatRegion(r: Region): string {
  if (r.whole) return "whole";
  const out: string[] = [];
  if (r.path !== undefined) out.push(`path=${encodePath(r.path)}`);
  if (r.page !== undefined) out.push(`page=${r.page}`);
  if (r.row !== undefined) out.push(`row=${r.row}`);
  if (r.t) out.push(`t=${fmtTime(r.t[0])},${fmtTime(r.t[1])}`);
  if (r.bbox) out.push(`bbox=${r.bbox.map(fmt).join(",")}`);
  if (r.bytes) out.push(`bytes=${r.bytes[0]},${r.bytes[1]}`);
  if (r.col !== undefined) out.push(`col=${r.col}`);
  return out.join("&");
}

const INF = Number.POSITIVE_INFINITY;
/** The union order (§7.4.2): page, row, time, y, x, byte start; a route last, by its path. */
function regionKey(r: Region): number[] {
  if (r.whole) return [-1];
  return [
    r.path === undefined ? 0 : 1,
    r.page ?? -1,
    r.row ?? -1,
    r.t?.[0] ?? -1,
    r.bbox ? Math.round(r.bbox[1] * 1e4) : -1,
    r.bbox ? Math.round(r.bbox[0] * 1e4) : -1,
    r.bytes?.[0] ?? -1,
    r.t?.[1] ?? -1,
    r.bytes?.[1] ?? -1,
    r.bbox ? Math.round(r.bbox[3] * 1e4) : -1,
    r.bbox ? Math.round(r.bbox[2] * 1e4) : -1,
    r.col ?? -1,
  ];
}

function compareRegions(a: Region, b: Region): number {
  const ka = regionKey(a);
  const kb = regionKey(b);
  if (ka[0] === 1 && kb[0] === 1 && a.path !== b.path) return a.path! < b.path! ? -1 : 1;
  for (let i = 0; i < Math.max(ka.length, kb.length); i++) {
    const x = ka[i] ?? -INF;
    const y = kb[i] ?? -INF;
    if (x !== y) return x < y ? -1 : 1;
  }
  return 0;
}

/** The canonical spelling: regions sorted and deduplicated, axes in order, numbers in shortest form, aspect kept. */
export function formatAddress(a: Address): string {
  const seen = new Set<string>();
  const parts: string[] = [];
  for (const r of [...a.regions].sort(compareRegions)) {
    const s = formatRegion(r);
    if (!seen.has(s)) {
      seen.add(s);
      parts.push(s);
    }
  }
  return parts.join(";") + (a.aspect ? `&${a.aspect}` : "");
}

export const canonicalAt = (at: string): string => formatAddress(parseAddress(at));

/** The scope's identity: the canonical address without its aspect. */
export const scopeAt = (at: string): string => formatAddress({ regions: parseAddress(at).regions });

/** The order addresses are listed in a record: the first region's union order, then the next. */
export function compareAt(a: string, b: string): number {
  const pa = parseAddress(a).regions.sort(compareRegions);
  const pb = parseAddress(b).regions.sort(compareRegions);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const x = pa[i];
    const y = pb[i];
    if (!x) return -1;
    if (!y) return 1;
    const c = compareRegions(x, y);
    if (c !== 0) return c;
  }
  return 0;
}

function boxContains(outer: Box, inner: Box, slack = SLACK): boolean {
  return (
    inner[0] >= outer[0] - slack &&
    inner[1] >= outer[1] - slack &&
    inner[0] + inner[2] <= outer[0] + outer[2] + slack &&
    inner[1] + inner[3] <= outer[1] + outer[3] + slack
  );
}

const within = (o: readonly [number, number], i: readonly [number, number], eps = 0) => i[0] >= o[0] - eps && i[1] <= o[1] + eps;

function regionContains(o: Region, i: Region): boolean {
  if (o.whole) return true;
  if (i.whole) return false;
  if (o.path !== i.path) return false;
  if (o.page !== undefined && i.page !== o.page) return false;
  if (o.row !== undefined && i.row !== o.row) return false;
  if (o.t && !(i.t && within(o.t, i.t, 1e-6))) return false;
  if (o.bbox && !(i.bbox && boxContains(o.bbox, i.bbox))) return false;
  if (o.bytes && !(i.bytes && within(o.bytes, i.bytes))) return false;
  if (o.col !== undefined && i.col !== o.col) return false;
  // a narrower outer must not lose an axis the inner lacks: `page=1&bbox` does not contain `page=1`
  return !(i.page === undefined && o.page !== undefined) && !(i.bbox === undefined && o.bbox !== undefined);
}

/** Whether every region of `inner` lies inside some region of `outer`. Containment is never coverage (§8.5.1). */
export function contains(outer: string | Address, inner: string | Address): boolean {
  const o = typeof outer === "string" ? parseAddress(outer) : outer;
  const i = typeof inner === "string" ? parseAddress(inner) : inner;
  return i.regions.every((ir) => o.regions.some((or) => regionContains(or, ir)));
}

export const centre = (b: Box): [number, number] => [b[0] + b[2] / 2, b[1] + b[3] / 2];

export function pointInBox(b: Box, x: number, y: number, slack = SLACK): boolean {
  return x >= b[0] - slack && x <= b[0] + b[2] + slack && y >= b[1] - slack && y <= b[1] + b[3] + slack;
}

/** The smallest box holding every box, at 4 decimals. */
export function unionBox(boxes: readonly Box[]): Box {
  const x0 = Math.min(...boxes.map((b) => b[0]));
  const y0 = Math.min(...boxes.map((b) => b[1]));
  const x1 = Math.max(...boxes.map((b) => b[0] + b[2]));
  const y1 = Math.max(...boxes.map((b) => b[1] + b[3]));
  const r = (n: number) => Math.round(n * 10 ** DECIMALS) / 10 ** DECIMALS;
  return [r(x0), r(y0), r(x1 - x0), r(y1 - y0)];
}

/** The pages an address touches. */
export const pagesOf = (a: Address): number[] =>
  [...new Set(a.regions.flatMap((r) => (r.page !== undefined ? [r.page] : [])))].sort((x, y) => x - y);

/** Whether `at` names a physical page whole (`page=N`). */
export function isPageAt(at: string): boolean {
  const r = parseAddress(at).regions;
  return r.length === 1 && r[0]!.page !== undefined && Object.keys(r[0]!).length === 1;
}

export const isWhole = (at: string): boolean => parseAddress(at).regions[0]!.whole === true;
