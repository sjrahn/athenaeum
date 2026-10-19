// document.ts — a record (spec §8.1–§8.2): one YAML document about one artifact, written only by the tool, in one
// style. Keys in a fixed order — `intrinsics`, `receipts`, `origins`, `shape`, `chrome`, `passes`, then `readings` or
// `scopes`; a pass's keys `by, verify, vocab, date, over, attests, note`; a receipt's `actor, received, name`; a scope's
// `form, at`, its fields in code-point order, its reading under its aspect, `scopes`. Readings are listed by address
// in the union order (§7.4.2). A multi-line body is a literal block; a scalar is written plain only where it begins
// with a letter, is no YAML keyword and holds no indicator, and is otherwise quoted as JSON — so no YAML reader, 1.1
// or 1.2, reads anything but a string where a string was written. Loading refuses a document that does not parse,
// a key the grammar lacks, and both `readings` and `scopes`.
import { byCodePoint } from "@ath/kit/canonical.ts";
import { AthError } from "@ath/kit/errors.ts";
import { ASPECTS, type Aspect, compareAt } from "../address/address.ts";

export type J = Record<string, unknown>;

/** One reading: one body per aspect (§8.3.1). `cells` is one row: a list of cell strings. */
export interface Reading {
  text?: string;
  cells?: string[];
  tex?: string;
}

/** One scope of the tree (§8.4.1): its form(s), its address, its fields, its reading, its children. */
export interface Scope {
  form: string | string[];
  at: string;
  text?: string;
  cells?: string[];
  tex?: string;
  scopes?: Scope[];
  [field: string]: unknown;
}

/** What a pass names it covers (§8.5.1): reading addresses, or the kinds `tree`, `shape`, `chrome`. */
export interface Pass {
  by: string;
  verify: string;
  vocab: string;
  date: string;
  over?: string[];
  attests?: ("readings" | "structure")[];
  note?: string;
}

export interface Receipt {
  actor: string;
  received: string;
  name: string;
}

export interface RecordDoc {
  /** Absent only on an extension's record of its base's artifact, which holds its own receipts and origins (§4.4). */
  intrinsics?: J;
  receipts?: Receipt[];
  origins?: J[];
  shape?: string;
  chrome?: J[];
  passes?: { [id: string]: Pass };
  readings?: { [at: string]: Reading };
  scopes?: Scope[];
}

export const RECORD_KEYS = ["intrinsics", "receipts", "origins", "shape", "chrome", "passes", "readings", "scopes"] as const;
const PASS_KEYS = ["by", "verify", "vocab", "date", "over", "attests", "note"] as const;
const RECEIPT_KEYS = ["actor", "received", "name"] as const;
const SCOPE_FIXED = new Set(["form", "at", "scopes", ...ASPECTS]);

// ── scalars ─────────────────────────────────────────────────────────────────────────────────────────────────────────

const KEYWORD = /^(true|false|yes|no|on|off|y|n|null|~)$/i;

/** Whether a string may be written plain: in block context, or (`flow`) inside `[…]` / `{…}`. */
export function plainOk(v: string, flow: boolean): boolean {
  return (
    /^[A-Za-z]/.test(v) &&
    // biome-ignore lint/suspicious/noControlCharactersInRegex: control characters are what this refuses
    !/[\u0000-\u001f\u007f\u0085\u2028\u2029]/.test(v) &&
    !/: | #|:$/.test(v) &&
    !/\s$/.test(v) &&
    !KEYWORD.test(v) &&
    !(flow && /[,[\]{}]/.test(v))
  );
}

const scalar = (v: unknown, flow = false): string => {
  if (typeof v === "string") return plainOk(v, flow) ? v : JSON.stringify(v);
  if (v === null) return "null";
  if (typeof v === "number" || typeof v === "boolean") return JSON.stringify(v);
  throw new AthError("INTERNAL", `record: cannot write ${typeof v} as a scalar`);
};

/** A value in flow style: `[a, b]`, `{k: v}`, scalars as `scalar` says. */
export function flow(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(flow).join(", ")}]`;
  if (v && typeof v === "object")
    return `{${Object.entries(v as J)
      .filter(([, x]) => x !== undefined)
      .map(([k, x]) => `${scalar(k, true)}: ${flow(x)}`)
      .join(", ")}}`;
  return scalar(v, true);
}

/** Whether a multi-line string is faithfully a literal block (`|-`): its first line non-blank and unindented, no
 * trailing newline or trailing blanks on a line, no carriage return or other break YAML would fold. */
const literalOk = (v: string): boolean =>
  v.includes("\n") && /^\S/.test(v) && !v.endsWith("\n") && !/[\r\u0085\u2028\u2029]/.test(v) && !/[ \t]\n|[ \t]$/.test(v);

/** One `key: value` line in block context, a multi-line string as a literal block. */
function entry(key: string, v: unknown, ind: string): string {
  if (typeof v === "string" && literalOk(v))
    return `${ind}${scalar(key)}: |-\n${v
      .split("\n")
      .map((l) => (l ? `${ind}  ${l}` : ""))
      .join("\n")}\n`;
  return `${ind}${scalar(key)}: ${typeof v === "string" ? scalar(v) : flow(v)}\n`;
}

// ── the document ────────────────────────────────────────────────────────────────────────────────────────────────────

const ordered = <T extends J>(o: T, keys: readonly string[]): J =>
  Object.fromEntries([
    ...keys.filter((k) => o[k] !== undefined).map((k) => [k, o[k]]),
    ...Object.entries(o).filter(([k]) => !keys.includes(k)),
  ]);

/** A pass's ids in numeric order: p1, p2, … p10. */
export const passOrder = (a: string, b: string): number => Number(a.slice(1)) - Number(b.slice(1)) || byCodePoint(a, b);

function scopeLines(sc: Scope, ind: string): string {
  const { form, at, scopes, ...rest } = sc;
  const fields = Object.keys(rest)
    .filter((k) => !ASPECTS.includes(k as Aspect) && rest[k] !== undefined)
    .sort(byCodePoint);
  const reading = ASPECTS.filter((a) => rest[a] !== undefined).sort(byCodePoint);
  let out = entry("form", form, `${ind}  `).replace(`${ind}  `, `${ind}- `);
  out += entry("at", at, `${ind}  `);
  for (const k of [...fields, ...reading]) out += entry(k, rest[k], `${ind}  `);
  if (scopes?.length) out += `${ind}  scopes:\n${scopes.map((c) => scopeLines(c, `${ind}    `)).join("")}`;
  return out;
}

/** `intrinsics` as a block mapping: each value in flow, but a list of mappings — a container's constituents, a
 * message's part table — as a block list, one entry per line, so a large container stays readable and diffable. */
function intrinsicsLines(v: J): string {
  if (!Object.values(v).some((x) => x !== undefined)) return "intrinsics: {}\n";
  let out = "intrinsics:\n";
  for (const [k, x] of Object.entries(v)) {
    if (x === undefined) continue;
    if (Array.isArray(x) && x.length && x.every((e) => e && typeof e === "object" && !Array.isArray(e)))
      out += `  ${scalar(k)}:\n${x.map((e) => `    - ${flow(e)}\n`).join("")}`;
    else out += entry(k, x, "  ");
  }
  return out;
}

/** The record in its one style. */
export function emitRecord(r: RecordDoc): string {
  let out = r.intrinsics ? intrinsicsLines(r.intrinsics) : "";
  if (r.receipts?.length) out += `receipts:\n${r.receipts.map((e) => `  - ${flow(ordered(e as unknown as J, RECEIPT_KEYS))}\n`).join("")}`;
  if (r.origins?.length) out += `origins:\n${r.origins.map((e) => `  - ${flow(e)}\n`).join("")}`;
  if (r.shape !== undefined) out += `shape: ${scalar(r.shape)}\n`;
  if (r.chrome?.length) out += `chrome:\n${r.chrome.map((c) => `  - ${flow(c)}\n`).join("")}`;
  if (r.passes && Object.keys(r.passes).length)
    out += `passes:\n${Object.keys(r.passes)
      .sort(passOrder)
      .map((id) => `  ${scalar(id)}: ${flow(ordered(r.passes![id] as unknown as J, PASS_KEYS))}\n`)
      .join("")}`;
  if (r.readings) {
    out += "readings:\n";
    for (const at of Object.keys(r.readings).sort(compareAt)) {
      const body = r.readings[at]!;
      out += `  ${scalar(at)}:\n`;
      for (const a of ASPECTS.filter((x) => body[x] !== undefined).sort(byCodePoint)) out += entry(a, body[a], "    ");
    }
  }
  if (r.scopes) out += `scopes:\n${r.scopes.map((s) => scopeLines(s, "  ")).join("")}`;
  return out;
}

// ── loading ─────────────────────────────────────────────────────────────────────────────────────────────────────────

const isObj = (v: unknown): v is J => !!v && typeof v === "object" && !Array.isArray(v);
const isStrList = (v: unknown): v is string[] => Array.isArray(v) && v.every((x) => typeof x === "string");

function checkBody(o: J, where: string, refuse: (m: string) => never): void {
  for (const a of ASPECTS) {
    const v = o[a];
    if (v === undefined) continue;
    if (a === "cells" ? !isStrList(v) : typeof v !== "string")
      refuse(`${where}: \`${a}\` is ${a === "cells" ? "a list of cell strings" : "a string"}`);
  }
}

function checkScope(s: unknown, where: string, refuse: (m: string) => never): void {
  if (!isObj(s)) refuse(`${where}: a scope is a mapping`);
  const sc = s as J;
  if (!(typeof sc.form === "string" || isStrList(sc.form))) refuse(`${where}: \`form\` names a form or a list of forms`);
  if (typeof sc.at !== "string") refuse(`${where}: \`at\` is an address`);
  checkBody(sc, `${where} ${sc.at}`, refuse);
  if (sc.scopes !== undefined) {
    if (!Array.isArray(sc.scopes)) refuse(`${where} ${sc.at}: \`scopes\` is a list`);
    for (const [i, c] of (sc.scopes as unknown[]).entries()) checkScope(c, `${where} ${sc.at} > ${i}`, refuse);
  }
}

/** Parse a record, refusing what the grammar lacks (§8.2.2). Field types are the vocabulary's to check (§17). */
export function loadRecord(text: string, where = "record"): RecordDoc {
  const refuse = (m: string): never => {
    throw new AthError("CONFLICT", `${where}: ${m}`);
  };
  let doc: unknown;
  try {
    doc = Bun.YAML.parse(text);
  } catch (e) {
    return refuse(`does not parse: ${(e as Error).message}`);
  }
  if (!isObj(doc)) return refuse("a record is a mapping");
  for (const k of Object.keys(doc)) if (!(RECORD_KEYS as readonly string[]).includes(k)) refuse(`\`${k}\` is not a key of a record`);
  if (doc.intrinsics !== undefined && !isObj(doc.intrinsics)) refuse("`intrinsics` is a mapping");
  if (doc.readings !== undefined && doc.scopes !== undefined) refuse("a record holds `readings` or `scopes`, never both");
  for (const k of ["receipts", "origins", "chrome"] as const)
    if (doc[k] !== undefined && !(Array.isArray(doc[k]) && (doc[k] as unknown[]).every(isObj))) refuse(`\`${k}\` is a list of mappings`);
  for (const [i, rc] of ((doc.receipts as J[] | undefined) ?? []).entries())
    for (const k of RECEIPT_KEYS) if (typeof rc[k] !== "string") refuse(`receipts[${i}]: \`${k}\` is a string`);
  if (doc.shape !== undefined && typeof doc.shape !== "string") refuse("`shape` names a shape");
  if (doc.passes !== undefined) {
    if (!isObj(doc.passes)) refuse("`passes` maps pass ids to passes");
    for (const [id, p] of Object.entries(doc.passes as J)) {
      if (!/^p[1-9]\d*$/.test(id)) refuse(`passes: '${id}' is not a pass id (p<n>)`);
      if (!isObj(p)) refuse(`passes.${id} is a mapping`);
      for (const k of Object.keys(p as J))
        if (!(PASS_KEYS as readonly string[]).includes(k)) refuse(`passes.${id}: \`${k}\` is not a key of a pass`);
      for (const k of ["by", "verify", "vocab", "date"]) if (typeof (p as J)[k] !== "string") refuse(`passes.${id}: \`${k}\` is required`);
      const pp = p as J;
      if (pp.over !== undefined && !isStrList(pp.over)) refuse(`passes.${id}: \`over\` is a list`);
      if (pp.attests !== undefined && !(isStrList(pp.attests) && pp.attests.every((a) => a === "readings" || a === "structure")))
        refuse(`passes.${id}: \`attests\` lists \`readings\` and \`structure\``);
    }
  }
  if (doc.readings !== undefined) {
    if (!isObj(doc.readings)) refuse("`readings` maps addresses to readings");
    for (const [at, r] of Object.entries(doc.readings as J)) {
      if (!isObj(r)) refuse(`readings.${at} is a mapping`);
      for (const k of Object.keys(r as J)) if (!ASPECTS.includes(k as Aspect)) refuse(`readings.${at}: \`${k}\` is not an aspect`);
      checkBody(r as J, `readings.${at}`, refuse);
    }
  }
  if (doc.scopes !== undefined) {
    if (!Array.isArray(doc.scopes)) refuse("`scopes` is a list");
    for (const [i, s] of (doc.scopes as unknown[]).entries()) checkScope(s, `scopes[${i}]`, refuse);
  }
  return doc as unknown as RecordDoc;
}

/** Whether a key is a scope's field (not its form, address, reading or children). */
export const isField = (k: string): boolean => !SCOPE_FIXED.has(k);
