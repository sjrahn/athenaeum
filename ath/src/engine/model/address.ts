// address.ts — the intrinsic address `at` (spec §5.2): parse, canonicalise, compare, contain. Axes are coordinates in
// the bytes; a union `a;b;c` is one box per page for a container that spans pages; a trailing `&text|&cells|&tex`
// names the reading surface a quote is taken from and is never part of a scope's identity.
import { AthError } from "../../kit/errors.ts";

export type Aspect = "text" | "cells" | "tex";
export const ASPECTS: readonly Aspect[] = ["text", "cells", "tex"];

export type Box = readonly [x: number, y: number, w: number, h: number];

export type Member =
  | { kind: "whole" }
  | { kind: "page"; page: number; box?: Box }
  | { kind: "bbox"; box: Box }
  | { kind: "bytes"; start: number; end: number }
  | { kind: "row"; row: number; col?: number }
  | { kind: "time"; start: number; end: number }
  | { kind: "path"; path: string };

export interface Address {
  members: Member[];
  aspect?: Aspect;
}

export const DECIMALS = 4;

/** A coordinate as the files spell it: at most 4 decimals, no trailing zeros, no exponent. */
export function fmt(n: number): string {
  const r = Math.round(n * 10 ** DECIMALS) / 10 ** DECIMALS;
  return Object.is(r, -0) ? "0" : String(r);
}

function num(s: string, what: string): number {
  if (!/^-?\d+(\.\d+)?$/.test(s)) throw new AthError("USAGE", `address: ${what} is not a number: '${s}'`);
  return Number(s);
}

function parseBox(s: string): Box {
  const p = s.split(",");
  if (p.length !== 4) throw new AthError("USAGE", `address: bbox needs x,y,w,h: '${s}'`);
  return [num(p[0]!, "bbox x"), num(p[1]!, "bbox y"), num(p[2]!, "bbox w"), num(p[3]!, "bbox h")];
}

function parseMember(s: string): Member {
  if (s === "whole") return { kind: "whole" };
  const params = new Map<string, string>();
  for (const part of s.split("&")) {
    const eq = part.indexOf("=");
    if (eq === -1) throw new AthError("USAGE", `address: '${part}' has no value`);
    params.set(part.slice(0, eq), part.slice(eq + 1));
  }
  const keys = [...params.keys()];
  const only = (allowed: string[]) => {
    for (const k of keys) if (!allowed.includes(k)) throw new AthError("USAGE", `address: '${k}' does not belong with ${allowed[0]}=`);
  };
  if (params.has("page")) {
    only(["page", "bbox"]);
    const page = num(params.get("page")!, "page");
    if (!Number.isInteger(page) || page < 1)
      throw new AthError("USAGE", `address: page must be a positive integer: '${params.get("page")}'`);
    const m: Member = { kind: "page", page };
    if (params.has("bbox")) m.box = parseBox(params.get("bbox")!);
    return m;
  }
  if (params.has("bbox")) {
    only(["bbox"]);
    return { kind: "bbox", box: parseBox(params.get("bbox")!) };
  }
  if (params.has("bytes")) {
    only(["bytes"]);
    const p = params.get("bytes")!.split(",");
    if (p.length !== 2) throw new AthError("USAGE", `address: bytes needs start,end: '${params.get("bytes")}'`);
    const start = num(p[0]!, "bytes start");
    const end = num(p[1]!, "bytes end");
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start)
      throw new AthError("USAGE", `address: bad byte range ${start},${end}`);
    return { kind: "bytes", start, end };
  }
  if (params.has("row")) {
    only(["row", "col"]);
    const row = num(params.get("row")!, "row");
    const m: Member = { kind: "row", row };
    if (params.has("col")) m.col = num(params.get("col")!, "col");
    return m;
  }
  if (params.has("t")) {
    only(["t"]);
    const p = params.get("t")!.split(",");
    if (p.length !== 2) throw new AthError("USAGE", `address: t needs start,end: '${params.get("t")}'`);
    return { kind: "time", start: num(p[0]!, "t start"), end: num(p[1]!, "t end") };
  }
  if (params.has("path")) {
    only(["path"]);
    return { kind: "path", path: decodeURIComponent(params.get("path")!) };
  }
  throw new AthError("USAGE", `address: no axis in '${s}'`);
}

/** Parse an `at` (optionally with a trailing aspect). */
export function parseAddress(at: string): Address {
  let s = at.trim();
  if (!s) throw new AthError("USAGE", "address: empty");
  let aspect: Aspect | undefined;
  const m = /&(text|cells|tex)$/.exec(s);
  if (m) {
    aspect = m[1] as Aspect;
    s = s.slice(0, -m[0].length);
  }
  const members = s.split(";").map((p) => parseMember(p.trim()));
  if (members.length > 1 && members.some((x) => x.kind === "whole"))
    throw new AthError("USAGE", "address: 'whole' cannot be a union member");
  const a: Address = { members };
  if (aspect) a.aspect = aspect;
  return a;
}

export function formatMember(m: Member): string {
  switch (m.kind) {
    case "whole":
      return "whole";
    case "page":
      return `page=${m.page}${m.box ? `&bbox=${m.box.map(fmt).join(",")}` : ""}`;
    case "bbox":
      return `bbox=${m.box.map(fmt).join(",")}`;
    case "bytes":
      return `bytes=${m.start},${m.end}`;
    case "row":
      return `row=${m.row}${m.col !== undefined ? `&col=${m.col}` : ""}`;
    case "time":
      return `t=${fmt(m.start)},${fmt(m.end)}`;
    case "path":
      return `path=${encodeURIComponent(m.path)}`;
  }
}

const memberSortKey = (m: Member): number[] => {
  switch (m.kind) {
    case "whole":
      return [0];
    case "page":
      return [1, m.page, m.box ? m.box[1] : -1, m.box ? m.box[0] : -1, m.box ? m.box[2] : -1, m.box ? m.box[3] : -1];
    case "bbox":
      return [2, m.box[1], m.box[0], m.box[2], m.box[3]];
    case "bytes":
      return [3, m.start, m.end];
    case "row":
      return [4, m.row, m.col ?? -1];
    case "time":
      return [5, m.start, m.end];
    case "path":
      return [6];
  }
};

function cmpKeys(a: number[], b: number[]): number {
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const x = a[i] ?? -Infinity;
    const y = b[i] ?? -Infinity;
    if (x !== y) return x < y ? -1 : 1;
  }
  return 0;
}

/** The canonical spelling: members sorted by page, y, x; numbers at 4 decimals; aspect kept. */
export function formatAddress(a: Address): string {
  const members = [...a.members].sort((x, y) => {
    const c = cmpKeys(memberSortKey(x), memberSortKey(y));
    return c !== 0 ? c : x.kind === "path" && y.kind === "path" ? x.path.localeCompare(y.path) : 0;
  });
  return members.map(formatMember).join(";") + (a.aspect ? `&${a.aspect}` : "");
}

export const canonicalAt = (at: string): string => formatAddress(parseAddress(at));

/** The scope's identity: the canonical address without its aspect. */
export function scopeAt(at: string): string {
  const a = parseAddress(at);
  return formatAddress({ members: a.members });
}

/** Sort key for a file: addresses in reading-neutral order (whole, then pages top-down, then the rest). */
export function compareAt(a: string, b: string): number {
  const pa = parseAddress(a).members;
  const pb = parseAddress(b).members;
  const n = Math.max(pa.length, pb.length);
  for (let i = 0; i < n; i++) {
    const x = pa[i];
    const y = pb[i];
    if (!x) return -1;
    if (!y) return 1;
    const c = cmpKeys(memberSortKey(x), memberSortKey(y));
    if (c !== 0) return c;
    if (x.kind === "path" && y.kind === "path" && x.path !== y.path) return x.path < y.path ? -1 : 1;
  }
  return 0;
}

export const SLACK = 0.002;

function boxContains(outer: Box, inner: Box, slack = SLACK): boolean {
  return (
    inner[0] >= outer[0] - slack &&
    inner[1] >= outer[1] - slack &&
    inner[0] + inner[2] <= outer[0] + outer[2] + slack &&
    inner[1] + inner[3] <= outer[1] + outer[3] + slack
  );
}

function memberContains(outer: Member, inner: Member): boolean {
  if (outer.kind === "whole") return true;
  if (inner.kind === "whole") return false;
  switch (outer.kind) {
    case "page":
      if (inner.kind !== "page" || inner.page !== outer.page) return false;
      if (!outer.box) return true;
      return inner.box !== undefined && boxContains(outer.box, inner.box);
    case "bbox":
      return inner.kind === "bbox" && boxContains(outer.box, inner.box);
    case "bytes":
      return inner.kind === "bytes" && inner.start >= outer.start && inner.end <= outer.end;
    case "row":
      return inner.kind === "row" && inner.row === outer.row && (outer.col === undefined || inner.col === outer.col);
    case "time":
      return inner.kind === "time" && inner.start >= outer.start - 1e-6 && inner.end <= outer.end + 1e-6;
    case "path":
      return inner.kind === "path" && inner.path === outer.path;
  }
}

/** Whether every member of `inner` lies inside some member of `outer`. */
export function contains(outer: string | Address, inner: string | Address): boolean {
  const o = typeof outer === "string" ? parseAddress(outer) : outer;
  const i = typeof inner === "string" ? parseAddress(inner) : inner;
  return i.members.every((im) => o.members.some((om) => memberContains(om, im)));
}

/** The centre of a box, for "the word's centre lies in the scope" tests. */
export const centre = (b: Box): [number, number] => [b[0] + b[2] / 2, b[1] + b[3] / 2];

export function pointInBox(b: Box, x: number, y: number, slack = SLACK): boolean {
  return x >= b[0] - slack && x <= b[0] + b[2] + slack && y >= b[1] - slack && y <= b[1] + b[3] + slack;
}

/** The union of boxes on one page. */
export function unionBox(boxes: readonly Box[]): Box {
  const x0 = Math.min(...boxes.map((b) => b[0]));
  const y0 = Math.min(...boxes.map((b) => b[1]));
  const x1 = Math.max(...boxes.map((b) => b[0] + b[2]));
  const y1 = Math.max(...boxes.map((b) => b[1] + b[3]));
  const r = (n: number) => Math.round(n * 10 ** DECIMALS) / 10 ** DECIMALS;
  return [r(x0), r(y0), r(x1 - x0), r(y1 - y0)];
}

/** The pages an address touches (empty for non-page axes). */
export function pagesOf(a: Address): number[] {
  return [...new Set(a.members.flatMap((m) => (m.kind === "page" ? [m.page] : [])))].sort((x, y) => x - y);
}

/** Does `at` name a physical page as a whole (`page=N`, no box)? */
export function isPageAt(at: string): boolean {
  const a = parseAddress(at);
  return a.members.length === 1 && a.members[0]!.kind === "page" && a.members[0]!.box === undefined;
}

export const isWhole = (at: string): boolean => parseAddress(at).members[0]!.kind === "whole";
